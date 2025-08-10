#!/usr/bin/env python3
"""
Voice chatbot with configurable audio devices
Usage:
    python main_configurable_audio.py
    python main_configurable_audio.py --input-device 2 --output-device 1
    
Or set environment variables:
    export AUDIO_INPUT_DEVICE=2
    export AUDIO_OUTPUT_DEVICE=1
"""

import os
import sys
import time
import logging
import threading
import argparse
from dotenv import load_dotenv

from deepgram_client import DeepgramClient
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


class VoiceChatbot:
    def __init__(self, input_device_index=None, output_device_index=None):
        # Load configuration
        self.config = ConfigLoader()
        
        # Determine audio device indices
        # Priority: function args > env vars > config file > defaults
        if input_device_index is None:
            input_device_index = os.getenv('AUDIO_INPUT_DEVICE')
            if input_device_index is not None:
                input_device_index = int(input_device_index)
        
        if output_device_index is None:
            output_device_index = os.getenv('AUDIO_OUTPUT_DEVICE')
            if output_device_index is not None:
                output_device_index = int(output_device_index)
            else:
                # Check config file (backwards compatibility)
                output_device_index = 1  # Default for Raspberry Pi
        
        logger.info(f"Audio configuration:")
        logger.info(f"  Input device index: {input_device_index} (None = system default)")
        logger.info(f"  Output device index: {output_device_index} (None = system default)")
        
        # Initialize components
        self.audio_manager = AudioManager(
            input_device_index=input_device_index,
            output_device_index=output_device_index
        )
        
        # List available devices for user reference
        self._list_audio_devices()
        
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
        self.shadow_listening = False
        self.last_transcript_time = 0
    
    def _list_audio_devices(self):
        """List available audio devices for reference"""
        logger.info("Available audio devices:")
        
        input_devices = self.audio_manager.get_input_devices()
        if input_devices:
            logger.info("  Input devices:")
            for device in input_devices:
                logger.info(f"    [{device['index']}] {device['name']}")
        
        output_devices = self.audio_manager.get_output_devices()
        if output_devices:
            logger.info("  Output devices:")
            for device in output_devices:
                logger.info(f"    [{device['index']}] {device['name']}")
        
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
                self._schedule_delayed_processing(transcript)
        else:
            self.current_transcript = transcript
            
    def should_process_utterance(self, transcript: str) -> bool:
        """Determine if we should process the utterance"""
        transcript = transcript.strip()
        
        if transcript.endswith(('?', '.', '!')) or len(transcript.split()) > 3:
            return True
            
        return False
    
    def _schedule_delayed_processing(self, transcript: str):
        """Schedule processing with a delay to ensure sentence completion"""
        def delayed_process():
            time.sleep(0.5)
            
            if time.time() - self.last_transcript_time < 0.4:
                logger.info("User still speaking, not processing yet")
                return
                
            if self.is_processing:
                logger.info("Already processing, skipping")
                return
                
            logger.info(f"Processing after delay: {transcript}")
            self.process_user_input(transcript)
            
        delay_thread = threading.Thread(target=delayed_process)
        delay_thread.daemon = True
        delay_thread.start()
    
    def _is_intentional_interruption(self, transcript: str) -> bool:
        """Determine if this is an intentional interruption"""
        transcript = transcript.strip().lower()
        
        words = transcript.split()
        if len(words) < 2:
            return False
            
        interruption_patterns = [
            'wait', 'stop', 'hold on', 'excuse me', 'sorry', 'actually',
            'let me', 'but', 'however', 'i need', 'i want', 'can you',
            'what about', 'i think', 'no', 'yes but', 'hang on',
            'shut up', 'quiet', 'enough', 'okay stop', 'okay shut'
        ]
        
        for pattern in interruption_patterns:
            if transcript.startswith(pattern):
                logger.info(f"Interruption pattern matched: '{pattern}'")
                return True
                
        if transcript.startswith(('what', 'why', 'how', 'when', 'where', 'who')):
            logger.info("Question interruption detected")
            return True
            
        if len(words) >= 4:
            logger.info("Long statement interruption detected")
            return True
            
        logger.info(f"Not considered interruption: '{transcript}' ({len(words)} words)")
        return False
    
    def handle_interruption(self, transcript: str):
        """Handle user interruption during AI speech"""
        logger.info("Handling interruption")
        
        self.audio_manager.interrupt_playback()
        self.shadow_listening = False
        time.sleep(0.2)
        self.process_user_input(transcript)
        
    def process_user_input(self, transcript: str):
        """Process user input and generate response"""
        if self.is_processing:
            return
            
        self.is_processing = True
        self.conversation.add_user_message(transcript)
        
        response_thread = threading.Thread(target=self._generate_and_speak_response)
        response_thread.daemon = True
        response_thread.start()
        
    def _generate_and_speak_response(self):
        """Generate AI response and speak it"""
        try:
            logger.info("Generating AI response...")
            full_response = ""
            for text_chunk in self.conversation.generate_response(streaming=True):
                full_response += text_chunk
                
            logger.info(f"Response: {full_response}")
            
            logger.info("Generating audio...")
            audio_data = self.elevenlabs.generate_audio(
                full_response,
                self.config.get_voice_settings()
            )
            
            self.shadow_listening = True
            logger.info("Shadow listening enabled - you can interrupt")
            
            logger.info("Playing audio...")
            self.audio_manager.play_audio(audio_data)
            
            while self.audio_manager.is_playing:
                time.sleep(0.1)
            
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
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(description='Voice chatbot with configurable audio devices')
    parser.add_argument('--input-device', type=int, help='Audio input device index')
    parser.add_argument('--output-device', type=int, help='Audio output device index')
    parser.add_argument('--list-devices', action='store_true', help='List available audio devices and exit')
    
    args = parser.parse_args()
    
    # If just listing devices
    if args.list_devices:
        from list_audio_devices import list_audio_devices
        list_audio_devices()
        return
    
    # Check for required environment variables
    required_vars = ["DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please create a .env file with your API keys")
        sys.exit(1)
        
    # Create and start chatbot
    chatbot = VoiceChatbot(
        input_device_index=args.input_device,
        output_device_index=args.output_device
    )
    chatbot.start()


if __name__ == "__main__":
    main()