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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Pin definitions
PHONE_HANDLE_PIN = 21     # Phone handle sensor
PULSE_ENABLE_PIN = 23     # Dial pulse enable
PULSE_INPUT_PIN = 24      # Dial pulse count

class PhoneChatbot:
    def __init__(self):
        # Audio components
        self.audio_manager = AudioManager()
        
        # State management
        self.phone_active = False
        self.dial_tone_playing = False
        self.conversation_active = False
        self.current_personality = None
        self.chatbot_instance = None
        
        # Conversation state for interruptions
        self.is_user_speaking = False
        self.last_speech_time = 0
        self.accumulated_transcript = ""
        self.is_generating = False
        self.generated_response = ""
        self.shadow_listening = False
        self.silence_threshold = 1.2
        self.monitoring_active = False
        
        # GPIO state
        self.last_phone_state = True
        self.last_pulse_enable_state = True
        self.last_pulse_state = True
        self.pulse_count = 0
        self.counting_active = False
        
        # Load personality list
        self.personalities = self._load_personalities()
        
        # Initialize GPIO if available
        if GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(PHONE_HANDLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(PULSE_ENABLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(PULSE_INPUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
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
                        self._process_dial(self.pulse_count)
                        
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
                self._process_dial(num)
            elif cmd == 'q':
                break
                
    def _handle_phone_pickup(self):
        """Handle when phone is picked up"""
        logger.info("☎️  Phone picked up!")
        self.phone_active = True
        self._play_dial_tone()
        
    def _handle_phone_hangup(self):
        """Handle when phone is hung up"""
        logger.info("📞 Phone hung up!")
        self.phone_active = False
        self._stop_dial_tone()
        self._end_conversation()
        
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
            while self.dial_tone_playing:
                try:
                    # Load and play dial tone
                    with open('sounds/dial_tone.wav', 'rb') as f:
                        audio_data = f.read()
                    self.audio_manager.play_audio(audio_data, format='wav')
                    
                    # Small gap between loops
                    if self.dial_tone_playing:
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
            
            # Start recording
            self.audio_manager.start_recording(self._handle_audio_chunk)
            
            # Start silence monitoring thread
            self.monitoring_active = True
            silence_thread = threading.Thread(target=self._monitor_silence)
            silence_thread.daemon = True
            silence_thread.start()
            
            # Greet the user
            greeting = f"Hello! This is {self.current_personality['name']} speaking. How can I help you?"
            self._speak_response(greeting)
            
            logger.info(f"✅ Conversation started with {self.current_personality['name']}")
            
        except Exception as e:
            logger.error(f"Error starting conversation: {e}")
            self.conversation_active = False
            
    def _end_conversation(self):
        """End current conversation"""
        if not self.conversation_active:
            return
            
        logger.info("Ending conversation...")
        self.conversation_active = False
        self.monitoring_active = False
        
        # Stop recording
        self.audio_manager.stop_recording()
        
        # Close connections
        if hasattr(self, 'deepgram'):
            self.deepgram.close()
            
        # Clear state
        self.current_personality = None
        self.accumulated_transcript = ""
        self.shadow_listening = False
        
    def _handle_audio_chunk(self, audio_data: bytes):
        """Handle audio from microphone"""
        if self.conversation_active and hasattr(self, 'deepgram'):
            # Always send audio for interruption detection
            if not self.audio_manager.is_playing or self.shadow_listening:
                self.deepgram.send_audio(audio_data)
            
    def _handle_transcript(self, transcript: str, is_final: bool):
        """Handle speech recognition results with interruption support"""
        if not self.conversation_active or not transcript.strip():
            return
            
        # Update speech timing
        self.last_speech_time = time.time()
        self.is_user_speaking = True
        
        # Handle interruption during AI speech
        if self.shadow_listening and self.audio_manager.is_playing:
            if is_final and self._is_intentional_interruption(transcript):
                logger.info(f"🛑 INTERRUPTION detected: {transcript}")
                self._handle_interruption(transcript)
                return
                
        if is_final:
            logger.info(f"User: {transcript}")
            # Accumulate transcripts
            if self.accumulated_transcript:
                self.accumulated_transcript += " " + transcript
            else:
                self.accumulated_transcript = transcript
                
            # Start generating response immediately
            self._start_response_generation(self.accumulated_transcript)
            
    def _is_intentional_interruption(self, transcript: str) -> bool:
        """Check if this is an intentional interruption"""
        transcript = transcript.strip().lower()
        
        # Must be at least 2 words
        words = transcript.split()
        if len(words) < 2:
            return False
            
        # Check for common interruption phrases
        interruption_patterns = [
            'wait', 'stop', 'hold on', 'excuse me', 'sorry', 'actually',
            'let me', 'but', 'however', 'i need', 'i want', 'can you',
            'what about', 'i think', 'no', 'yes but', 'hang on',
            'shut up', 'quiet', 'enough', 'okay stop', 'okay shut'
        ]
        
        for pattern in interruption_patterns:
            if transcript.startswith(pattern):
                return True
                
        # Check for questions or longer statements
        if transcript.startswith(('what', 'why', 'how', 'when', 'where', 'who')) or len(words) >= 4:
            return True
            
        return False
        
    def _handle_interruption(self, transcript: str):
        """Handle user interruption"""
        # Stop current audio
        self.audio_manager.interrupt_playback()
        self.shadow_listening = False
        
        # Clear accumulated transcript and start fresh
        self.accumulated_transcript = transcript
        
        # Wait a moment
        time.sleep(0.2)
        
        # Process the interruption
        self._start_response_generation(transcript)
        
    def _monitor_silence(self):
        """Monitor for silence to trigger responses"""
        while self.monitoring_active:
            time.sleep(0.1)
            
            if self.is_user_speaking and not self.audio_manager.is_playing:
                silence_duration = time.time() - self.last_speech_time
                
                if silence_duration > self.silence_threshold:
                    logger.info(f"🔇 Silence detected ({silence_duration:.1f}s)")
                    self.is_user_speaking = False
                    
                    # Respond with the accumulated transcript
                    if self.accumulated_transcript.strip():
                        self._respond_to_user()
                        
    def _start_response_generation(self, transcript: str):
        """Start generating response in background"""
        if self.is_generating:
            return
            
        self.is_generating = True
        thread = threading.Thread(target=self._generate_response, args=(transcript,))
        thread.daemon = True
        thread.start()
        
    def _generate_response(self, transcript: str):
        """Generate response in background"""
        try:
            # Temporarily add to conversation
            original_count = len(self.conversation.messages)
            self.conversation.add_user_message(transcript)
            
            # Generate response
            response_parts = []
            for chunk in self.conversation.generate_response(streaming=True):
                response_parts.append(chunk)
                
            self.generated_response = ''.join(response_parts)
            
            # Remove temporary message
            if len(self.conversation.messages) > original_count:
                self.conversation.messages.pop()
                
            logger.info(f"Response ready: {self.generated_response[:50]}...")
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
        finally:
            self.is_generating = False
            
    def _respond_to_user(self):
        """Respond to user after silence"""
        if not self.accumulated_transcript.strip():
            return
            
        # Wait for generation if needed
        if self.is_generating:
            timeout = 3
            start = time.time()
            while self.is_generating and time.time() - start < timeout:
                time.sleep(0.1)
                
        if not self.generated_response:
            return
            
        # Add to conversation properly
        self.conversation.add_user_message(self.accumulated_transcript)
        
        # Speak the response
        self._speak_response(self.generated_response)
        
        # Add assistant response to history
        from src.conversation_manager import Message
        self.conversation.messages.append(
            Message(role="assistant", content=self.generated_response)
        )
        
        # Reset state
        self.accumulated_transcript = ""
        self.generated_response = ""
        
    def _speak_response(self, text: str):
        """Speak a response using ElevenLabs with interruption support"""
        try:
            logger.info(f"Speaking: {text}")
            
            # Enable shadow listening for interruptions
            self.shadow_listening = True
            logger.info("👂 Listening for interruptions...")
            
            audio_data = self.elevenlabs.generate_audio(
                text,
                self.current_personality.get("voice_settings", {})
            )
            self.audio_manager.play_audio(audio_data)
            
            # Wait for playback to complete
            while self.audio_manager.is_playing:
                time.sleep(0.1)
                
            # Disable shadow listening
            self.shadow_listening = False
            
        except Exception as e:
            logger.error(f"Error speaking response: {e}")
            self.shadow_listening = False
            
    def cleanup(self):
        """Clean up resources"""
        self._stop_dial_tone()
        self._end_conversation()
        self.audio_manager.cleanup()
        
        if GPIO_AVAILABLE:
            GPIO.cleanup()
            

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