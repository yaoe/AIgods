# Simple Voice Chatbot

A streamlined real-time voice conversation system with an AI chatbot, inspired by mechanical-garden but simplified for easy setup and use.

## Architecture

Unlike mechanical-garden's multi-process ESP32-based system, this implementation uses a single-process architecture with threading for concurrent operations:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Microphone │────▶│   Deepgram   │────▶│     LLM     │
└─────────────┘     │  WebSocket   │     │   (OpenAI)  │
                    └──────────────┘     └─────────────┘
                                                │
┌─────────────┐     ┌──────────────┐           │
│   Speaker   │◀────│  ElevenLabs  │◀──────────┘
└─────────────┘     │  Streaming   │
                    └──────────────┘
```

## Features

- **Real-time Speech Recognition**: Deepgram WebSocket API for low-latency transcription
- **Streaming TTS**: ElevenLabs streaming for natural-sounding responses
- **Configurable Personality**: JSON-based personality configuration
- **Interruption Support**: Can detect and handle interruptions mid-speech
- **Simple Audio I/O**: Direct microphone/speaker access via PyAudio

## Quick Start

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure your API keys in `.env`:
```
DEEPGRAM_API_KEY=your_key
ELEVENLABS_API_KEY=your_key
OPENAI_API_KEY=your_key
```

3. Configure personality in `config/personality.json`

4. Run:
```bash
python src/main.py
```

## Key Differences from mechanical-garden

- **Single Process**: No complex multi-process architecture
- **No ESP32**: Direct computer audio I/O
- **Simplified WebSocket**: Only for Deepgram, not device management
- **Minimal Dependencies**: Core functionality only
- **Easy Configuration**: Single JSON file for personality# AI gods
