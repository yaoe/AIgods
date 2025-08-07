#!/usr/bin/env python3
"""
Ultra-fast predictive voice chatbot that starts generating responses while you speak
"""

import os
import sys
import time
import logging
import threading
import queue
from dotenv import load_dotenv

from deepgram_client import DeepgramClient
from elevenlabs_client import ElevenLabsClient
from conversation_manager import ConversationManager
from audio_manager import AudioManager
from config_loader import ConfigLoader

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PredictiveVoiceChatbot:
    def __init__(self):
        # Load configuration
        self.config = ConfigLoader()
        
        # Initialize components
        self.audio_manager = AudioManager(output_device_index=1)
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
        
        # State
        self.is_listening = False
        self.current_transcript = ""
        self.is_user_speaking = False
        self.last_speech_time = 0
        self.silence_threshold = 1.0  # seconds of silence before responding
        
        # Predictive generation
        self.prediction_thread = None
        self.current_prediction = ""
        self.prediction_ready = False
        self.should_cancel_prediction = False
        
    def start(self):
        """Start the predictive chatbot"""
        logger.info("Starting Predictive Voice Chatbot")
        
        try:
            # Connect to Deepgram
            self.deepgram.connect()
            
            # Start silence detection thread
            silence_thread = threading.Thread(target=self._silence_detector)
            silence_thread.daemon = True
            silence_thread.start()
            
            # Start listening
            self.is_listening = True
            self.audio_manager.start_recording(self.handle_audio_chunk)
            
            logger.info("Ready! I'll start thinking of responses as you speak...")
            
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
        if self.is_listening:
            self.deepgram.send_audio(audio_data)
            
    def handle_transcript(self, transcript: str, is_final: bool):
        """Handle transcript with predictive generation"""
        if not transcript.strip():
            return
            
        self.last_speech_time = time.time()
        self.is_user_speaking = True
        
        if is_final:
            logger.info(f"Heard: {transcript}")
            self.current_transcript = transcript
            
            # Cancel any ongoing prediction if user continues
            if self.prediction_thread and self.prediction_thread.is_alive():
                self.should_cancel_prediction = True
                
            # Start predictive generation immediately
            self.start_predictive_generation(transcript)
        else:
            # Show interim for context
            logger.debug(f"Interim: {transcript}")
            
    def start_predictive_generation(self, transcript: str):
        """Start generating a response predictively"""
        if len(transcript.split()) < 3:  # Too short to predict
            return
            
        self.should_cancel_prediction = False
        self.prediction_ready = False
        
        self.prediction_thread = threading.Thread(
            target=self._generate_prediction,
            args=(transcript,)
        )
        self.prediction_thread.daemon = True
        self.prediction_thread.start()
        
    def _generate_prediction(self, transcript: str):
        """Generate prediction in background"""
        try:
            logger.info(f"Starting to think about: '{transcript}'")
            
            # Add to conversation temporarily
            self.conversation.add_user_message(transcript)
            
            # Generate response
            response_parts = []
            for chunk in self.conversation.generate_response(streaming=True):
                if self.should_cancel_prediction:
                    logger.info("Prediction cancelled - user still speaking")
                    # Remove the temporary message
                    self.conversation.messages.pop()
                    return
                    
                response_parts.append(chunk)
                
            self.current_prediction = ''.join(response_parts)
            self.prediction_ready = True
            logger.info(f"Response ready: {self.current_prediction[:50]}...")
            
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            # Clean up on error
            if self.conversation.messages and self.conversation.messages[-1].role == "user":
                self.conversation.messages.pop()
                
    def _silence_detector(self):
        """Detect silence and trigger response"""
        while self.is_listening:
            time.sleep(0.1)
            
            # Check if user stopped speaking
            if self.is_user_speaking:
                silence_duration = time.time() - self.last_speech_time
                
                if silence_duration > self.silence_threshold:
                    self.is_user_speaking = False
                    
                    # If we have a ready prediction, speak it immediately
                    if self.prediction_ready:
                        self.speak_prediction()
                    # Otherwise wait for current generation
                    elif self.prediction_thread and self.prediction_thread.is_alive():
                        logger.info("Waiting for response to complete...")
                        self.prediction_thread.join(timeout=2.0)
                        if self.prediction_ready:
                            self.speak_prediction()
                            
    def speak_prediction(self):
        """Speak the prepared prediction"""
        try:
            logger.info("Speaking prepared response immediately!")
            
            # Generate audio
            audio_data = self.elevenlabs.generate_audio(
                self.current_prediction,
                self.config.get_voice_settings()
            )
            
            # Play it
            self.audio_manager.play_audio(audio_data)
            
            # Reset prediction state
            self.prediction_ready = False
            self.current_prediction = ""
            
        except Exception as e:
            logger.error(f"Error speaking prediction: {e}")
            
    def cleanup(self):
        """Clean up resources"""
        logger.info("Shutting down...")
        self.is_listening = False
        self.audio_manager.cleanup()
        self.deepgram.close()


def main():
    required_vars = ["DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
        
    chatbot = PredictiveVoiceChatbot()
    chatbot.start()


if __name__ == "__main__":
    main()