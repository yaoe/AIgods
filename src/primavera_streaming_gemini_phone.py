#!/usr/bin/env python3
"""
Real-time streaming voice chatbot with predictive responses
"""

import random
import os
import sys
import time
import logging
import threading
import queue
import subprocess
import ctypes
from ctypes import cdll
from dotenv import load_dotenv
import signal

from deepgram_client import DeepgramClient
from elevenlabs_client import ElevenLabsClient
from conversation_manager import GeminiConversationManager
from audio_manager import AudioManager
from config_loader import ConfigLoader


# GPIO imports
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError as e:
    GPIO_AVAILABLE = False
    print("Warning: RPi.GPIO not available: {e} — running in test mode")



# Load environment variables
load_dotenv()

# AUDIO DEVICE CONFIGURATION
# Run 'python list_audio_devices.py' to find your device indices
# Set these based on your hardware setup:
AUDIO_INPUT_DEVICE = int(os.getenv("AUDIO_INPUT_DEVICE", "-1"))  # USB microphone index
AUDIO_OUTPUT_DEVICE = int(os.getenv("AUDIO_OUTPUT_DEVICE", "-1"))  # 3.5mm jack index

# Use None if -1 (will use system default)
AUDIO_INPUT_DEVICE = None if AUDIO_INPUT_DEVICE == -1 else AUDIO_INPUT_DEVICE
AUDIO_OUTPUT_DEVICE = None if AUDIO_OUTPUT_DEVICE == -1 else AUDIO_OUTPUT_DEVICE

# Suppress ALSA error messages
os.environ['ALSA_PCM_CARD'] = '1'
os.environ['ALSA_PCM_DEVICE'] = '0'

# Redirect ALSA errors to null (optional - more aggressive)
ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int,
                                     ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)

def py_error_handler(filename, line, function, err, fmt):
    pass

c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

try:
    asound = cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except:
    pass  # If library not found, just continue

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)





# Pin definitions
PHONE_HANDLE_PIN = 21     # Phone handle sensor
PULSE_ENABLE_PIN = 23     # Dial pulse enable
PULSE_INPUT_PIN = 24      # Dial pulse count






