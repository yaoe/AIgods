import pyaudio
import threading
import queue
import numpy as np
import wave
import io
from typing import Callable, Optional
import logging
from pydub import AudioSegment
from pydub.playback import play

logger = logging.getLogger(__name__)


class AudioManager:
    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024, output_device_index: Optional[int] = None):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio = pyaudio.PyAudio()
        self.output_device_index = output_device_index
        
        # Audio queues
        self.record_queue = queue.Queue()
        self.playback_queue = queue.Queue()
        
        # State management
        self.is_recording = False
        self.is_playing = False
        self.is_interrupted = False
        
        # Callbacks
        self.on_audio_chunk: Optional[Callable[[bytes], None]] = None
        
        # Threads
        self.record_thread: Optional[threading.Thread] = None
        self.playback_thread: Optional[threading.Thread] = None
        
    def start_recording(self, callback: Callable[[bytes], None]):
        """Start recording from microphone"""
        if self.is_recording:
            logger.warning("Already recording")
            return
            
        self.on_audio_chunk = callback
        self.is_recording = True
        
        self.record_thread = threading.Thread(target=self._record_loop)
        self.record_thread.daemon = True
        self.record_thread.start()
        
        logger.info("Started recording")
        
    def stop_recording(self):
        """Stop recording"""
        self.is_recording = False
        if self.record_thread:
            self.record_thread.join()
        logger.info("Stopped recording")
        
    def _record_loop(self):
        """Recording loop"""
        stream = None
        try:
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            
            while self.is_recording:
                try:
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                    if self.on_audio_chunk:
                        self.on_audio_chunk(data)
                except Exception as e:
                    logger.error(f"Recording error: {e}")
                    
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
                
    def play_audio(self, audio_data: bytes, format: str = "mp3"):
        """Play audio data"""
        self.is_playing = True
        self.is_interrupted = False
        
        try:
            # Convert MP3 to PCM for PyAudio
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_data))
            
            # Convert to 16-bit PCM at our sample rate
            audio_segment = audio_segment.set_frame_rate(self.sample_rate)
            audio_segment = audio_segment.set_channels(1)
            audio_segment = audio_segment.set_sample_width(2)  # 16-bit
            
            # Get raw PCM data
            pcm_data = audio_segment.raw_data
            
            # Play through PyAudio
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=self.chunk_size
            )
            
            # Play in chunks, checking for interruption
            for i in range(0, len(pcm_data), self.chunk_size):
                if self.is_interrupted:
                    logger.info("Playback interrupted")
                    break
                    
                chunk = pcm_data[i:i + self.chunk_size]
                stream.write(chunk)
                
            stream.stop_stream()
            stream.close()
            
        except Exception as e:
            logger.error(f"Playback error: {e}")
        finally:
            self.is_playing = False
            
    def play_audio_stream(self, audio_generator):
        """Play streaming audio"""
        self.is_playing = True
        self.is_interrupted = False
        
        # Start playback thread
        self.playback_thread = threading.Thread(
            target=self._playback_stream_loop,
            args=(audio_generator,)
        )
        self.playback_thread.daemon = True
        self.playback_thread.start()
        
    def _playback_stream_loop(self, audio_generator):
        """Playback loop for streaming audio"""
        stream = None
        audio_buffer = b''
        
        try:
            # Collect ALL audio before playback (simpler approach)
            logger.info("Buffering audio...")
            for chunk in audio_generator:
                audio_buffer += chunk
                    
            if not audio_buffer:
                logger.warning("No audio data received")
                return
                
            logger.info(f"Received {len(audio_buffer)} bytes of audio")
            
            # Convert complete MP3 to PCM
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_buffer))
            audio_segment = audio_segment.set_frame_rate(self.sample_rate)
            audio_segment = audio_segment.set_channels(1)
            audio_segment = audio_segment.set_sample_width(2)
            
            pcm_data = audio_segment.raw_data
            
            # Open audio stream
            stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=self.chunk_size
            )
            
            # Play complete audio
            for i in range(0, len(pcm_data), self.chunk_size):
                if self.is_interrupted:
                    logger.info("Playback interrupted")
                    break
                chunk = pcm_data[i:i + self.chunk_size]
                stream.write(chunk)
                    
        except Exception as e:
            logger.error(f"Playback error: {e}")
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            self.is_playing = False
            
    def interrupt_playback(self):
        """Interrupt current playback"""
        self.is_interrupted = True
        
    def get_input_devices(self):
        """Get list of input devices"""
        devices = []
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxInputChannels']
                })
        return devices
        
    def get_output_devices(self):
        """Get list of output devices"""
        devices = []
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            if info['maxOutputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxOutputChannels']
                })
        return devices
        
    def cleanup(self):
        """Clean up audio resources"""
        self.stop_recording()
        self.interrupt_playback()
        self.audio.terminate()