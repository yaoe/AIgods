import os
import requests
import logging
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# Base path to voice profiles (local, for reading transcript.txt)
PROFILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "voice_library", "profiles"
)

# Voice preset: "Ryan" for male, "Vivian" for female
VOICE_PRESETS = {
    "charlie":   "Vivian",   # female
    "ed":        "Ryan",     # male
    "giuseppe":  "Ryan",     # male
    "iannis":    "Ryan",     # male
    "plantony":  "Ryan",     # male
    "primavera": "Vivian",   # female
    "rita":      "Vivian",   # female
    "ryan":      "Ryan",     # male
    "shelby":    "Vivian",   # female
    "sofi":      "Vivian",   # female
}

# TTS servers
TTS_SERVERS = [
    # {
    #     "name": "MacBook",
    #     "url": "http://100.67.155.96:8000/v1/audio/speech",
    #     "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
    #     "timeout": 10,
    #     "streaming_interval": 2.0,
    #     "ref_audio_base": os.path.expanduser(
    #         "~/Desktop/ART <3/The Artist is Present/AI-GOD/simple-voice-chatbot/voice_library/profiles"
    #     ),
    # },
    {
        "name": "Glitchbox",
        "url": "http://100.79.41.86:8000/v1/audio/speech",
        "model": "qwen3-tts",
        "timeout": 60,
        "streaming_interval": 0.5,
        "ref_audio_base": "/home/plantoidz/PLANTOIDZ/voice_references",
    },
]


class QwenTTSClient:
    """
    Text-to-speech client using Qwen-TTS servers with voice cloning.
    Uses ref_audio (file path on the server) + ref_text + voice preset.
    """

    def __init__(self, voice_id: str = "primavera"):
        self.voice_id = voice_id

    def _load_ref_text(self, profile_id: str) -> str:
        """Load ref_text from the local voice profile directory."""
        txt_path = os.path.join(PROFILES_DIR, profile_id, "transcript.txt")
        if os.path.exists(txt_path):
            with open(txt_path) as f:
                return f.read().strip()
        return ""

    def stream_text(self, text: str, voice_settings: dict = None,
                    voice_id: str = None) -> Generator[bytes, None, None]:
        """Stream TTS audio as WAV chunks, trying each server in order."""
        selected_voice = voice_id or self.voice_id
        ref_text = self._load_ref_text(selected_voice)
        voice_preset = VOICE_PRESETS.get(selected_voice, "Vivian")

        for server in TTS_SERVERS:
            try:
                ref_audio = os.path.join(
                    server["ref_audio_base"], selected_voice, "reference.wav"
                )

                payload = {
                    "model": server["model"],
                    "input": text,
                    "voice": voice_preset,
                    "ref_audio": ref_audio,
                    "ref_text": ref_text,
                    "response_format": "wav",
                    "stream": True,
                    "streaming_interval": server.get("streaming_interval", 0.5),
                }

                resp = requests.post(
                    server["url"],
                    json=payload,
                    timeout=server["timeout"],
                    stream=True,
                )

                if resp.status_code == 200:
                    logger.info(f"TTS - using {server['name']} (voice: {selected_voice}, preset: {voice_preset})")
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

    # Alias for backwards compat
    stream_text_official = stream_text

    def generate_audio(self, text: str, voice_settings: dict = None,
                       voice_id: str = None) -> bytes:
        """Generate complete audio (non-streaming, returns all bytes)."""
        chunks = []
        for chunk in self.stream_text(text, voice_settings, voice_id):
            chunks.append(chunk)
        return b"".join(chunks)
