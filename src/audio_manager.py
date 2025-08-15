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
    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024, 
                 output_device_index: Optional[int] = None,
                 input_device_index: Optional[int] = None):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio = pyaudio.PyAudio()
        self.output_device_index = output_device_index
        self.input_device_index = input_device_index
        
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
                input_device_index=self.input_device_index,
                frames_per_buffer=self.chunk_size
            )
            
            while self.is_recording:
                try:
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                    if self.on_audio_chunk:
                        # Reduce microphone volume by applying gain reduction
                        reduced_volume_data = self._reduce_mic_volume(data)
                        self.on_audio_chunk(reduced_volume_data)
                except Exception as e:
                    logger.error(f"Recording error: {e}")
                    
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
                
    def _reduce_mic_volume(self, audio_data: bytes, reduction_factor: float = 0.5) -> bytes:
        """Reduce microphone input volume by the given factor"""
        try:
            # Convert bytes to numpy array (16-bit signed integers)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Apply volume reduction (0.5 = half volume, 0.25 = quarter volume)
            reduced_audio = (audio_array * reduction_factor).astype(np.int16)
            
            # Convert back to bytes
            return reduced_audio.tobytes()
        except Exception as e:
            logger.error(f"Error reducing mic volume: {e}")
            # Return original data if reduction fails
            return audio_data
    
    def play_audio(self, audio_data: bytes, format: str = "mp3"):
        """Play audio data"""
        self.is_playing = True
        self.is_interrupted = False
        
        try:
            # Convert audio to PCM for PyAudio
            if format == "mp3":
                audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_data))
            elif format == "wav":
                audio_segment = AudioSegment.from_wav(io.BytesIO(audio_data))
            elif format == "raw":
                # Raw 16-bit PCM data, create AudioSegment directly
                audio_segment = AudioSegment(
                    data=audio_data,
                    sample_width=2,  # 16-bit = 2 bytes
                    frame_rate=self.sample_rate,
                    channels=1
                )
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            # Convert to 16-bit PCM at our sample rate with proper channel handling
            audio_segment = audio_segment.set_frame_rate(self.sample_rate)
            audio_segment = audio_segment.set_channels(1)  # Force mono
            audio_segment = audio_segment.set_sample_width(2)  # 16-bit
            
            # Increase volume by 6dB (approximately double the volume)
            audio_segment = audio_segment + 6
            
            logger.debug(f"Audio format: {audio_segment.frame_rate}Hz, {audio_segment.channels} channels, {audio_segment.sample_width} bytes/sample")
            
            # Get raw PCM data
            pcm_data = audio_segment.raw_data
            
            # Play through PyAudio with error handling
            try:
                stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.sample_rate,
                    output=True,
                    output_device_index=self.output_device_index,
                    frames_per_buffer=self.chunk_size
                )
            except Exception as e:
                logger.error(f"Error opening audio stream: {e}")
                # Try without specifying device
                stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.sample_rate,
                    output=True,
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
        """Playback loop for streaming audio - true streaming approach"""
        stream = None
        audio_buffer = b''
        min_buffer_size = 8192  # Minimum bytes before starting playback
        pcm_queue = queue.Queue(maxsize=50)  # Buffer for PCM chunks
        playback_started = False
        
        def audio_decoder_thread():
            """Decode MP3 chunks to PCM in a separate thread"""
            try:
                chunk_buffer = b''
                for chunk in audio_generator:
                    chunk_buffer += chunk
                    
                    # Process in larger chunks for better MP3 decoding
                    if len(chunk_buffer) >= 4096:
                        try:
                            # Decode MP3 chunk to PCM
                            audio_segment = AudioSegment.from_mp3(io.BytesIO(chunk_buffer))
                            audio_segment = audio_segment.set_frame_rate(self.sample_rate)
                            audio_segment = audio_segment.set_channels(1)
                            audio_segment = audio_segment.set_sample_width(2)
                            audio_segment = audio_segment + 6  # Volume boost
                            
                            pcm_data = audio_segment.raw_data
                            pcm_queue.put(pcm_data)
                            chunk_buffer = b''  # Reset buffer
                        except Exception as e:
                            # Keep accumulating if decode fails
                            continue
                
                # Process any remaining data
                if chunk_buffer:
                    try:
                        audio_segment = AudioSegment.from_mp3(io.BytesIO(chunk_buffer))
                        audio_segment = audio_segment.set_frame_rate(self.sample_rate)
                        audio_segment = audio_segment.set_channels(1)
                        audio_segment = audio_segment.set_sample_width(2)
                        audio_segment = audio_segment + 6
                        pcm_queue.put(audio_segment.raw_data)
                    except Exception as e:
                        logger.error(f"Error decoding final chunk: {e}")
                
                # Signal end of stream
                pcm_queue.put(None)
                
            except Exception as e:
                logger.error(f"Decoder thread error: {e}")
                pcm_queue.put(None)
        
        try:
            # Start decoder thread
            decoder = threading.Thread(target=audio_decoder_thread)
            decoder.daemon = True
            decoder.start()
            
            logger.info("Starting true audio streaming from ElevenLabs...")
            
            # Open audio stream
            try:
                stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.sample_rate,
                    output=True,
                    output_device_index=self.output_device_index,
                    frames_per_buffer=self.chunk_size
                )
            except Exception as e:
                logger.error(f"Error opening stream: {e}")
                return
            
            # Play PCM chunks as they become available
            accumulated_pcm = b''
            while True:
                if self.is_interrupted:
                    logger.info("Streaming playback interrupted")
                    break
                
                try:
                    # Get PCM chunk (timeout prevents hanging)
                    pcm_chunk = pcm_queue.get(timeout=0.1)
                    
                    if pcm_chunk is None:  # End of stream
                        break
                    
                    accumulated_pcm += pcm_chunk
                    
                    # Start playback once we have enough data
                    if not playback_started and len(accumulated_pcm) >= min_buffer_size:
                        logger.info("Starting audio playback...")
                        playback_started = True
                    
                    # Play accumulated data if we've started
                    if playback_started:
                        for i in range(0, len(accumulated_pcm), self.chunk_size):
                            if self.is_interrupted:
                                break
                            chunk = accumulated_pcm[i:i + self.chunk_size]
                            if len(chunk) > 0:
                                stream.write(chunk)
                        accumulated_pcm = b''  # Clear played data
                        
                except queue.Empty:
                    # Play any accumulated data if available
                    if playback_started and accumulated_pcm:
                        for i in range(0, len(accumulated_pcm), self.chunk_size):
                            if self.is_interrupted:
                                break
                            chunk = accumulated_pcm[i:i + self.chunk_size]
                            if len(chunk) > 0:
                                stream.write(chunk)
                        accumulated_pcm = b''
                    continue
                    
        except Exception as e:
            logger.error(f"Streaming playback error: {e}")
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