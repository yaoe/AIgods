import requests
import json
import queue
import threading
from typing import Callable, Optional, Generator
import logging
try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    from io import BytesIO
except ImportError:
    ElevenLabs = None
    VoiceSettings = None

logger = logging.getLogger(__name__)


class ElevenLabsClient:
    def __init__(self, api_key: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM"):
        self.api_key = api_key
        self.voice_id = voice_id
        self.base_url = "https://api.elevenlabs.io/v1"
        self.audio_queue = queue.Queue()
        self.is_playing = False
        
        # Initialize official ElevenLabs client if available
        self.client = ElevenLabs(api_key=api_key) if ElevenLabs else None
    
    def stream_text_official(self, text: str, voice_settings: dict = None, voice_id: str = None) -> Generator[bytes, None, None]:
        """Stream TTS audio using direct ElevenLabs REST API"""
        # Use the voice_id from personality or fallback to default
        selected_voice_id = voice_id or self.voice_id
        logger.info(f"Starting ElevenLabs REST API streaming with voice: {selected_voice_id}")
        
        # Use direct REST API streaming (always works)
        url = f"{self.base_url}/text-to-speech/{selected_voice_id}/stream"
        
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        # Convert voice_settings to the expected format
        voice_config = voice_settings or {}
        api_voice_settings = {
            "stability": voice_config.get("stability", 0.5),
            "similarity_boost": voice_config.get("similarity_boost", 0.75),
            "style": voice_config.get("style", 0.0),
            "use_speaker_boost": voice_config.get("use_speaker_boost", True)
        }
        
        data = {
            "text": text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": api_voice_settings
        }
        
        try:
            logger.info("Making streaming request to ElevenLabs REST API...")
            response = requests.post(url, headers=headers, json=data, stream=True)
            
            if response.status_code != 200:
                logger.error(f"ElevenLabs API error: {response.status_code} - {response.text}")
                return
            
            logger.info("Successfully connected to ElevenLabs streaming API")
            
            # Stream audio chunks
            chunk_count = 0
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    chunk_count += 1
                    yield chunk
                    
            logger.info(f"Streaming completed: {chunk_count} chunks received")
                    
        except Exception as e:
            logger.error(f"ElevenLabs REST API streaming error: {e}")
            # Still fallback to the original HTTP method if this fails
            logger.info("Falling back to original HTTP streaming...")
            yield from self.stream_text(text, voice_settings, voice_id)
        
    def stream_text_realtime(self, text: str, voice_settings: dict = None, on_audio_chunk: Callable[[bytes], None] = None):
        """Stream TTS audio using websockets for real-time playback"""
        if not on_audio_chunk:
            return
            
        voice_settings = voice_settings or {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True
        }
        
        # WebSocket URL for streaming
        ws_url = f"wss://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream-input?model_id=eleven_turbo_v2"
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                if data.get("audio"):
                    # Decode base64 audio data
                    audio_chunk = base64.b64decode(data["audio"])
                    on_audio_chunk(audio_chunk)
                elif data.get("isFinal"):
                    ws.close()
            except Exception as e:
                logger.error(f"Error processing websocket message: {e}")
        
        def on_error(ws, error):
            logger.error(f"WebSocket error: {error}")
        
        def on_open(ws):
            # Send initial configuration
            config = {
                "text": " ",  # Initial space to start stream
                "voice_settings": voice_settings,
                "generation_config": {
                    "chunk_length_schedule": [120, 160, 250, 290]
                }
            }
            ws.send(json.dumps(config))
            
            # Send the actual text
            text_message = {
                "text": text + " ",
                "try_trigger_generation": True
            }
            ws.send(json.dumps(text_message))
            
            # Send EOS (End of Stream)
            eos_message = {"text": ""}
            ws.send(json.dumps(eos_message))
        
        # Create and run websocket
        ws = websocket.WebSocketApp(
            ws_url,
            header=[f"xi-api-key: {self.api_key}"],
            on_message=on_message,
            on_error=on_error,
            on_open=on_open
        )
        
        ws.run_forever()
    
    def stream_text(self, text: str, voice_settings: dict = None, voice_id: str = None) -> Generator[bytes, None, None]:
        """Stream TTS audio chunks as they're generated (HTTP fallback)"""
        selected_voice_id = voice_id or self.voice_id
        logger.info(f"Starting HTTP streaming with voice: {selected_voice_id}")
        url = f"{self.base_url}/text-to-speech/{selected_voice_id}/stream"
        
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