class StreamingVoiceChatbot:

    def __init__(self):
        # Load configuration
        self.config = ConfigLoader()

        # Initialize components with configured audio devices
        logger.info(f"Audio Config - Input Device: {AUDIO_INPUT_DEVICE}, Output Device: {AUDIO_OUTPUT_DEVICE}")
        self.audio_manager = AudioManager(
            input_device_index=AUDIO_INPUT_DEVICE,
            output_device_index=AUDIO_OUTPUT_DEVICE
        )

        # Always set volume on startup (most reliable method)
        self._ensure_audio_setup()

        # Debug audio devices
        self._debug_audio_devices()
        self.deepgram = DeepgramClient(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            on_transcript=self.handle_transcript
        )
        self.elevenlabs = ElevenLabsClient(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "ejy6o7z7KXJFIAKYR1Ly")
        )
        self.conversation = GeminiConversationManager(
            api_key=os.getenv("GOOGLE_API_KEY"),
            personality_config=self.config.personality
        )

        # State management
        self.phone_active = False
        self.dial_tone_playing = False
        self.ringback_playing = False
        self.conversation_active = False

        self.is_listening = False
        self.is_processing = False
        self.is_ai_speaking = False  # New flag to track AI speech state
        self.processing_lock = threading.Lock()  # Lock to prevent concurrent processing
        self.current_transcript = ""
        self.accumulated_transcript = ""
        self.last_final_time = 0

        # Initialize GPIO if available
        if GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(PHONE_HANDLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(PULSE_ENABLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(PULSE_INPUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # GPIO states
        self.last_phone_state = True
        self.last_pulse_enable_state = True
        self.last_pulse_state = True
        self.pulse_count = 0
        self.counting_active = False
        
        # Processing tick state
        self.processing_tick_active = False
        
        # Streaming queues
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        
        # Threads
        self.tts_thread = None
        self.playback_thread = None
        
   

    def start(self):

        """Start the phone system"""
        logger.info("📞 Phone Chatbot System Ready!")
        logger.info("Pick up the phone to begin...")
        logger.info(f"Personality: {self.config.personality['name']}")

        # Generate the dial tone and ringback tone .wav files
        self._generate_dial_tone()
        self._generate_ringback_tone()


        try:
            if GPIO_AVAILABLE:
                self._gpio_loop()
            else:
                self._test_loop()

        except KeyboardInterrupt:
            logger.info("\nShutting down...")
        finally:
            self.cleanup()


    def _test_loop(self):

        """Test loop for non-GPIO systems"""
        print("\nTest mode - use keyboard commands:")
        print("  p: Pick up phone")
        print("  h: Hang up phone")
        print("  1-9,0: Dial number (0=10)")
        print("  q: Quit")
        
        while True:
            cmd = input("\nCommand: ").strip().lower()
            
            if cmd == 'p':
                self._handle_phone_pickup()
            elif cmd == 'h':
                self._handle_phone_hangup()
            
            elif cmd in '1234567890':
                num = 10 if cmd == '0' else int(cmd)
                self._stop_dial_tone()
                self._start_conversation()                
            elif cmd == 'q':
                break


    def _gpio_loop(self):

        """Main GPIO monitoring loop"""
        while True:
            phone_state = GPIO.input(PHONE_HANDLE_PIN)
            pulse_enable_state = GPIO.input(PULSE_ENABLE_PIN)
            pulse_state = GPIO.input(PULSE_INPUT_PIN)
            
            # Phone handle detection
            if self.last_phone_state == True and phone_state == False:
                self._handle_phone_pickup()
            elif self.last_phone_state == False and phone_state == True:
                self._handle_phone_hangup()
                
        
                
            # Pulse counting (dialing)
            if self.phone_active and not self.conversation_active:

                # Start counting
                if self.last_pulse_enable_state == True and pulse_enable_state == False:
                    logger.info("📞 Dialing started...")
                    self.counting_active = True
                    self.pulse_count = 0
                    self._stop_dial_tone()
                    
                # Stop counting and process
                elif self.last_pulse_enable_state == False and pulse_enable_state == True:
                    if self.counting_active:
                        self.counting_active = False
                        self._start_conversation()
                        
                # Count pulses
                if self.counting_active:
                    if self.last_pulse_state == True and pulse_state == False:
                        self.pulse_count += 1
                        logger.info(f"Pulse {self.pulse_count}")
                        

            # Update states
            self.last_phone_state = phone_state
            
            self.last_pulse_enable_state = pulse_enable_state
            self.last_pulse_state = pulse_state
            
            time.sleep(0.01)

     

    def _play_random_sound(self, folder_path):

        wav_files = [f for f in os.listdir(folder_path) if f.endswith('.wav')]
        if not wav_files:
            print("No .wav files found.")
            exit()

        selected_file = random.choice(wav_files)
        full_path = os.path.join(folder_path, selected_file)
        print(f"Playing: {selected_file}")
        with open(full_path, "rb") as f:
            audio_bytes = f.read()
        self.audio_manager.play_audio(audio_bytes, format='wav') 

    def _start_conversation(self):

        """Start conversation with Primavera"""

        if self.conversation_active:
                return
        self.conversation_active = True

        #self._stop_dial_tone()

        # Play ringback tone while setting up
        logger.info("Setting up connection...")
        self._play_ringback_tone()

        try:
            # Connect to Deepgram FIRST (before playing greeting)
            logger.info("Connecting to Deepgram...")
            self.deepgram.connect()

            # Start streaming threads
            self.start_streaming_threads()

            # Start listening
            self.is_listening = True
            self.audio_manager.start_recording(self.handle_audio_chunk)

            logger.info("Ready! Stopping ringback and playing greeting...")

            # Stop ringback tone
            self._stop_ringback_tone()
            time.sleep(0.5)  # Brief pause after ringback stops

            # Now play greeting after everything is ready
            self._play_random_sound('./Voice samples/greetings/')

            logger.info("Listening for user speech...")

            # Don't block here - let the main GPIO loop continue checking phone state
            # The conversation will stay active until phone is hung up

        except Exception as e:
            logger.error(f"Error starting conversation: {e}")
            self._stop_ringback_tone()
            self.conversation_active = False          
      
            

    def _handle_phone_pickup(self):
        """Handle when phone is picked up"""
        logger.info("☎️  Phone picked up!")
        self.phone_active = True
        self._play_dial_tone()
        
    def _handle_phone_hangup(self):
        """Handle when phone is hung up - complete shutdown until pickup"""
        logger.info("📞 Phone hung up - shutting down everything!")
        self.phone_active = False
        self.conversation_active = False

        # Stop all ongoing processes
        self._stop_dial_tone()
        self._stop_ringback_tone()
        self._stop_processing_tick()

        # Stop listening and clear state
        self.is_listening = False
        self.is_processing = False
        self.is_ai_speaking = False
        self.accumulated_transcript = ""
        self.current_transcript = ""

        # Stop recording
        self.audio_manager.stop_recording()

        # Interrupt any playing audio
        self.audio_manager.interrupt_playback()

        # Close Deepgram connection
        if self.deepgram:
            try:
                self.deepgram.close()
            except:
                pass

        # Clear queues
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
            except:
                pass

        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except:
                pass

        logger.info("✅ System reset - ready for next pickup")



    def _generate_dial_tone(self):
        """Generate dial tone if it doesn't exist"""
        if not os.path.exists('sounds/dial_tone.wav'):
            logger.info("Generating dial tone...")
            subprocess.run([sys.executable, 'generate_dial_tone.py'])

    def _generate_ringback_tone(self):
        """Generate ringback tone (the tone you hear while waiting for someone to answer)"""
        if not os.path.exists('sounds/ringback_tone.wav'):
            logger.info("Generating ringback tone...")
            import numpy as np
            import wave

            sample_rate = 16000
            duration = 2.0  # One ring cycle: beep-beep (0.4s each) + silence (1.2s)

            # Generate two short beeps at 440Hz and 480Hz (typical ringback frequencies)
            t_beep = np.linspace(0, 0.4, int(sample_rate * 0.4), False)
            beep1 = np.sin(2 * np.pi * 440 * t_beep)
            beep2 = np.sin(2 * np.pi * 480 * t_beep)
            beep = (beep1 + beep2) * 0.3  # Mix both frequencies, moderate volume

            # Add fade in/out to beeps
            fade_samples = int(0.01 * sample_rate)
            beep[:fade_samples] *= np.linspace(0, 1, fade_samples)
            beep[-fade_samples:] *= np.linspace(1, 0, fade_samples)

            # Create silence
            silence = np.zeros(int(sample_rate * 1.2))

            # Combine: beep + beep + silence
            ringback = np.concatenate([beep, beep, silence])

            # Convert to 16-bit PCM
            ringback_audio = (ringback * 32767).astype(np.int16)

            # Save to file
            os.makedirs('sounds', exist_ok=True)
            with wave.open('sounds/ringback_tone.wav', 'w') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(ringback_audio.tobytes())

            logger.info("Ringback tone generated")
            

    def _play_dial_tone(self):
        """Play dial tone in loop"""
        if self.dial_tone_playing:
            return
            
        self.dial_tone_playing = True
        
        def play_loop():
            while self.dial_tone_playing and self.phone_active:
                try:
                    # Only play if phone is still active
                    if not self.phone_active:
                        break
                        
                    # Load and play dial tone
                    with open('sounds/dial_tone.wav', 'rb') as f:
                        audio_data = f.read()
                    self.audio_manager.play_audio(audio_data, format='wav')
                    
                    # Small gap between loops
                    if self.dial_tone_playing and self.phone_active:
                        time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error playing dial tone: {e}")
                    break
                    
        threading.Thread(target=play_loop, daemon=True).start()
        
    def _stop_dial_tone(self):
        """Stop dial tone"""
        self.dial_tone_playing = False
        # time.sleep(2)  # Let it finish
        print("dialtone is over")

    def _play_ringback_tone(self):
        """Play ringback tone in loop (the tone while waiting for answer)"""
        if self.ringback_playing:
            return

        self.ringback_playing = True

        def play_loop():
            while self.ringback_playing and self.phone_active:
                try:
                    # Only play if phone is still active
                    if not self.phone_active or not self.ringback_playing:
                        break

                    # Load and play ringback tone
                    with open('sounds/ringback_tone.wav', 'rb') as f:
                        audio_data = f.read()
                    self.audio_manager.play_audio(audio_data, format='wav')

                    # No gap needed - the silence is built into the tone
                except Exception as e:
                    logger.error(f"Error playing ringback tone: {e}")
                    break

        threading.Thread(target=play_loop, daemon=True).start()

    def _stop_ringback_tone(self):
        """Stop ringback tone"""
        self.ringback_playing = False
        logger.info("Ringback tone stopped")





    def start_streaming_threads(self):
        """Start background threads for streaming"""
        # TTS thread - converts text chunks to audio
        self.tts_thread = threading.Thread(target=self._tts_worker)
        self.tts_thread.daemon = True
        self.tts_thread.start()
        
        # Playback thread - plays audio chunks
        self.playback_thread = threading.Thread(target=self._playback_worker)
        self.playback_thread.daemon = True
        self.playback_thread.start()
        
    def handle_audio_chunk(self, audio_data: bytes):
        """Handle audio chunk from microphone"""
        # Only send audio if we're listening AND AI is not speaking
        if self.is_listening and not self.is_ai_speaking:
            self.deepgram.send_audio(audio_data)
            
    def handle_transcript(self, transcript: str, is_final: bool):
        """Handle transcript from Deepgram"""
        # Ignore all transcripts while AI is speaking
        if self.is_ai_speaking or not transcript.strip():
            return
            
        current_time = time.time()
        
        if is_final:
            logger.info(f"Final: {transcript}")
            # Double-check AI is not speaking before processing
            if not self.is_ai_speaking:
                self.accumulated_transcript += " " + transcript
                self.last_final_time = current_time
                
                # Start processing immediately on sentence boundaries
                if self._is_sentence_boundary(self.accumulated_transcript):
                    self.process_accumulated_transcript()
        else:
            # Show interim results only if AI is not speaking
            if not self.is_ai_speaking:
                self.current_transcript = transcript
            
    def _is_sentence_boundary(self, text: str) -> bool:
        """Check if text ends with sentence boundary"""
        text = text.strip()
        # More aggressive sentence detection for faster responses
        return (text.endswith(('.', '?', '!')) or 
                len(text.split()) > 10 or  # Long enough
                any(text.endswith(phrase) for phrase in [' and', ' so', ' but']))
                
    def process_accumulated_transcript(self):
        """Process the accumulated transcript"""
        # Use lock to prevent race conditions when checking/setting processing state
        with self.processing_lock:
            # Don't process if AI is speaking, already processing, or no transcript
            if self.is_ai_speaking or self.is_processing or not self.accumulated_transcript.strip():
                return

            transcript = self.accumulated_transcript.strip()
            self.accumulated_transcript = ""

            # Don't process very short utterances
            if len(transcript.split()) < 2:
                return

            logger.info(f"Processing: {transcript}")
            # Set both flags immediately while holding the lock
            self.is_processing = True
            self.is_ai_speaking = True  # Set this early to block new transcripts

        # Start ticking sound to indicate processing
        self._start_processing_tick()

        # Start generating response in background with timeout monitoring
        response_thread = threading.Thread(
            target=self._generate_streaming_response_with_monitor,
            args=(transcript,)
        )
        response_thread.daemon = True
        response_thread.start()
        
    def _generate_streaming_response_with_monitor(self, transcript: str):
        """Wrapper to monitor response generation with timeout"""
        thread_timeout = 60.0  # Maximum time to wait for thread completion
        
        # Create the actual response generation thread
        generation_thread = threading.Thread(
            target=self._generate_streaming_response,
            args=(transcript,)
        )
        generation_thread.daemon = True
        generation_thread.start()
        
        # Monitor the thread with timeout
        generation_thread.join(thread_timeout)
        
        if generation_thread.is_alive():
            logger.error(f"Response generation thread timed out after {thread_timeout} seconds")
            # Force stop processing state
            self.is_processing = False
            self._stop_processing_tick()
            # Queue error message
            error_msg = "I'm sorry, I'm having trouble responding right now."
            self.text_queue.put(error_msg)
        
    def _generate_streaming_response(self, transcript: str):
        """Generate and stream response with timeout protection"""
        response_timeout = 45.0  # 45 second timeout for response generation
        start_time = time.time()
        
        try:
            # Add to conversation
            self.conversation.add_user_message(transcript)
            
            # Stream response text with timeout protection
            sentence_buffer = ""
            response_generator = self.conversation.generate_response(streaming=True, timeout=30.0)
            
            for text_chunk in response_generator:
                # Check if we've exceeded the overall timeout
                if time.time() - start_time > response_timeout:
                    logger.warning("Response generation timed out")
                    error_msg = "I'm sorry, I'm taking too long to respond."
                    self.text_queue.put(error_msg)
                    break
                    
                sentence_buffer += text_chunk
            
                # Send complete sentences to TTS
                # sentences = self._extract_sentences(sentence_buffer)
                # for sentence in sentences['complete']:
                #     if sentence.strip():
                #         logger.info(f"Queueing TTS: {sentence}")
                #         self.text_queue.put(sentence)
                        
                # sentence_buffer = sentences['incomplete']
                
            # Don't forget the last part
            if sentence_buffer.strip():
                self.text_queue.put(sentence_buffer)

        #    self._play_random_sound('./Voice samples/acks/')

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            # Provide user feedback for errors
            error_msg = "I'm sorry, I encountered an issue. Can you please try again?"
            self.text_queue.put(error_msg)
        finally:
            self.is_processing = False
            
    def _extract_sentences(self, text: str) -> dict:
        """Extract complete sentences from text"""
        sentences = []
        current = ""
        
        for char in text:
            current += char
            if char in '.!?':
                sentences.append(current.strip())
                current = ""
                
        return {
            'complete': sentences,
            'incomplete': current
        }
        
    def _tts_worker(self):
        """Worker thread for text-to-speech conversion with WebSocket streaming"""
        while True:
            try:
                # Get text from queue
                text = self.text_queue.get(timeout=1)

                if text is None:  # Shutdown signal
                    break

                # Use WebSocket streaming for faster response
                logger.info(f"WebSocket streaming TTS for: {text[:50]}...")
                audio_chunks = []
                chunk_count = 0

                for chunk in self.elevenlabs.stream_text_realtime(text, self.config.get_voice_settings()):
                    audio_chunks.append(chunk)
                    chunk_count += 1
                    # Log first chunk arrival
                    if chunk_count == 1:
                        logger.info(f"First audio chunk received ({len(chunk)} bytes)! Collecting more...")
                    # Log progress every 20 chunks
                    elif chunk_count % 20 == 0:
                        logger.info(f"Received {chunk_count} audio chunks ({len(b''.join(audio_chunks))} bytes)...")

                # Combine all MP3 chunks for playback
                audio_data = b''.join(audio_chunks)
                logger.info(f"WebSocket TTS complete: {chunk_count} chunks, {len(audio_data)} bytes total")
                self.audio_queue.put(('mp3', audio_data))  # Tag as MP3 audio from WebSocket

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"TTS error: {e}")
                
    def _playback_worker(self):
        """Worker thread for audio playback"""
        while True:
            try:
                # Get audio from queue
                queue_item = self.audio_queue.get(timeout=1)

                if queue_item is None:  # Shutdown signal
                    break

                # Handle both old format (raw bytes) and new format (tuple)
                if isinstance(queue_item, tuple):
                    audio_format, audio_data = queue_item
                else:
                    # Old format - assume MP3
                    audio_format = 'mp3'
                    audio_data = queue_item

                # Stop processing tick when audio is ready to play
                self._stop_processing_tick()

                # Stop listening while AI is speaking to prevent queuing user speech
                was_listening = self.is_listening
                if was_listening:
                    self.is_listening = False
                    logger.info("🔇 Stopped listening during AI speech")

                # Clear any accumulated transcript to prevent processing during AI speech
                self.accumulated_transcript = ""
                self.current_transcript = ""

                # Play audio with explicit format
                logger.info(f"Playing audio chunk (format: {audio_format})...")
                logger.info(f"Audio output device: {self.audio_manager.output_device_index}")

                # Play MP3 audio (both WebSocket and HTTP use MP3 format)
                # Skip cleaning on Pi3 as it's too slow - play directly
                logger.info(f"Audio size: {len(audio_data)} bytes")

                # Estimate duration from file size (MP3 at ~22-32 kbps for 22050Hz)
                estimated_duration = (len(audio_data) / 3000) + 5.0  # ~3KB per second for lower bitrate
                logger.info(f"Estimated duration: {estimated_duration:.1f}s")

                # Play audio directly without cleaning (faster on Pi3)
                success = self._play_audio_with_timeout(audio_data, timeout=estimated_duration, format='mp3')

                if not success:
                    logger.error("Audio playback failed or timed out - waiting before resuming")
                    # Wait a bit before resuming to avoid overlapping with stuck audio
                    time.sleep(2.0)

                # Clear AI speaking flag and resume listening after AI finishes speaking
                self.is_ai_speaking = False
                self.is_processing = False  # Also clear processing flag
                if was_listening:
                    self.is_listening = True
                    logger.info("🎤 Resumed listening after AI speech")

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Playback error: {e}")
                # Make sure we reset flags on error
                self.is_ai_speaking = False
                self.is_processing = False
                
    def cleanup(self):
        """Clean up resources"""
        logger.info("Shutting down...")
        self.is_listening = False
        
        # Stop threads
        self.text_queue.put(None)
        self.audio_queue.put(None)
        
        # Clean up
        self.audio_manager.cleanup()
        self.deepgram.close()
        
        # Turn off relay and cleanup GPIO
        if GPIO_AVAILABLE:
            GPIO.cleanup()


    def _ensure_audio_setup(self):
        """Ensure audio is properly configured every time we start"""
        try:
            # Wait a moment for audio system to be ready
            time.sleep(1)
            
            # Force 3.5mm jack (only on Raspberry Pi - safe to run on other systems)
            subprocess.run(['amixer', 'cset', 'numid=3', '1'], 
                        check=False, capture_output=True)
            
            # Set maximum volume (card 1 is typically USB audio on Raspberry Pi)
            subprocess.run(['amixer', '-c', '1', 'sset', 'PCM', '100%'], 
                        check=False, capture_output=True)
            
            # Verify it worked
            result = subprocess.run(['amixer', '-c', '1', 'sget', 'PCM'], 
                                capture_output=True, text=True, check=False)
            if '100%' in result.stdout:
                logger.info("🔊 Audio configured: 3.5mm jack at 100% volume")
            else:
                logger.warning("⚠️ Volume setting may not have worked (may be running on Mac)")
                
        except Exception as e:
            logger.error(f"Error setting up audio: {e}")
            
    def _debug_audio_devices(self):
        """Debug available audio devices"""
        try:
            logger.info("=== AUDIO DEVICES DEBUG ===")
            logger.info("Available output devices:")
            for device in self.audio_manager.get_output_devices():
                logger.info(f"  {device['index']}: {device['name']} ({device['channels']} channels)")
            
            logger.info("Available input devices:")
            for device in self.audio_manager.get_input_devices():
                logger.info(f"  {device['index']}: {device['name']} ({device['channels']} channels)")
                
            logger.info(f"Selected input device: {AUDIO_INPUT_DEVICE}")
            logger.info(f"Selected output device: {AUDIO_OUTPUT_DEVICE}")
            logger.info("===========================")
        except Exception as e:
            logger.error(f"Error debugging audio devices: {e}")
            
    def _clean_audio_end(self, audio_data: bytes) -> bytes:
        """Remove noise at the end of ElevenLabs audio by trimming and fading out"""
        try:
            from pydub import AudioSegment
            import io
            
            # Load the MP3 audio
            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_data))
            
            # Get audio length in milliseconds
            audio_length = len(audio_segment)
            
            # Trim last 0.1 seconds (100ms) to remove end noise
            trim_amount = min(100, audio_length // 4)  # Don't trim more than 25% of audio
            if audio_length > trim_amount:
                audio_segment = audio_segment[:-trim_amount]
            
            # Add a 200ms fade out to make it smooth
            fade_duration = min(200, len(audio_segment) // 2)  # Don't fade more than 50% of audio
            audio_segment = audio_segment.fade_out(fade_duration)
            
            # Convert back to MP3 bytes
            output_buffer = io.BytesIO()
            audio_segment.export(output_buffer, format="mp3")
            output_buffer.seek(0)
            
            return output_buffer.read()
            
        except Exception as e:
            logger.error(f"Error cleaning audio: {e}")
            # Return original audio if cleaning fails
            return audio_data
            
    def _get_audio_duration(self, audio_data: bytes) -> float:
        """Get duration of audio in seconds"""
        try:
            from pydub import AudioSegment
            import io

            audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_data))
            duration_seconds = len(audio_segment) / 1000.0  # pydub returns milliseconds
            return duration_seconds
        except Exception as e:
            logger.error(f"Error getting audio duration: {e}")
            # Return a default safe duration
            return 30.0

    def _play_audio_with_timeout(self, audio_data: bytes, timeout: float = 10.0, format: str = 'mp3'):
        """Play audio with timeout protection to prevent hanging"""
        result = [None]
        exception = [None]

        def play_audio():
            try:
                if format == 'pcm':
                    # Play raw PCM audio (16-bit, 22050Hz, mono)
                    self.audio_manager.play_audio_raw(audio_data, sample_rate=22050, channels=1, sample_width=2)
                else:
                    # Play MP3
                    self.audio_manager.play_audio(audio_data, format='mp3')
                result[0] = "success"
            except Exception as e:
                exception[0] = e

        # Start audio playback in separate thread
        playback_thread = threading.Thread(target=play_audio)
        playback_thread.daemon = True
        playback_thread.start()

        # Wait for completion with timeout
        playback_thread.join(timeout)

        if playback_thread.is_alive():
            # Thread is still running, timeout occurred
            logger.error(f"Audio playback timed out after {timeout:.1f} seconds - this should not happen!")
            logger.error("Audio thread is still running in background - may cause overlap")
            # Note: Can't force-kill PyAudio thread if it's hanging in native code
            return False

        if exception[0]:
            logger.error(f"Audio playback error: {exception[0]}")
            return False

        return True
            
    def _start_processing_tick(self):
        """Start processing tick sound"""
        if self.processing_tick_active:
            return
            
        self.processing_tick_active = True
        tick_thread = threading.Thread(target=self._play_processing_tick)
        tick_thread.daemon = True
        tick_thread.start()
        
    def _stop_processing_tick(self):
        """Stop processing tick sound"""
        self.processing_tick_active = False
        
    def _play_processing_tick(self):
        """Play subtle ticking sound during processing"""
        try:
            import numpy as np
            from pydub import AudioSegment
            import io
            
            sample_rate = 16000
            duration = 0.08  # Short tick (80ms)
            frequency = 220  # A3 note (220Hz) - low, subtle tone

            # Generate subtle tick sound
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            tick_tone = np.sin(2 * np.pi * frequency * t) * 0.6  # Moderate volume
            
            # Add fade in/out to avoid clicks
            fade_samples = int(0.005 * sample_rate)  # 5ms fade
            tick_tone[:fade_samples] *= np.linspace(0, 1, fade_samples)
            tick_tone[-fade_samples:] *= np.linspace(1, 0, fade_samples)
            
            # Convert to 16-bit PCM
            tick_audio = (tick_tone * 32767).astype(np.int16)
            
            # Create AudioSegment
            audio_segment = AudioSegment(
                data=tick_audio.tobytes(),
                sample_width=2,
                frame_rate=sample_rate,
                channels=1
            )
            
            # Export as WAV
            wav_buffer = io.BytesIO()
            audio_segment.export(wav_buffer, format="wav")
            wav_buffer.seek(0)
            tick_wav = wav_buffer.read()

            # Save tick to file for debugging
            try:
                with open("/tmp/debug_tick.wav", "wb") as f:
                    f.write(tick_wav)
                logger.info("Saved tick to /tmp/debug_tick.wav for testing")
            except Exception as e:
                logger.error(f"Could not save tick: {e}")

            logger.info("⏳ Playing processing tick...")
            logger.info(f"Tick: duration={duration}s, frequency={frequency}Hz, volume=1.0, size={len(tick_wav)} bytes")
            logger.info(f"Output device index: {self.audio_manager.output_device_index}")

            # Play ticks every 0.8 seconds while processing
            # Use afplay directly since PyAudio isn't working reliably for short sounds
            tick_count = 0
            while self.processing_tick_active:
                if self.processing_tick_active:
                    tick_count += 1
                    logger.info(f"🔊 TICK #{tick_count}")
                    # Use aplay on Linux/Raspberry Pi, afplay on macOS
                    if sys.platform == 'linux':
                        # Use device 1 (3.5mm jack) on Raspberry Pi
                        subprocess.Popen(['aplay', '-D', 'plughw:1,0', '/tmp/debug_tick.wav'],
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
                    else:
                        subprocess.Popen(['afplay', '/tmp/debug_tick.wav'],
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
                    time.sleep(0.8)  # Pause between ticks
                
        except Exception as e:
            logger.error(f"Error playing processing tick: {e}")



def main():
    """Main entry point"""
    # Check environment variables
    required_vars = ["DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY", "GOOGLE_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
        
    # Create and start chatbot
    chatbot = StreamingVoiceChatbot()
    chatbot.start()
    

if __name__ == "__main__":
    main()