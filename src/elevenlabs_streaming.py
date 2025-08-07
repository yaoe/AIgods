import requests
import json
import threading
import queue
import time
from typing import Callable, Generator
import logging

logger = logging.getLogger(__name__)


class ElevenLabsStreamingClient:
    def __init__(self, api_key: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM"):
        self.api_key = api_key
        self.voice_id = voice_id
        self.base_url = "https://api.elevenlabs.io/v1"
        
    def stream_text_realtime(self, text_generator: Generator[str, None, None], 
                           audio_callback: Callable[[bytes], None],
                           voice_settings: dict = None):
        """Stream TTS from a text generator in real-time"""
        
        def stream_worker():
            """Worker that streams text to ElevenLabs and streams back audio"""
            url = f"{self.base_url}/text-to-speech/{self.voice_id}/stream"
            
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            
            # Buffer text into sentences for better quality
            sentence_buffer = ""
            
            for text_chunk in text_generator:
                sentence_buffer += text_chunk
                
                # Extract complete sentences
                sentences = self._extract_complete_sentences(sentence_buffer)
                
                for sentence in sentences['complete']:
                    if sentence.strip():
                        # Stream this sentence
                        self._stream_sentence(sentence, url, headers, voice_settings, audio_callback)
                        
                sentence_buffer = sentences['incomplete']
                
            # Don't forget the last part
            if sentence_buffer.strip():
                self._stream_sentence(sentence_buffer, url, headers, voice_settings, audio_callback)
                
        # Start streaming in background
        stream_thread = threading.Thread(target=stream_worker)
        stream_thread.daemon = True
        stream_thread.start()
        return stream_thread
        
    def _extract_complete_sentences(self, text: str) -> dict:
        """Extract complete sentences for better TTS quality"""
        sentences = []
        current = ""
        
        for char in text:
            current += char
            if char in '.!?':
                # Look ahead for continuation (e.g., "Mr.", "Dr.")
                if len(current.strip()) > 3:  # Avoid single letters
                    sentences.append(current.strip())
                    current = ""
                    
        return {
            'complete': sentences,
            'incomplete': current
        }
        
    def _stream_sentence(self, sentence: str, url: str, headers: dict, 
                        voice_settings: dict, audio_callback: Callable[[bytes], None]):
        """Stream a single sentence to TTS"""
        try:
            data = {
                "text": sentence,
                "model_id": "eleven_turbo_v2_5",  # Fastest model
                "voice_settings": voice_settings or {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.0,
                    "use_speaker_boost": True
                }
            }
            
            logger.info(f"Streaming TTS: {sentence[:50]}...")
            
            response = requests.post(
                url, 
                json=data, 
                headers=headers, 
                stream=True,
                timeout=5
            )
            
            if response.status_code != 200:
                logger.error(f"ElevenLabs error: {response.status_code}")
                return
                
            # Stream audio chunks as they arrive
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    audio_callback(chunk)
                    
        except Exception as e:
            logger.error(f"Streaming error: {e}")


class RealTimeAudioPlayer:
    """Plays audio chunks as they arrive"""
    
    def __init__(self, audio_manager):
        self.audio_manager = audio_manager
        self.audio_buffer = queue.Queue()
        self.is_playing = False
        self.playback_thread = None
        
    def start_playback(self):
        """Start real-time playback"""
        self.is_playing = True
        self.playback_thread = threading.Thread(target=self._playback_worker)
        self.playback_thread.daemon = True
        self.playback_thread.start()
        
    def add_audio_chunk(self, chunk: bytes):
        """Add audio chunk to playback queue"""
        if self.is_playing:
            self.audio_buffer.put(chunk)
            
    def _playback_worker(self):
        """Worker that plays audio chunks in real-time"""
        audio_chunks = []
        
        while self.is_playing:
            try:
                # Collect a few chunks for smoother playback
                chunk = self.audio_buffer.get(timeout=0.5)
                audio_chunks.append(chunk)
                
                # If we have enough chunks or queue is empty, play them
                if len(audio_chunks) >= 3 or self.audio_buffer.empty():
                    combined_audio = b''.join(audio_chunks)
                    self.audio_manager.play_audio(combined_audio)
                    audio_chunks = []
                    
            except queue.Empty:
                # No more chunks, finish playing what we have
                if audio_chunks:
                    combined_audio = b''.join(audio_chunks)
                    self.audio_manager.play_audio(combined_audio)
                    break
                    
    def stop(self):
        """Stop playback"""
        self.is_playing = False
        if self.playback_thread:
            self.playback_thread.join()