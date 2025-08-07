#!/usr/bin/env python3
"""
Keyboard input version - for systems without microphone
"""

import os
import sys
import logging
import threading
import queue
from dotenv import load_dotenv

from elevenlabs_client import ElevenLabsClient
from conversation_manager import ConversationManager
from audio_manager import AudioManager
from config_loader import ConfigLoader

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class KeyboardVoiceChatbot:
    def __init__(self):
        # Load configuration
        self.config = ConfigLoader()
        
        # Initialize components
        # Use device 1 for Raspberry Pi headphones
        self.audio_manager = AudioManager(output_device_index=1)
        self.elevenlabs = ElevenLabsClient(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        )
        self.conversation = ConversationManager(
            api_key=os.getenv("OPENAI_API_KEY"),
            personality_config=self.config.personality
        )
        
        self.is_processing = False
        
    def start(self):
        """Start the keyboard-input chatbot with voice output"""
        logger.info("Starting Keyboard-Voice Chatbot")
        logger.info(f"Personality: {self.config.personality['name']}")
        logger.info("Type your messages (or 'quit' to exit)")
        logger.info("The AI will respond with both text and voice")
        
        try:
            while True:
                # Get text input
                try:
                    user_input = input("\nYou: ").strip()
                except KeyboardInterrupt:
                    break
                
                if user_input.lower() in ['quit', 'exit', 'bye']:
                    break
                    
                if not user_input:
                    continue
                
                # Process input
                self.process_user_input(user_input)
                
                # Wait for response to complete
                while self.is_processing:
                    import time
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Error: {e}")
        finally:
            self.cleanup()
            
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
            
            # Print response as it streams
            print(f"\n{self.config.personality['name']}: ", end="", flush=True)
            
            for text_chunk in self.conversation.generate_response(streaming=True):
                full_response += text_chunk
                print(text_chunk, end="", flush=True)
                
            print()  # New line after response
            
            # Generate audio for complete response
            logger.info("Generating audio...")
            audio_data = self.elevenlabs.generate_audio(
                full_response,
                self.config.get_voice_settings()
            )
            
            # Play the audio
            logger.info("Playing audio...")
            self.audio_manager.play_audio(audio_data)
            
            # Wait for playback to complete
            while self.audio_manager.is_playing:
                import time
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Error generating response: {e}")
        finally:
            self.is_processing = False
            
    def cleanup(self):
        """Clean up resources"""
        logger.info("Shutting down...")
        self.audio_manager.cleanup()
        

def main():
    """Main entry point"""
    # Check for required environment variables
    required_vars = ["ELEVENLABS_API_KEY", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
        
    # Create and start chatbot
    chatbot = KeyboardVoiceChatbot()
    chatbot.start()
    

if __name__ == "__main__":
    main()