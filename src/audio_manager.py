import pyaudio
import threading
import queue
import numpy as np
import wave
import io
import time
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
                        # Amplify microphone volume for better recognition
                        amplified_data = self._amplify_mic_volume(data)
                        self.on_audio_chunk(amplified_data)
                except Exception as e:
                    logger.error(f"Recording error: {e}")
                    
        finally:
            if stream:
                # Only close, don't stop (stop_stream can hang)
                stream.close()
                
    def _amplify_mic_volume(self, audio_data: bytes, amplification_factor: float = 3.0) -> bytes:
        """Amplify microphone input volume by the given factor"""
        try:
            # Convert bytes to numpy array (16-bit signed integers)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Apply volume amplification (3.0 = triple volume, 2.0 = double volume)
            amplified_audio = (audio_array * amplification_factor)
            
            # Prevent clipping by limiting to int16 range
            amplified_audio = np.clip(amplified_audio, -32768, 32767).astype(np.int16)
            
            # Convert back to bytes
            return amplified_audio.tobytes()
        except Exception as e:
            logger.error(f"Error amplifying mic volume: {e}")
            # Return original data if amplification fails
            return audio_data
    
    def play_audio(self, audio_data: bytes, format: str = "mp3"):
        """Play audio data"""
        self.is_playing = True
        self.is_interrupted = False
        stream = None

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

            logger.info(f"Starting playback of {len(pcm_data)} bytes...")

            # Calculate how long the audio should take to play
            playback_duration = len(pcm_data) / (self.sample_rate * 2)  # 2 bytes per sample (16-bit)

            # Play in chunks, checking for interruption
            chunks_written = 0
            for i in range(0, len(pcm_data), self.chunk_size):
                if self.is_interrupted:
                    logger.info("Playback interrupted")
                    break

                chunk = pcm_data[i:i + self.chunk_size]

                # For very short audio (like ticks), use blocking write to ensure it plays
                if playback_duration < 0.5:
                    stream.write(chunk)  # Blocking write - ensures audio plays
                else:
                    stream.write(chunk, exception_on_underflow=False)

                chunks_written += 1

            logger.info(f"Finished writing {chunks_written} chunks, closing stream...")

            # Close stream directly (don't call stop_stream as it can hang on some systems)
            stream.close()
            stream = None

            logger.info("Audio playback completed successfully")

        except Exception as e:
            logger.error(f"Playback error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # Make absolutely sure stream is closed
            if stream is not None:
                try:
                    # Only close, don't stop (stop_stream can hang)
                    stream.close()
                except:
                    pass
            self.is_playing = False
            logger.info("play_audio() method returning")
            
    def play_audio_raw(self, pcm_data: bytes, sample_rate: int = 22050, channels: int = 1, sample_width: int = 2):
        """Play raw PCM audio data directly"""
        self.is_playing = True
        self.is_interrupted = False
        stream = None

        try:
            logger.info(f"Playing raw PCM: {len(pcm_data)} bytes, {sample_rate}Hz, {channels}ch, {sample_width}B")

            # Open audio stream
            stream = self.audio.open(
                format=self.audio.get_format_from_width(sample_width),
                channels=channels,
                rate=sample_rate,
                output=True,
                output_device_index=self.output_device_index,
                frames_per_buffer=self.chunk_size
            )

            # Play in chunks
            chunks_written = 0
            for i in range(0, len(pcm_data), self.chunk_size):
                if self.is_interrupted:
                    logger.info("Raw audio playback interrupted")
                    break

                chunk = pcm_data[i:i + self.chunk_size]
                stream.write(chunk, exception_on_underflow=False)
                chunks_written += 1

            logger.info(f"Finished playing {chunks_written} raw PCM chunks")

        except Exception as e:
            logger.error(f"Raw PCM playback error: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            if stream is not None:
                try:
                    stream.close()
                except:
                    pass
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
        
    def play_realtime_stream(self, audio_generator):
        """Play audio with real-time streaming (plays chunks as they arrive)"""
        self.is_playing = True
        self.is_interrupted = False
        
        # Start real-time playback thread
        self.playback_thread = threading.Thread(
            target=self._realtime_stream_loop,
            args=(audio_generator,)
        )
        self.playback_thread.daemon = True
        self.playback_thread.start()
        
    def _playback_stream_loop(self, audio_generator):
        """Standard ElevenLabs streaming playback - collect all then play"""
        stream = None
        audio_buffer = b''
        
        try:
            # Collect all audio chunks from ElevenLabs streaming
            logger.info("Streaming audio from ElevenLabs...")
            for chunk in audio_generator:
                audio_buffer += chunk
                    
            if not audio_buffer:
                logger.warning("No audio data received from stream")
                return
                
            logger.info(f"Received {len(audio_buffer)} bytes of streamed audio")
            
            # Convert complete MP3 to PCM
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_buffer))
            audio_segment = audio_segment.set_frame_rate(self.sample_rate)
            audio_segment = audio_segment.set_channels(1)
            audio_segment = audio_segment.set_sample_width(2)
            
            # Increase volume by 6dB (same as regular playback)
            audio_segment = audio_segment + 6
            
            pcm_data = audio_segment.raw_data
            
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
            
            # Play audio
            for i in range(0, len(pcm_data), self.chunk_size):
                if self.is_interrupted:
                    logger.info("Streaming playback interrupted")
                    break
                chunk = pcm_data[i:i + self.chunk_size]
                stream.write(chunk)
                    
        except Exception as e:
            logger.error(f"Streaming playback error: {e}")
        finally:
            if stream:
                # Only close, don't stop (stop_stream can hang)
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