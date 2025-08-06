# Setup Guide

## Prerequisites

- Python 3.8 or higher
- Working microphone and speakers
- API keys for:
  - [Deepgram](https://deepgram.com/) - for speech recognition
  - [ElevenLabs](https://elevenlabs.io/) - for text-to-speech
  - [OpenAI](https://openai.com/) - for conversational AI

## Installation

1. Clone the repository:
```bash
cd simple-voice-chatbot
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install system dependencies for PyAudio:

**macOS:**
```bash
brew install portaudio
```

**Ubuntu/Debian:**
```bash
sudo apt-get install portaudio19-dev python3-pyaudio
```

**Windows:**
PyAudio wheels should install automatically. If issues occur, download the appropriate wheel from [here](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio).

5. Install ffmpeg (required for pydub):

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html)

## Configuration

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` and add your API keys:
```
DEEPGRAM_API_KEY=your_deepgram_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key
OPENAI_API_KEY=your_openai_api_key
```

3. (Optional) Customize the personality in `config/personality.json`:
```json
{
  "name": "Your Assistant Name",
  "system_message": "Your custom personality prompt",
  "voice_settings": {
    "stability": 0.5,
    "similarity_boost": 0.75
  }
}
```

## Running the Chatbot

```bash
python src/main.py
```

## Troubleshooting

### PyAudio Installation Issues

If you encounter issues installing PyAudio:

**macOS:**
```bash
pip install --global-option='build_ext' --global-option='-I/usr/local/include' --global-option='-L/usr/local/lib' pyaudio
```

**Windows:**
Download the appropriate .whl file from [here](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio) and install:
```bash
pip install PyAudio‑0.2.11‑cp39‑cp39‑win_amd64.whl
```

### Audio Device Issues

If the default audio devices aren't working, you can list available devices:
```python
python -c "import pyaudio; p = pyaudio.PyAudio(); print([p.get_device_info_by_index(i)['name'] for i in range(p.get_device_count())])"
```

### API Rate Limits

- Deepgram: Free tier includes 12,000 minutes/year
- ElevenLabs: Free tier includes 10,000 characters/month
- OpenAI: Pay-as-you-go pricing

## Voice Customization

### Using Different ElevenLabs Voices

1. Get available voices:
```python
from src.elevenlabs_client import ElevenLabsClient
client = ElevenLabsClient(api_key="your_key")
voices = client.get_voices()
for voice in voices:
    print(f"{voice['name']}: {voice['voice_id']}")
```

2. Set the voice ID in `.env`:
```
ELEVENLABS_VOICE_ID=new_voice_id_here
```

### Creating Custom Voices

ElevenLabs supports voice cloning. Upload voice samples through their web interface and use the generated voice ID.