#!/usr/bin/env python3
"""
Text-based version of the chatbot for testing without speech recognition
"""

import os
import sys
import logging
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


class TextVoiceChatbot:
    def __init__(self):
        # Load configuration
        self.config = ConfigLoader()
        
        # Initialize components
        self.audio_manager = AudioManager()
        self.elevenlabs = ElevenLabsClient(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        )
        self.conversation = ConversationManager(
            api_key=os.getenv("OPENAI_API_KEY"),
            personality_config=self.config.personality
        )
        
    def start(self):
        """Start the text-based chatbot with voice output"""
        logger.info("Starting Text-Voice Chatbot")
        logger.info(f"Personality: {self.config.personality['name']}")
        logger.info("Type your messages (or 'quit' to exit)")
        
        try:
            while True:
                # Get text input
                user_input = input("\nYou: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'bye']:
                    break
                    
                if not user_input:
                    continue
                    
                # Process input
                self.conversation.add_user_message(user_input)
                
                # Generate response
                print(f"\n{self.config.personality['name']}: ", end="", flush=True)
                
                full_response = ""
                for text_chunk in self.conversation.generate_response(streaming=True):
                    print(text_chunk, end="", flush=True)
                    full_response += text_chunk
                    
                print()  # New line after response
                
                # Speak the response
                try:
                    audio_data = self.elevenlabs.generate_audio(
                        full_response,
                        self.config.get_voice_settings()
                    )
                    self.audio_manager.play_audio(audio_data)
                except Exception as e:
                    logger.error(f"Error playing audio: {e}")
                    
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()
            
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
    chatbot = TextVoiceChatbot()
    chatbot.start()
    

if __name__ == "__main__":
    main()