#!/usr/bin/env python3
"""
Pre-render greeting lines to WAVs via OmniVoice voice clone.

One-time tool: turns a text file of greetings into ready-to-play WAV
files so the chatbot can play a random WAV instantly on pickup, instead
of waiting ~2–3s for live TTS synthesis each time.

Usage:
    python render_greetings.py \\
        --in config/logina_greetings.txt \\
        --voice logina \\
        --out "Voice samples/greetings_logina/"

Re-run any time you edit the greetings file; it overwrites existing
files in-place (numbered greeting_01.wav, greeting_02.wav, ...).
"""
import argparse
import os
import struct
import sys
import wave
from pathlib import Path

import requests

TTS_URL = os.getenv("TTS_URL", "http://100.79.41.86:8000/v1/audio/speech")
TTS_MODEL = os.getenv("TTS_MODEL", "qwen3-tts")
SAMPLE_RATE = 24000


def _extract_pcm(data: bytes) -> bytes:
    """Strip RIFF/WAVE headers from a streamed WAV response and return
    raw 16-bit mono PCM. Mirrors src/omnivoice_client.py:_extract_pcm."""
    out, i = bytearray(), 0
    n = len(data)
    while i < n:
        if i + 12 <= n and data[i:i + 4] == b"RIFF" and data[i + 8:i + 12] == b"WAVE":
            j = i + 12
            while j + 8 <= n:
                if data[j:j + 4] == b"data":
                    i = j + 8
                    break
                j += 8 + struct.unpack_from("<I", data, j + 4)[0]
            else:
                i += 44  # malformed header — best-effort skip
        else:
            out.append(data[i])
            i += 1
    return bytes(out)


def render_one(text: str, voice_id: str) -> bytes:
    """POST one greeting to OmniVoice, return raw 16-bit mono PCM @ 24kHz."""
    payload = {
        "model": TTS_MODEL,
        "input": text,
        "voice": f"clone:{voice_id}",
        "response_format": "wav",
        "stream": True,
        "streaming_interval": 0.5,
    }
    resp = requests.post(TTS_URL, json=payload, timeout=(5, 90), stream=True)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    pcm = bytearray()
    for chunk in resp.iter_content(chunk_size=4096):
        if chunk:
            pcm.extend(_extract_pcm(chunk))
    return bytes(pcm)


def save_wav(pcm: bytes, path: Path):
    """Wrap PCM in a clean WAV file (16-bit mono @ SAMPLE_RATE)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)


def main():
    parser = argparse.ArgumentParser(
        description="Pre-render greeting lines to WAVs via OmniVoice.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--in", dest="in_file", required=True, type=Path,
                        help="Text file with one greeting per non-blank line")
    parser.add_argument("--voice", required=True,
                        help="Voice clone name (e.g. logina, primavera)")
    parser.add_argument("--out", required=True, type=Path,
                        help="Output folder to write WAVs into")
    parser.add_argument("--prefix", default="greeting_",
                        help="Filename prefix (default: greeting_)")
    args = parser.parse_args()

    if not args.in_file.is_file():
        sys.exit(f"Input file not found: {args.in_file}")

    lines = [
        ln.strip()
        for ln in args.in_file.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if not lines:
        sys.exit(f"No non-empty lines in {args.in_file}")

    print(f"Rendering {len(lines)} greetings as clone:{args.voice} → {args.out}")
    print(f"TTS server: {TTS_URL}")

    failed = 0
    for i, text in enumerate(lines, start=1):
        out_path = args.out / f"{args.prefix}{i:02d}.wav"
        preview = text[:60] + ("…" if len(text) > 60 else "")
        print(f"  [{i:02d}/{len(lines)}] {preview}")
        try:
            pcm = render_one(text, args.voice)
            if not pcm:
                raise RuntimeError("empty PCM from server")
            save_wav(pcm, out_path)
            print(f"      → {out_path.name} ({len(pcm):,} bytes PCM, "
                  f"~{len(pcm) / (SAMPLE_RATE * 2):.1f}s)")
        except Exception as e:
            print(f"      ✗ failed: {e}")
            failed += 1

    rendered = len(list(args.out.glob(f"{args.prefix}*.wav")))
    print(f"\nDone. {rendered} WAVs in {args.out} ({failed} failed)")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
