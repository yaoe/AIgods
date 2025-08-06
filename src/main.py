#!/usr/bin/env python3

import os
import sys
import time
import logging
import threading
from dotenv import load_dotenv

from deepgram_client import DeepgramClient
from elevenlabs_client import ElevenLabsClient
from conversation_manager import ConversationManager
from audio_manager import AudioManager
from config_loader import ConfigLoader

# Load environment variables at module level
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class VoiceChatbot:
    def __init__(self):
        # Load environment variables from parent directory
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        load_dotenv(env_path)
        
        # Load configuration
        self.config = ConfigLoader()
        
        # Initialize components
        self.audio_manager = AudioManager()
        self.deepgram = DeepgramClient(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            on_transcript=self.handle_transcript
        )
        self.elevenlabs = ElevenLabsClient(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        )
        self.conversation = ConversationManager(
            api_key=os.getenv("OPENAI_API_KEY"),
            personality_config=self.config.personality
        )
        
        # State management
        self.is_listening = False
        self.is_processing = False
        self.current_transcript = ""
        self.last_final_transcript = ""
        self.shadow_listening = False  # For interruption detection
        self.last_transcript_time = 0  # For sentence completion delay
        
    def start(self):
        """Start the voice chatbot"""
        logger.info("Starting Voice Chatbot")
        logger.info(f"Personality: {self.config.personality['name']}")
        
        try:
            # Connect to Deepgram
            self.deepgram.connect()
            
            # Start listening
            self.is_listening = True
            self.audio_manager.start_recording(self.handle_audio_chunk)
            
            logger.info("Ready! Start speaking...")
            
            # Keep running
            while True:
                try:
                    time.sleep(0.1)
                except KeyboardInterrupt:
                    break
                    
        except Exception as e:
            logger.error(f"Error: {e}")
        finally:
            self.cleanup()
            
    def handle_audio_chunk(self, audio_data: bytes):
        """Handle audio chunk from microphone"""
        if (self.is_listening and not self.is_processing) or self.shadow_listening:
            self.deepgram.send_audio(audio_data)
            
    def handle_transcript(self, transcript: str, is_final: bool):
        """Handle transcript from Deepgram"""
        if not transcript.strip():
            return
            
        # Handle interruption during AI speech
        if self.shadow_listening and self.audio_manager.is_playing:
            if is_final and self._is_intentional_interruption(transcript):
                logger.info(f"INTERRUPTION detected: {transcript}")
                self.handle_interruption(transcript)
                return
            
        if is_final:
            logger.info(f"Final transcript: {transcript}")
            self.last_final_transcript = transcript
            self.last_transcript_time = time.time()
            
            # Check if we should process this as a complete utterance
            if self.should_process_utterance(transcript):
                # Add a small delay to ensure the user finished speaking
                self._schedule_delayed_processing(transcript)
        else:
            # Update current transcript for display
            self.current_transcript = transcript
            
    def should_process_utterance(self, transcript: str) -> bool:
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
            # Wait for 0.5 seconds
            time.sleep(0.5)
            
            # Check if there was a more recent transcript (user continued speaking)
            if time.time() - self.last_transcript_time < 0.4:
                logger.info("User still speaking, not processing yet")
                return
                
            # Check if we're already processing something
            if self.is_processing:
                logger.info("Already processing, skipping")
                return
                
            # Process the input
            logger.info(f"Processing after delay: {transcript}")
            self.process_user_input(transcript)
            
        # Start delay thread
        delay_thread = threading.Thread(target=delayed_process)
        delay_thread.daemon = True
        delay_thread.start()
    
    def _is_intentional_interruption(self, transcript: str) -> bool:
        """Determine if this is an intentional interruption"""
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
        
        # Check if transcript starts with common interruption words/phrases
        for pattern in interruption_patterns:
            if transcript.startswith(pattern):
                logger.info(f"Interruption pattern matched: '{pattern}'")
                return True
                
        # Check for question patterns
        if transcript.startswith(('what', 'why', 'how', 'when', 'where', 'who')):
            logger.info("Question interruption detected")
            return True
            
        # Check for strong statements (longer phrases)
        if len(words) >= 4:
            logger.info("Long statement interruption detected")
            return True
            
        logger.info(f"Not considered interruption: '{transcript}' ({len(words)} words)")
        return False
    
    def handle_interruption(self, transcript: str):
        """Handle user interruption during AI speech"""
        logger.info("Handling interruption")
        
        # Stop current audio playback
        self.audio_manager.interrupt_playback()
        
        # Turn off shadow listening
        self.shadow_listening = False
        
        # Wait a moment for audio to stop
        time.sleep(0.2)
        
        # No acknowledgment - just process the interruption directly
        # This makes it feel more natural and responsive
        self.process_user_input(transcript)
        
    def process_user_input(self, transcript: str):
        """Process user input and generate response"""
        if self.is_processing:
            return
            
        self.is_processing = True
        
        # Add user message to conversation
        self.conversation.add_user_message(transcript)
        
        # Generate and speak response in a separate thread
        response_thread = threading.Thread(target=self._generate_and_speak_response)
        response_thread.daemon = True
        response_thread.start()
        
    def _generate_and_speak_response(self):
        """Generate AI response and speak it"""
        try:
            # Generate complete response first
            logger.info("Generating AI response...")
            full_response = ""
            for text_chunk in self.conversation.generate_response(streaming=True):
                full_response += text_chunk
                
            logger.info(f"Response: {full_response}")
            
            # Generate audio for complete response
            logger.info("Generating audio...")
            audio_data = self.elevenlabs.generate_audio(
                full_response,
                self.config.get_voice_settings()
            )
            
            # Enable shadow listening for interruption detection
            self.shadow_listening = True
            logger.info("Shadow listening enabled - you can interrupt")
            
            # Play the audio
            logger.info("Playing audio...")
            self.audio_manager.play_audio(audio_data)
            
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
        logger.info("Shutting down...")
        self.is_listening = False
        self.audio_manager.cleanup()
        self.deepgram.close()
        

def main():
    """Main entry point"""
    # Debug: Show current directory and .env status
    logger.info(f"Current directory: {os.getcwd()}")
    logger.info(f".env file exists: {os.path.exists('.env')}")
    
    # Check for required environment variables
    required_vars = ["DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please create a .env file with your API keys (see .env.example)")
        # Debug: Try to show what's in the environment
        for var in required_vars:
            value = os.getenv(var)
            if value:
                logger.info(f"{var}: Found (length: {len(value)})")
            else:
                logger.info(f"{var}: Not found")
        sys.exit(1)
        
    # Create and start chatbot
    chatbot = VoiceChatbot()
    chatbot.start()
    

if __name__ == "__main__":
    main()