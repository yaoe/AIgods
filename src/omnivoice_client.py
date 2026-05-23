"""
OmniVoice TTS client.

Mirrors the streaming TTS approach from plantoid15-raspberry's
lib/plantoid/speech.py — same Qwen3-TTS server on glitchbox, but with
the cleaner "clone:NAME" voice syntax and WAV streaming (vs. raw PCM
with explicit voice_path + ref_text).

The server streams WAV: chunks may contain RIFF headers followed by
PCM data, and partial RIFF blocks can span chunk boundaries. We extract
just the PCM samples so callers get a clean 16-bit mono stream
(default 24kHz) drop-in compatible with QwenTTSClient.
"""

import os
import time
import struct
import logging
from typing import Generator, Optional

import requests
from requests.exceptions import ChunkedEncodingError, ConnectionError as ReqConnectionError

logger = logging.getLogger(__name__)


# OmniVoice / Qwen3-TTS servers. MacBook left here commented for reference.
TTS_SERVERS = [
    # {
    #     "name": "MacBook",
    #     "url": "http://100.67.155.96:8000/v1/audio/speech",
    #     "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
    #     "timeout": (2, 30),
    #     "streaming_interval": 2.0,
    # },
    {
        "name": "Glitchbox",
        "url": os.getenv("TTS_URL", "http://100.79.41.86:8000/v1/audio/speech"),
        "model": os.getenv("TTS_MODEL", "qwen3-tts"),
        "timeout": (2, 30),
        "streaming_interval": 0.5,
    },
]

DEFAULT_SAMPLE_RATE = 24000


def _extract_pcm(data: bytes) -> bytes:
    """Strip RIFF/WAVE headers from a chunk, return raw PCM bytes.

    Streaming WAV responses concatenate independent RIFF blocks back-to-back.
    Each block looks like:
        'RIFF' <size:4> 'WAVE' <subchunks...> 'data' <size:4> <pcm...>
    This walks the buffer, skipping every RIFF header it finds and
    appending only the PCM payload to the output. Bytes that don't
    start a recognisable RIFF block are passed through verbatim
    (they're part of a previous block's PCM payload).
    """
    out, i = bytearray(), 0
    n = len(data)
    while i < n:
        if i + 12 <= n and data[i:i + 4] == b'RIFF' and data[i + 8:i + 12] == b'WAVE':
            j = i + 12
            while j + 8 <= n:
                if data[j:j + 4] == b'data':
                    i = j + 8
                    break
                j += 8 + struct.unpack_from('<I', data, j + 4)[0]
            else:
                i += 44  # malformed/short header — best-effort skip
        else:
            out.append(data[i])
            i += 1
    return bytes(out)


class OmniVoiceClient:
    """Streaming TTS via OmniVoice/Qwen3-TTS with voice cloning by name.

    Drop-in replacement for QwenTTSClient. Yields raw 16-bit mono PCM
    at 24kHz (parsed out of the server's WAV stream).
    """

    def __init__(self, voice_id: str = "primavera"):
        self.voice_id = voice_id
        self.sample_rate = DEFAULT_SAMPLE_RATE

    def stream_text(self, text: str, voice_settings: dict = None,
                    voice_id: str = None) -> Generator[bytes, None, None]:
        """Stream TTS audio as raw PCM chunks, trying each server in order.

        Resilience strategy per server:
        1. Try chunked-streaming (faster first byte).
        2. If the stream breaks before any data, retry once.
        3. If retry also fails, fall back to a non-streaming request
           and yield the parsed PCM as one buffer (slower but robust).
        """
        selected_voice = voice_id or self.voice_id

        for server in TTS_SERVERS:
            base_payload = {
                "model": server["model"],
                "input": text,
                "voice": f"clone:{selected_voice}",
                "response_format": "wav",
            }

            # Attempt 1 + retry: chunked streaming
            for attempt in range(2):
                yielded_any = False
                try:
                    resp = requests.post(
                        server["url"],
                        json={
                            **base_payload,
                            "stream": True,
                            "streaming_interval": server.get("streaming_interval", 0.5),
                        },
                        timeout=server["timeout"],
                        stream=True,
                    )

                    if resp.status_code != 200:
                        logger.warning(
                            f"TTS {server['name']} HTTP {resp.status_code}: {resp.text[:200]}"
                        )
                        break  # don't retry on HTTP-level failures

                    logger.info(
                        f"TTS - using {server['name']} (clone: {selected_voice}, "
                        f"stream attempt {attempt + 1})"
                    )
                    for chunk in resp.iter_content(chunk_size=4096):
                        if not chunk:
                            continue
                        pcm = _extract_pcm(chunk)
                        if pcm:
                            yielded_any = True
                            yield pcm
                    return  # success

                except (ChunkedEncodingError, ReqConnectionError) as e:
                    if yielded_any:
                        logger.warning(
                            f"TTS {server['name']} stream broke mid-flight "
                            f"(partial audio delivered): {e}"
                        )
                        return
                    logger.warning(
                        f"TTS {server['name']} stream broke before any data "
                        f"(attempt {attempt + 1}): {e}"
                    )
                    if attempt == 0:
                        time.sleep(0.3)
                        continue
                except Exception as e:
                    logger.warning(f"TTS {server['name']} streaming failed: {e}")
                    break

            # Fallback: non-streaming request (one shot, full WAV in body)
            try:
                logger.info(f"TTS {server['name']} — falling back to non-streaming")
                resp = requests.post(
                    server["url"],
                    json={**base_payload, "stream": False},
                    timeout=server["timeout"],
                )
                if resp.status_code == 200 and resp.content:
                    pcm = _extract_pcm(resp.content)
                    if pcm:
                        logger.info(
                            f"TTS - using {server['name']} (clone: {selected_voice}, non-streaming)"
                        )
                        yield pcm
                        return
                else:
                    logger.warning(
                        f"TTS {server['name']} non-streaming HTTP "
                        f"{resp.status_code}: {resp.text[:200]}"
                    )
            except Exception as e:
                logger.warning(f"TTS {server['name']} non-streaming failed: {e}")

        logger.error("All TTS servers failed")

    def generate_audio(self, text: str, voice_settings: dict = None,
                       voice_id: str = None) -> bytes:
        """Generate complete PCM audio (non-streaming)."""
        return b"".join(self.stream_text(text, voice_settings, voice_id))
