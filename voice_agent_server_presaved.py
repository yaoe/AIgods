## RUN WITH:  uv run voice_agent_server_presaved.py
## Uses the latest pre-saved voice reference — no 30s recording phase needed.

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import numpy as np
from collections import deque
import requests as req
import tempfile, os, base64, json, asyncio
import soundfile as sf
import onnxruntime as ort
import urllib.request
import httpx

app = FastAPI()

# ── Audio settings ──────────────────────────────────────────────────
RATE = 16000
CHUNK = 512
VAD_THRESHOLD = 0.5
STOP_CHUNKS = 48          # ~1.5s silence to consider speech done
PRE_CHUNKS = 7            # ~200ms pre-speech buffer

# ── External services ──────────────────────────────────────────────
WHISPER_URL = "http://100.67.155.96:8005/v1/audio/transcriptions"
WHISPER_PROMPT = "Plantoid, Plantoids, plantoid"

LLM_URL = "http://100.79.41.86:1235/v1/chat/completions"
LLM_MODEL = "LFM2.5-VL-1.6B-Q8_0.gguf"

TTS_URL = "http://localhost:8000/v1/audio/speech"

VOICE_REF_DIR = os.path.join(os.path.dirname(__file__), "voice_references")

SYSTEM_PROMPT = (
    "You are Plantoid, a decentralized autonomous organism. "
    "You are having a live voice conversation. "
    "Keep your responses concise and conversational."
)

# ── Load pre-saved voice reference at startup ──────────────────────

def _load_latest_voice_ref() -> tuple[str, str]:
    """Find the most recent voice reference folder and load it."""
    if not os.path.isdir(VOICE_REF_DIR):
        raise RuntimeError(f"No voice_references directory at {VOICE_REF_DIR}")

    folders = sorted(
        [d for d in os.listdir(VOICE_REF_DIR)
         if os.path.isdir(os.path.join(VOICE_REF_DIR, d))],
        reverse=True,
    )
    for folder_name in folders:
        folder = os.path.join(VOICE_REF_DIR, folder_name)
        wav = os.path.join(folder, "reference.wav")
        txt = os.path.join(folder, "transcript.txt")
        if os.path.exists(wav) and os.path.exists(txt):
            with open(wav, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            with open(txt) as f:
                ref_text = f.read().strip()
            print(f"[startup] loaded voice reference from {folder}")
            print(f"[startup] ref_text: {ref_text[:120]}...")
            return b64, ref_text

    raise RuntimeError(f"No valid voice reference found in {VOICE_REF_DIR}")

VOICE_REF_B64, VOICE_REF_TEXT = _load_latest_voice_ref()

# ── Silero VAD ──────────────────────────────────────────────────────
ONNX_PATH = os.path.join(os.path.dirname(__file__), "silero_vad.onnx")
if not os.path.exists(ONNX_PATH):
    urllib.request.urlretrieve(
        "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
        ONNX_PATH,
    )


class SileroVAD:
    def __init__(self):
        self.session = ort.InferenceSession(ONNX_PATH, providers=["CPUExecutionProvider"])
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, 64), dtype=np.float32)

    def reset(self):
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, 64), dtype=np.float32)

    def prob(self, chunk_f32):
        x = np.concatenate((self._context, chunk_f32.reshape(1, -1)), axis=1)
        out, self._state = self.session.run(
            None,
            {
                "input": x.astype(np.float32),
                "state": self._state,
                "sr": np.array(16000, dtype=np.int64),
            },
        )
        self._context = x[:, -64:]
        return float(out[0][0])


# ── Helpers ─────────────────────────────────────────────────────────

