import requests
import json
import queue
import threading
from typing import Callable, Optional, Generator
import logging

logger = logging.getLogger(__name__)


class ElevenLabsClient:
    def __init__(self, api_key: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM"):
        self.api_key = api_key
        self.voice_id = voice_id
        self.base_url = "https://api.elevenlabs.io/v1"
        self.audio_queue = queue.Queue()
        self.is_playing = False
        
    def stream_text(self, text: str, voice_settings: dict = None) -> Generator[bytes, None, None]:
        """Stream TTS audio chunks as they're generated"""
        url = f"{self.base_url}/text-to-speech/{self.voice_id}/stream"
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        
        data = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": voice_settings or {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }
        
        response = requests.post(
            url, 
            json=data, 
            headers=headers, 
            stream=True
        )
        
        if response.status_code != 200:
            logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
            return
            
        # Stream audio chunks
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                yield chunk
                
    def generate_audio(self, text: str, voice_settings: dict = None) -> bytes:
        """Generate complete audio (non-streaming)"""
        audio_chunks = []
        for chunk in self.stream_text(text, voice_settings):
            audio_chunks.append(chunk)
        return b''.join(audio_chunks)
    
    def get_voices(self):
        """Get available voices"""
        url = f"{self.base_url}/voices"
        headers = {"xi-api-key": self.api_key}
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()["voices"]
        else:
            logger.error(f"Failed to get voices: {response.status_code}")
            return []
            
    def get_voice_settings(self):
        """Get current voice settings"""
        url = f"{self.base_url}/voices/{self.voice_id}/settings"
        headers = {"xi-api-key": self.api_key}
        
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to get voice settings: {response.status_code}")
            return None