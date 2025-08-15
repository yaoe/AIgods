#!/usr/bin/env python3
"""
Phone-based Voice Chatbot System
- Pick up phone → hear dial tone
- Dial 1-10 → select personality
- Start conversation with selected personality
- Hang up → end conversation
"""

import os
import sys
import time
import json
import logging
import threading
import subprocess
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.deepgram_client import DeepgramClient
from src.elevenlabs_client import ElevenLabsClient
from src.conversation_manager import ConversationManager
from src.audio_manager import AudioManager
from src.config_loader import ConfigLoader

# GPIO imports
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("Warning: RPi.GPIO not available, running in test mode")

load_dotenv()

# AUDIO DEVICE CONFIGURATION
# Run 'python list_audio_devices.py' to find your device indices
# Set these based on your hardware setup:
AUDIO_INPUT_DEVICE = int(os.getenv("AUDIO_INPUT_DEVICE", "-1"))  # USB microphone index
AUDIO_OUTPUT_DEVICE = int(os.getenv("AUDIO_OUTPUT_DEVICE", "-1"))  # 3.5mm jack index

# Use None if -1 (will use system default)
AUDIO_INPUT_DEVICE = None if AUDIO_INPUT_DEVICE == -1 else AUDIO_INPUT_DEVICE
AUDIO_OUTPUT_DEVICE = None if AUDIO_OUTPUT_DEVICE == -1 else AUDIO_OUTPUT_DEVICE

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Pin definitions
PHONE_HANDLE_PIN = 21     # Phone handle sensor
MUTE_BUTTON_PIN = 25      # Mute button
RELAY_PIN = 8             # Relay output (mute indicator)
PULSE_ENABLE_PIN = 23     # Dial pulse enable
PULSE_INPUT_PIN = 24      # Dial pulse count