def transcribe_audio(audio_f32: np.ndarray) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(tmp.name, audio_f32, RATE)
    try:
        with open(tmp.name, "rb") as f:
            resp = req.post(
                WHISPER_URL,
                files={"file": f},
                data={"prompt": WHISPER_PROMPT},
                timeout=30,
            )
        if resp.status_code == 200:
            return resp.json().get("text", "").strip()
        print(f"[whisper] error {resp.status_code}: {resp.text[:200]}")
        return ""
    except Exception as e:
        print(f"[whisper] exception: {e}")
        return ""
    finally:
        os.unlink(tmp.name)


def call_llm(transcript: str, history: list[dict] | None = None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": transcript})

    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        resp = req.post(LLM_URL, json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        print(f"[llm] error {resp.status_code}: {resp.text[:200]}")
        return "Sorry, I could not generate a response."
    except Exception as e:
        print(f"[llm] exception: {e}")
        return "Sorry, I could not generate a response."


async def tts_stream(ws: WebSocket, text: str):
    """Call Qwen3-TTS with the pre-loaded voice clone and stream audio back."""
    payload = {
        "model": "qwen3-tts",
        "input": text,
        "voice": "Vivian",
        "voice_data": VOICE_REF_B64,
        "ref_text": VOICE_REF_TEXT,
        "response_format": "pcm",
        "stream": True,
        "speed": 1.0,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            async with client.stream("POST", TTS_URL, json=payload) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    print(f"[tts] error {resp.status_code}: {err[:200]}")
                    await ws.send_json({"event": "error", "message": "TTS generation failed"})
                    return
                await ws.send_json({"event": "tts_start", "format": "pcm", "sample_rate": 24000})
                async for chunk in resp.aiter_bytes(chunk_size=4800):
                    await ws.send_bytes(chunk)
                await ws.send_json({"event": "tts_end"})
    except Exception as e:
        print(f"[tts] exception: {e}")
        await ws.send_json({"event": "error", "message": str(e)})


# ── WebSocket endpoint ─────────────────────────────────────────────

@app.websocket("/v1/voice-agent")
async def voice_agent(ws: WebSocket):
    await ws.accept()
    vad = SileroVAD()

    pre_buffer = deque(maxlen=PRE_CHUNKS)
    segment: list[np.ndarray] = []
    speech_active = False
    trailing_silence = 0
    conversation_history: list[dict] = []

    await ws.send_json({
        "event": "ready",
        "message": "Voice reference pre-loaded. Conversation mode active — speak freely.",
    })

    try:
        while True:
            data = await ws.receive_bytes()
            if not data:
                break

            int16 = np.frombuffer(data, dtype=np.int16)
            f32 = int16.astype(np.float32) / 32768.0

            for i in range(0, len(f32), CHUNK):
                chunk = f32[i : i + CHUNK]
                if len(chunk) < CHUNK:
                    chunk = np.pad(chunk, (0, CHUNK - len(chunk)))

                is_speech = vad.prob(chunk) > VAD_THRESHOLD

                if not speech_active:
                    pre_buffer.append(chunk)
                    if is_speech:
                        segment = list(pre_buffer)
                        speech_active = True
                        trailing_silence = 0
                        await ws.send_json({"event": "speech_start"})
                else:
                    segment.append(chunk)
                    trailing_silence = 0 if is_speech else trailing_silence + 1

                    if trailing_silence >= STOP_CHUNKS:
                        seg_audio = np.concatenate(segment, dtype=np.float32)

                        # Transcribe
                        seg_text = transcribe_audio(seg_audio)
                        if seg_text:
                            await ws.send_json({"event": "transcription", "text": seg_text})

                            # LLM
                            llm_response = call_llm(seg_text, conversation_history)
                            await ws.send_json({"event": "llm_response", "text": llm_response})

                            conversation_history.append({"role": "user", "content": seg_text})
                            conversation_history.append({"role": "assistant", "content": llm_response})

                            # TTS with pre-loaded voice
                            await tts_stream(ws, llm_response)

                        # Reset segment state
                        segment.clear()
                        speech_active = False
                        trailing_silence = 0
                        pre_buffer.clear()
                        vad.reset()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[ws] error: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8300)
