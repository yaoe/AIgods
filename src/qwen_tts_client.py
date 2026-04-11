import requests
import logging
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# TTS servers: MacBook first, Glitchbox fallback
TTS_SERVERS = [
    {
        "name": "MacBook",
        "url": "http://100.67.155.96:8000/v1/audio/speech",
        "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
        "timeout": 10,
        "use_ref_audio": True,
        "ref_audio_base": "/Users/ya/Desktop/PLANTOID 22/WHISPER/QwenTTS/voice-samples",
        "ref_text": "Hello my name is Plantoid, I am a blockchain-based lifeform. I feed off cryptocurrency in order to replicate myself.",
        "streaming_interval": 2.0,
    },
    {
        "name": "Glitchbox",
        "url": "http://100.79.41.86:8000/v1/audio/speech",
        "model": "qwen3-tts",
        "timeout": 20,
        "use_ref_audio": False,
        "streaming_interval": 0.5,
    },
]


class QwenTTSClient:
    """
    Text-to-speech client using Qwen-TTS servers.
    Drop-in replacement for ElevenLabsClient with same interface:
      - stream_text(text, ...) -> Generator[bytes]
      - generate_audio(text, ...) -> bytes
    """

    def __init__(self, voice_id: str = "primavera"):
        self.voice_id = voice_id

    def stream_text(self, text: str, voice_settings: dict = None,
                    voice_id: str = None) -> Generator[bytes, None, None]:
        """Stream TTS audio as WAV chunks, trying each server in order."""
        selected_voice = voice_id or self.voice_id

        for server in TTS_SERVERS:
            try:
                payload = {
                    "model": server["model"],
                    "input": text,
                    "response_format": "wav",
                    "stream": True,
                    "streaming_interval": server["streaming_interval"],
                }

                if server["use_ref_audio"]:
                    payload["ref_audio"] = f"{server['ref_audio_base']}/{selected_voice}.mp3"
                    payload["ref_text"] = server["ref_text"]
                else:
                    payload["voice"] = f"clone:{selected_voice}"

                resp = requests.post(
                    server["url"],
                    json=payload,
                    timeout=server["timeout"],
                    stream=True,
                )

                if resp.status_code == 200:
                    logger.info(f"TTS - using {server['name']} (voice: {selected_voice})")
                    for chunk in resp.iter_content(chunk_size=4096):
                        if chunk:
                            yield chunk
                    return
                else:
                    logger.warning(
                        f"TTS {server['name']} returned {resp.status_code}"
                    )

            except Exception as e:
                logger.warning(f"TTS {server['name']} failed: {e}")

        logger.error("All TTS servers failed")

    # Alias so callers using the old ElevenLabs streaming path keep working
    stream_text_official = stream_text

    def generate_audio(self, text: str, voice_settings: dict = None,
                       voice_id: str = None) -> bytes:
        """Generate complete audio (non-streaming, returns all bytes)."""
        chunks = []
        for chunk in self.stream_text(text, voice_settings, voice_id):
            chunks.append(chunk)
        return b"".join(chunks)