class PhoneChatbot:
    def __init__(self):
        # Audio components with separate input/output devices
        # USB mic as input, 3.5mm jack as output
        logger.info(f"Audio Config - Input Device: {AUDIO_INPUT_DEVICE}, Output Device: {AUDIO_OUTPUT_DEVICE}")
        self.audio_manager = AudioManager(
            input_device_index=AUDIO_INPUT_DEVICE,
            output_device_index=AUDIO_OUTPUT_DEVICE
        )
        
        # State management
        self.phone_active = False
        self.dial_tone_playing = False
        self.conversation_active = False
        self.current_personality = None
        self.chatbot_instance = None
        
        # Conversation state (simplified like main.py)
        self.is_listening = False
        self.is_processing = False
        self.current_transcript = ""
        self.last_final_transcript = ""
        self.shadow_listening = False
        self.last_transcript_time = 0
        self.processing_start_time = 0  # Track when we start processing
        self.audio_playback_start_time = 0  # Track when audio actually starts playing
        
        # GPIO state
        self.last_phone_state = True
        self.last_mute_button_state = True
        self.last_pulse_enable_state = True
        self.last_pulse_state = True
        self.pulse_count = 0
        self.counting_active = False
        
        # Mute state
        self.is_muted = False
        
        # Load personality list
        self.personalities = self._load_personalities()
        
        # Initialize GPIO if available
        if GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(PHONE_HANDLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(MUTE_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(RELAY_PIN, GPIO.OUT)
            GPIO.setup(PULSE_ENABLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(PULSE_INPUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
            # Initialize relay to OFF (unmuted)
            GPIO.output(RELAY_PIN, GPIO.LOW)
            
    def _load_personalities(self):
        """Load all personality configurations"""
        personalities = {}
        for i in range(1, 11):
            try:
                with open(f'config/personalities/personality_{i}.json', 'r') as f:
                    personalities[i] = json.load(f)
                    logger.info(f"Loaded personality {i}: {personalities[i]['name']}")
            except Exception as e:
                logger.error(f"Error loading personality {i}: {e}")
        return personalities
        
    def start(self):
        """Start the phone system"""
        logger.info("📞 Phone Chatbot System Ready!")
        logger.info("Pick up the phone to begin...")
        
        # Start dial tone generation
        self._generate_dial_tone()
        
        try:
            if GPIO_AVAILABLE:
                self._gpio_loop()
            else:
                self._test_loop()
        except KeyboardInterrupt:
            logger.info("\nShutting down...")
        finally:
            self.cleanup()
            
    def _gpio_loop(self):
        """Main GPIO monitoring loop"""
        while True:
            phone_state = GPIO.input(PHONE_HANDLE_PIN)
            mute_button_state = GPIO.input(MUTE_BUTTON_PIN)
            pulse_enable_state = GPIO.input(PULSE_ENABLE_PIN)
            pulse_state = GPIO.input(PULSE_INPUT_PIN)
            
            # Phone handle detection
            if self.last_phone_state == True and phone_state == False:
                self._handle_phone_pickup()
            elif self.last_phone_state == False and phone_state == True:
                self._handle_phone_hangup()
                
            # Mute button detection (only when phone is active)
            if self.phone_active:
                if self.last_mute_button_state == True and mute_button_state == False:
                    self._handle_mute_pressed()
                elif self.last_mute_button_state == False and mute_button_state == True:
                    self._handle_mute_released()
                
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
                        self._process_dial(self.pulse_count)
                        
                # Count pulses
                if self.counting_active:
                    if self.last_pulse_state == True and pulse_state == False:
                        self.pulse_count += 1
                        logger.info(f"Pulse {self.pulse_count}")
                        
            # Update states
            self.last_phone_state = phone_state
            self.last_mute_button_state = mute_button_state
            self.last_pulse_enable_state = pulse_enable_state
            self.last_pulse_state = pulse_state
            
            time.sleep(0.01)
            
    def _test_loop(self):
        """Test loop for non-GPIO systems"""
        print("\nTest mode - use keyboard commands:")
        print("  p: Pick up phone")
        print("  h: Hang up phone")
        print("  m: Toggle mute")
        print("  1-9,0: Dial number (0=10)")
        print("  q: Quit")
        
        while True:
            cmd = input("\nCommand: ").strip().lower()
            
            if cmd == 'p':
                self._handle_phone_pickup()
            elif cmd == 'h':
                self._handle_phone_hangup()
            elif cmd == 'm':
                if self.is_muted:
                    self._handle_mute_released()
                else:
                    self._handle_mute_pressed()
            elif cmd in '1234567890':
                num = 10 if cmd == '0' else int(cmd)
                self._stop_dial_tone()
                self._process_dial(num)
            elif cmd == 'q':
                break
                
    def _handle_phone_pickup(self):
        """Handle when phone is picked up"""
        logger.info("☎️  Phone picked up!")
        self.phone_active = True
        self._play_dial_tone()
        
    def _handle_phone_hangup(self):
        """Handle when phone is hung up - complete shutdown until pickup"""
        logger.info("📞 Phone hung up - shutting down everything!")
        self.phone_active = False
        
        # Immediately stop ALL audio playback
        self.audio_manager.interrupt_playback()
        
        # Stop dial tone
        self._stop_dial_tone()
        
        # End conversation completely
        self._end_conversation()
        
        # Ensure complete silence - stop recording too
        if self.audio_manager.is_recording:
            self.audio_manager.stop_recording()
        
        logger.info("📞 System silent - waiting for phone pickup...")
        
    def _handle_mute_pressed(self):
        """Handle mute button press - mute microphone"""
        logger.info("🔇 MUTE button pressed - microphone muted")
        self.is_muted = True
        
        # Turn on relay (mute indicator)
        if GPIO_AVAILABLE:
            GPIO.output(RELAY_PIN, GPIO.HIGH)
        
        # Stop sending audio to Deepgram (effectively mute mic)
        logger.info("🎤 Microphone muted - not sending audio to speech recognition")
        
    def _handle_mute_released(self):
        """Handle mute button release - unmute microphone"""
        logger.info("🔊 MUTE button released - microphone unmuted")
        self.is_muted = False
        
        # Turn off relay (unmute indicator)
        if GPIO_AVAILABLE:
            GPIO.output(RELAY_PIN, GPIO.LOW)
            
        logger.info("🎤 Microphone unmuted - resuming speech recognition")
        
    def _generate_dial_tone(self):
        """Generate dial tone if it doesn't exist"""
        if not os.path.exists('sounds/dial_tone.wav'):
            logger.info("Generating dial tone...")
            subprocess.run([sys.executable, 'generate_dial_tone.py'])
            
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
        time.sleep(0.2)  # Let it finish
        
    def _process_dial(self, number):
        """Process dialed number and start conversation"""
        logger.info(f"📞 Dialed: {number}")
        
        if number < 1 or number > 10:
            logger.warning(f"Invalid number: {number}")
            # Play error tone or message
            return
            
        if number not in self.personalities:
            logger.error(f"Personality {number} not found")
            return
            
        # Select personality
        self.current_personality = self.personalities[number]
        logger.info(f"🎭 Selected: {self.current_personality['name']}")
        
        # Play phone-line beep while connecting to the god
        logger.info("📞 Connecting to divine line...")
        self._start_connection_beep()
        
        # Start conversation with selected personality
        self._start_conversation()
        
    def _start_conversation(self):
        """Start conversation with selected personality"""
        if self.conversation_active:
            return
            
        self.conversation_active = True
        
        # Create chatbot instance with selected personality
        try:
            # Create a config loader with the selected personality
            config = ConfigLoader()
            config.personality = self.current_personality
            
            # Initialize chatbot components
            self.deepgram = DeepgramClient(
                api_key=os.getenv("DEEPGRAM_API_KEY"),
                on_transcript=self._handle_transcript
            )
            self.elevenlabs = ElevenLabsClient(
                api_key=os.getenv("ELEVENLABS_API_KEY"),
                voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
            )
            self.conversation = ConversationManager(
                api_key=os.getenv("OPENAI_API_KEY"),
                personality_config=self.current_personality
            )
            
            # Connect to Deepgram
            self.deepgram.connect()
            
            # Start listening
            self.is_listening = True
            self.audio_manager.start_recording(self._handle_audio_chunk)
            
            # The god answers the phone immediately with their unique greeting
            greeting = self.current_personality.get("greeting", f"You have reached {self.current_personality['name']}")
            
            # Start greeting generation and playback immediately
            threading.Thread(target=self._play_god_greeting, args=(greeting,), daemon=True).start()
            
            logger.info(f"✅ {self.current_personality['name']} is answering the divine phone!")
            
        except Exception as e:
            logger.error(f"Error starting conversation: {e}")
            self.conversation_active = False
            
    def _end_conversation(self):
        """End current conversation"""
        if not self.conversation_active:
            return
            
        logger.info("Ending conversation...")
        self.conversation_active = False
        self.is_listening = False
        
        # Stop recording
        self.audio_manager.stop_recording()
        
        # Close connections
        if hasattr(self, 'deepgram'):
            self.deepgram.close()
            
        # Clear state
        self.current_personality = None
        self.current_transcript = ""
        self.last_final_transcript = ""
        self.shadow_listening = False
        self.processing_start_time = 0
        self.audio_playback_start_time = 0
        
        # Reset mute state
        self.is_muted = False
        if GPIO_AVAILABLE:
            GPIO.output(RELAY_PIN, GPIO.LOW)
        
    def _handle_audio_chunk(self, audio_data: bytes):
        """Handle audio chunk from microphone (respects mute state)"""
        # Don't send audio if muted
        if self.is_muted:
            return
            
        if (self.is_listening and not self.is_processing) or self.shadow_listening:
            if hasattr(self, 'deepgram'):
                self.deepgram.send_audio(audio_data)
            
    def _handle_transcript(self, transcript: str, is_final: bool):
        """Handle transcript from Deepgram (using main.py approach)"""
        if not transcript.strip():
            return
            
        # Handle interruption during AI speech
        if self.shadow_listening and self.audio_manager.is_playing:
            # Ignore fragments that come too soon after processing started
            # OR before audio playback actually started (these are trailing parts)
            time_since_processing = time.time() - self.processing_start_time
            time_since_audio_start = time.time() - self.audio_playback_start_time
            
            if time_since_processing < 5.0 or time_since_audio_start < 1.0:
                logger.info(f"Ignoring trailing fragment (processing: {time_since_processing:.1f}s, audio: {time_since_audio_start:.1f}s): {transcript}")
                return
                
            if is_final and self._is_intentional_interruption(transcript):
                logger.info(f"🛑 INTERRUPTION detected: {transcript}")
                self._handle_interruption(transcript)
                return
            
        if is_final:
            logger.info(f"Final transcript: {transcript}")
            self.last_final_transcript = transcript
            self.last_transcript_time = time.time()
            
            # Check if we should process this as a complete utterance
            if self._should_process_utterance(transcript):
                # Add a small delay to ensure the user finished speaking
                self._schedule_delayed_processing(transcript)
        else:
            # Update current transcript for display
            self.current_transcript = transcript
            
    def _is_intentional_interruption(self, transcript: str) -> bool:
        """Check if this is an intentional interruption"""
        transcript = transcript.strip().lower()
        
        # Must be at least 2 words
        words = transcript.split()
        if len(words) < 2:
            return False
            
        # Check for common interruption phrases (English and French)
        interruption_patterns = [
            # English patterns
            'wait', 'stop', 'hold on', 'excuse me', 'sorry', 'actually',
            'let me', 'but', 'however', 'i need', 'i want', 'can you',
            'what about', 'i think', 'no', 'yes but', 'hang on',
            'shut up', 'quiet', 'enough', 'okay stop', 'okay shut',
            # French patterns
            'attends', 'attendez', 'arrête', 'arrêtez', 'pardon', 'excusez-moi',
            'désolé', 'désolée', 'en fait', 'laisse-moi', 'laissez-moi',
            'mais', 'cependant', 'j\'ai besoin', 'je veux', 'pouvez-vous',
            'et alors', 'je pense', 'non', 'oui mais', 'moment', 'un moment'
        ]
        
        for pattern in interruption_patterns:
            if transcript.startswith(pattern):
                return True
                
        # Check for questions or longer statements (English and French)
        question_words = ('what', 'why', 'how', 'when', 'where', 'who',  # English
                         'qu\'est-ce', 'pourquoi', 'comment', 'quand', 'où', 'qui',  # French
                         'que', 'quoi', 'quel', 'quelle', 'quels', 'quelles')  # More French
        if transcript.startswith(question_words) or len(words) >= 4:
            return True
            
        return False
    
    def _should_process_utterance(self, transcript: str) -> bool:
        """Determine if we should process the utterance"""
        # Simple heuristic: process if it's a complete sentence or question
        transcript = transcript.strip()
        
        # Check for question marks or common sentence endings
        if transcript.endswith(('?', '.', '!')) or len(transcript.split()) > 3:
            return True
            
        return False
    
    def _schedule_delayed_processing(self, transcript: str):
        """Schedule processing with a delay to ensure sentence completion"""
        def delayed_process():
            # Wait for 3.0 seconds to ensure user has finished speaking completely
            time.sleep(3.0)
            
            # Check if there was a more recent transcript (user continued speaking)
            if time.time() - self.last_transcript_time < 2.5:
                logger.info("User still speaking, not processing yet")
                return
                
            # Check if we're already processing something
            if self.is_processing:
                logger.info("Already processing, skipping")
                return
                
            # Process the input
            logger.info(f"Processing after delay: {transcript}")
            self._process_user_input(transcript)
            
        # Start delay thread
        delay_thread = threading.Thread(target=delayed_process)
        delay_thread.daemon = True
        delay_thread.start()
        
    def _handle_interruption(self, transcript: str):
        """Handle user interruption"""
        # Stop current audio
        self.audio_manager.interrupt_playback()
        self.shadow_listening = False
        
        # Wait a moment for audio to stop
        time.sleep(0.2)
        
        # Process the interruption directly
        self._process_user_input(transcript)
        
    def _process_user_input(self, transcript: str):
        """Process user input and generate response"""
        if self.is_processing:
            return
            
        self.is_processing = True
        self.processing_start_time = time.time()  # Record when we start processing
        
        # Add user message to conversation
        self.conversation.add_user_message(transcript)
        
        # Generate and speak response in a separate thread
        response_thread = threading.Thread(target=self._generate_and_speak_response)
        response_thread.daemon = True
        response_thread.start()
        
    def _generate_and_speak_response(self):
        """Generate AI response and speak it"""
        try:
            # Start continuous thinking beep
            self._start_thinking_beep()
            
            # Generate complete response first
            logger.info("Generating AI response...")
            full_response = ""
            for text_chunk in self.conversation.generate_response(streaming=True):
                full_response += text_chunk
                
            logger.info(f"Response: {full_response}")
            
            # Generate audio for complete response
            logger.info("Generating audio...")
            voice_settings = self.current_personality.get("voice_settings", {})
            voice_id = self.current_personality.get("voice_id")
            logger.info(f"Using voice_id for response: {voice_id}")
            
            # Stop thinking beep right before playing audio
            self._thinking_beep_active = False
            time.sleep(0.1)  # Brief pause to stop beep cleanly
            
            # Enable shadow listening for interruption detection
            self.shadow_listening = True
            self.audio_playback_start_time = time.time()  # Record when audio starts
            logger.info("Shadow listening enabled - you can interrupt")
            
            # Play the audio using ElevenLabs streaming function
            logger.info("Playing audio...")
            from elevenlabs import stream
            audio_stream = self.elevenlabs.client.text_to_speech.stream(
                text=full_response,
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                voice_settings=self.elevenlabs._create_voice_settings(voice_settings) if voice_settings else None
            )
            
            # Option 2: process the audio bytes manually and play through our device
            audio_chunks = []
            for chunk in audio_stream:
                if isinstance(chunk, bytes):
                    audio_chunks.append(chunk)
            
            # Combine and play through our audio manager (correct device)
            if audio_chunks:
                complete_audio = b''.join(audio_chunks)
                self.audio_manager.play_audio(complete_audio, format='mp3')
            
            # Wait for playback to complete
            while self.audio_manager.is_playing:
                time.sleep(0.1)
            
            # Disable shadow listening when done
            self.shadow_listening = False
                
        except Exception as e:
            logger.error(f"Error generating response: {e}")
        finally:
            self.is_processing = False
        
            
    def cleanup(self):
        """Clean up resources"""
        self._stop_dial_tone()
        self._end_conversation()
        self.audio_manager.cleanup()
        
        # Turn off relay and cleanup GPIO
        if GPIO_AVAILABLE:
            GPIO.output(RELAY_PIN, GPIO.LOW)  # Ensure relay is off
            GPIO.cleanup()
    
    def _start_connection_beep(self):
        """Start the phone-line beep while connecting"""
        self._beep_active = True
        beep_thread = threading.Thread(target=self._play_connection_beep)
        beep_thread.daemon = True
        beep_thread.start()
    
    def _play_god_greeting(self, greeting: str):
        """Play the god's greeting using standard ElevenLabs streaming"""
        try:
            logger.info("🎭 Streaming divine greeting...")
            voice_settings = self.current_personality.get("voice_settings", {})
            voice_id = self.current_personality.get("voice_id")
            logger.info(f"Using voice_id for {self.current_personality['name']}: {voice_id}")
            
            # Stop connection beep as soon as we start streaming
            self._beep_active = False
            time.sleep(0.1)  # Brief pause to stop beep cleanly
            
            logger.info(f"👑 The god speaks (streaming): {greeting[:50]}...")
            
            # Use ElevenLabs streaming function directly
            from elevenlabs import stream
            audio_stream = self.elevenlabs.client.text_to_speech.stream(
                text=greeting,
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                voice_settings=self.elevenlabs._create_voice_settings(voice_settings) if voice_settings else None
            )
            
            # Option 2: process the audio bytes manually and play through our device
            audio_chunks = []
            for chunk in audio_stream:
                if isinstance(chunk, bytes):
                    audio_chunks.append(chunk)
            
            # Combine and play through our audio manager (correct device)
            if audio_chunks:
                complete_audio = b''.join(audio_chunks)
                self.audio_manager.play_audio(complete_audio, format='mp3')
            
        except Exception as e:
            logger.error(f"Error streaming god greeting: {e}")
            self._beep_active = False
    
    def _play_connection_beep(self):
        """Play phone-line connection beep until god answers"""
        try:
            # Phone-like beep tone (800Hz for 0.2s every 1 second, like phone ringing)
            import numpy as np
            from pydub import AudioSegment
            import io
            
            sample_rate = 16000
            duration = 0.2
            frequency = 800
            
            # Generate phone-like beep tone
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            beep_tone = np.sin(2 * np.pi * frequency * t) * 0.4  # Moderate volume
            
            # Add fade to avoid clicks
            fade_samples = int(0.01 * sample_rate)
            beep_tone[:fade_samples] *= np.linspace(0, 1, fade_samples)
            beep_tone[-fade_samples:] *= np.linspace(1, 0, fade_samples)
            
            # Convert to 16-bit PCM
            beep_audio = (beep_tone * 32767).astype(np.int16)
            
            # Create AudioSegment
            audio_segment = AudioSegment(
                data=beep_audio.tobytes(),
                sample_width=2,
                frame_rate=sample_rate,
                channels=1
            )
            
            # Export as WAV
            wav_buffer = io.BytesIO()
            audio_segment.export(wav_buffer, format="wav")
            wav_buffer.seek(0)
            beep_wav = wav_buffer.read()
            
            logger.info("📞 Playing connection tone while god prepares...")
            
            while hasattr(self, '_beep_active') and self._beep_active:
                if hasattr(self, '_beep_active') and self._beep_active:
                    self.audio_manager.play_audio(beep_wav, format='wav')
                    time.sleep(0.8)  # Pause between beeps (like phone ringing)
                
        except Exception as e:
            logger.error(f"Error playing connection beep: {e}")
    
    def _start_thinking_beep(self):
        """Start continuous thinking beep while AI processes"""
        self._thinking_beep_active = True
        beep_thread = threading.Thread(target=self._play_thinking_beep)
        beep_thread.daemon = True
        beep_thread.start()
    
    def _play_thinking_beep(self):
        """Play continuous calm thinking tone until stopped"""
        try:
            import numpy as np
            from pydub import AudioSegment
            import io
            
            sample_rate = 16000
            duration = 0.8  # Longer, calmer tone
            frequency = 220  # Lower frequency (A3 note)
            
            # Generate calm thinking tone
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            beep_tone = np.sin(2 * np.pi * frequency * t) * 0.25  # Quieter volume
            
            # Add longer fade in/out for smoother sound
            fade_samples = int(0.05 * sample_rate)  # 50ms fade
            beep_tone[:fade_samples] *= np.linspace(0, 1, fade_samples)
            beep_tone[-fade_samples:] *= np.linspace(1, 0, fade_samples)
            
            # Convert to 16-bit PCM
            beep_audio = (beep_tone * 32767).astype(np.int16)
            
            # Create AudioSegment
            audio_segment = AudioSegment(
                data=beep_audio.tobytes(),
                sample_width=2,
                frame_rate=sample_rate,
                channels=1
            )
            
            # Export as WAV
            wav_buffer = io.BytesIO()
            audio_segment.export(wav_buffer, format="wav")
            wav_buffer.seek(0)
            beep_wav = wav_buffer.read()
            
            logger.info("🤔 Playing calm thinking tone while AI processes...")
            
            while hasattr(self, '_thinking_beep_active') and self._thinking_beep_active:
                if hasattr(self, '_thinking_beep_active') and self._thinking_beep_active:
                    self.audio_manager.play_audio(beep_wav, format='wav')
                    time.sleep(1.2)  # Longer pause between tones
                
        except Exception as e:
            logger.error(f"Error playing thinking beep: {e}")
            

def main():
    # Check required environment variables
    required = ["DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY", "OPENAI_API_KEY"]
    missing = [var for var in required if not os.getenv(var)]
    
    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        sys.exit(1)
        
    # Start phone chatbot
    chatbot = PhoneChatbot()
    chatbot.start()
    

if __name__ == "__main__":
    main()