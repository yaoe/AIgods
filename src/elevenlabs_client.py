import requests
import json
import queue
import threading
from typing import Callable, Optional, Generator
import logging
try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings, stream
    from io import BytesIO
except ImportError:
    ElevenLabs = None
    VoiceSettings = None
    stream = None

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
    
    def _create_voice_settings(self, voice_settings_dict):
        """Create VoiceSettings object from dict"""
        if not VoiceSettings or not voice_settings_dict:
            return None
        
        return VoiceSettings(
            stability=voice_settings_dict.get("stability", 0.5),
            similarity_boost=voice_settings_dict.get("similarity_boost", 0.75),
            style=voice_settings_dict.get("style", 0.0),
            use_speaker_boost=voice_settings_dict.get("use_speaker_boost", True)
        )
    
    def stream_text_official(self, text: str, voice_settings: dict = None, voice_id: str = None) -> Generator[bytes, None, None]:
        """Stream TTS audio using official ElevenLabs 2.9+ API"""
        if not self.client:
            logger.warning("ElevenLabs client not available, using HTTP fallback")
            yield from self.stream_text(text, voice_settings, voice_id)
            return
            
        # Use the voice_id from personality or fallback to default
        selected_voice_id = voice_id or self.voice_id
        logger.info(f"Starting official ElevenLabs streaming with voice: {selected_voice_id}")
        
        try:
            # Use the official streaming method from ElevenLabs 2.9+
            audio_stream = self.client.text_to_speech.stream(
                text=text,
                voice_id=selected_voice_id,
                model_id="eleven_multilingual_v2",
                voice_settings=VoiceSettings(
                    stability=voice_settings.get("stability", 0.5) if voice_settings else 0.5,
                    similarity_boost=voice_settings.get("similarity_boost", 0.75) if voice_settings else 0.75,
                    style=voice_settings.get("style", 0.0) if voice_settings else 0.0,
                    use_speaker_boost=voice_settings.get("use_speaker_boost", True) if voice_settings else True
                ) if voice_settings else None
            )
            
            logger.info("Successfully created ElevenLabs audio stream")
            
            # Process the audio bytes manually (option 2 from the API docs)
            chunk_count = 0
            for chunk in audio_stream:
                if isinstance(chunk, bytes):
                    chunk_count += 1
                    yield chunk
                    
            logger.info(f"Official streaming completed: {chunk_count} chunks received")
                    
        except Exception as e:
            logger.error(f"Official ElevenLabs streaming error: {e}")
            # Fallback to HTTP streaming
            logger.info("Falling back to HTTP streaming...")
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
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": voice_settings or {
                "stability": 0.6,
                "similarity_boost": 0.99,
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