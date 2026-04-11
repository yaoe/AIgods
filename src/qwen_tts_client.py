import os
import requests
import logging
from typing import Generator, Optional

logger = logging.getLogger(__name__)

# Base path to voice profiles (resolved relative to this file)
PROFILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "voice_library", "profiles"
)

# TTS servers: Glitchbox first (MacBook TTS commented out, LLM still uses MacBook)
# ref_audio_base: where reference.wav files live ON THAT SERVER's filesystem
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
        "timeout": 20,
        "streaming_interval": 0.5,
        "ref_audio_base": "/home/plantoidz/PLANTOIDZ/voice_references",
    },
]


class QwenTTSClient:
    """
    Text-to-speech client using Qwen-TTS servers with voice cloning
    from per-profile reference.wav + transcript.txt.
    """

    def __init__(self, voice_id: str = "primavera"):
        self.voice_id = voice_id

    def _load_profile(self, profile_id: str):
        """Load ref_audio path and ref_text from a voice profile directory."""
        profile_dir = os.path.join(PROFILES_DIR, profile_id)
        ref_audio = os.path.join(profile_dir, "reference.wav")
        ref_text_file = os.path.join(profile_dir, "transcript.txt")

        ref_text = ""
        if os.path.exists(ref_text_file):
            with open(ref_text_file) as f:
                ref_text = f.read().strip()

        return ref_audio, ref_text

    def stream_text(self, text: str, voice_settings: dict = None,
                    voice_id: str = None) -> Generator[bytes, None, None]:
        """Stream TTS audio as WAV chunks, trying each server in order."""
        selected_voice = voice_id or self.voice_id
        _, ref_text = self._load_profile(selected_voice)

        for server in TTS_SERVERS:
            try:
                payload = {
                    "model": server["model"],
                    "input": text,
                    "response_format": "wav",
                    "stream": True,
                    "streaming_interval": server["streaming_interval"],
                }

                ref_audio = os.path.join(
                    server["ref_audio_base"], selected_voice, "reference.wav"
                )
                payload["ref_audio"] = ref_audio
                payload["ref_text"] = ref_text

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

    # Alias for backwards compat
    stream_text_official = stream_text

    def generate_audio(self, text: str, voice_settings: dict = None,
                       voice_id: str = None) -> bytes:
        """Generate complete audio (non-streaming, returns all bytes)."""
        chunks = []
        for chunk in self.stream_text(text, voice_settings, voice_id):
            chunks.append(chunk)
        return b"".join(chunks)
