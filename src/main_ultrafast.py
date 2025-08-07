#!/usr/bin/env python3
"""
Ultra-fast voice chatbot with:
- Real-time OpenAI response streaming
- Real-time ElevenLabs TTS streaming  
- Predictive response generation while user speaks
- Near-zero latency responses
"""

import os
import sys
import time
import logging
import threading
import queue
from dotenv import load_dotenv

from deepgram_client import DeepgramClient
from elevenlabs_streaming import ElevenLabsStreamingClient, RealTimeAudioPlayer
from conversation_manager import ConversationManager
from audio_manager import AudioManager
from config_loader import ConfigLoader

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UltraFastVoiceChatbot:
    def __init__(self):
        # Load configuration
        self.config = ConfigLoader()
        
        # Initialize components  
        self.audio_manager = AudioManager(output_device_index=1)
        self.deepgram = DeepgramClient(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            on_transcript=self.handle_transcript
        )
        self.elevenlabs = ElevenLabsStreamingClient(
            api_key=os.getenv("ELEVENLABS_API_KEY"),
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        )
        self.conversation = ConversationManager(
            api_key=os.getenv("OPENAI_API_KEY"),
            personality_config=self.config.personality
        )
        
        # Real-time audio player
        self.audio_player = RealTimeAudioPlayer(self.audio_manager)
        
        # State
        self.is_listening = False
        self.current_transcript = ""
        self.is_user_speaking = False
        self.last_speech_time = 0
        self.response_active = False
        
        # Prediction state
        self.prediction_ready = False
        self.response_generator = None
        self.should_cancel = False
        
    def start(self):
        """Start the ultra-fast chatbot"""
        logger.info("Starting Ultra-Fast Voice Chatbot")
        logger.info("Features: Real-time streaming, predictive responses, near-zero latency")
        
        try:
            # Connect to Deepgram
            self.deepgram.connect()
            
            # Start silence monitoring
            silence_thread = threading.Thread(target=self._monitor_silence)
            silence_thread.daemon = True
            silence_thread.start()
            
            # Start listening
            self.is_listening = True
            self.audio_manager.start_recording(self.handle_audio_chunk)
            
            logger.info("Ready! I'll respond instantly when you pause...")
            
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
        """Handle audio from microphone"""
        if self.is_listening:
            self.deepgram.send_audio(audio_data)
            
    def handle_transcript(self, transcript: str, is_final: bool):
        """Handle transcripts with ultra-fast processing"""
        if not transcript.strip():
            return
            
        self.last_speech_time = time.time()
        self.is_user_speaking = True
        
        if is_final:
            logger.info(f"You: {transcript}")
            self.current_transcript = transcript
            
            # Cancel any existing prediction
            self.should_cancel = True
            time.sleep(0.05)  # Brief pause to cancel
            
            # Start new prediction immediately
            self.start_ultra_fast_prediction(transcript)
            
    def start_ultra_fast_prediction(self, transcript: str):
        """Start generating response while user might still be speaking"""
        if len(transcript.split()) < 2:
            return
            
        logger.info("🚀 Starting ultra-fast prediction...")
        
        self.should_cancel = False
        self.prediction_ready = False
        
        # Start prediction in background
        prediction_thread = threading.Thread(
            target=self._generate_ultra_fast_response,
            args=(transcript,)
        )
        prediction_thread.daemon = True
        prediction_thread.start()
        
    def _generate_ultra_fast_response(self, transcript: str):
        """Generate response with immediate streaming"""
        try:
            # Add to conversation
            self.conversation.add_user_message(transcript)
            
            # Create text generator for streaming
            def text_generator():
                for chunk in self.conversation.generate_response(streaming=True):
                    if self.should_cancel:
                        logger.info("❌ Response cancelled")
                        return
                    yield chunk
                    
            self.response_generator = text_generator()
            self.prediction_ready = True
            logger.info("⚡ Response ready for instant streaming")
            
        except Exception as e:
            logger.error(f"Ultra-fast generation error: {e}")
            
    def _monitor_silence(self):
        """Monitor for silence and trigger instant response"""
        silence_threshold = 0.8  # Very fast response
        
        while self.is_listening:
            time.sleep(0.05)  # Check every 50ms for ultra-responsiveness
            
            if self.is_user_speaking and not self.response_active:
                silence_duration = time.time() - self.last_speech_time
                
                if silence_duration > silence_threshold:
                    self.is_user_speaking = False
                    
                    if self.prediction_ready and self.response_generator:
                        logger.info("🎯 Instant response triggered!")
                        self.trigger_instant_response()
                        
    def trigger_instant_response(self):
        """Trigger instant streaming response"""
        if self.response_active:
            return
            
        self.response_active = True
        
        try:
            # Start real-time audio player
            self.audio_player.start_playback()
            
            # Stream TTS in real-time as OpenAI generates text
            logger.info("🔊 Starting real-time speech...")
            
            stream_thread = self.elevenlabs.stream_text_realtime(
                text_generator=self.response_generator,
                audio_callback=self.audio_player.add_audio_chunk,
                voice_settings=self.config.get_voice_settings()
            )
            
            # Wait for streaming to complete
            stream_thread.join()
            
            # Wait for audio to finish
            time.sleep(0.5)
            self.audio_player.stop()
            
        except Exception as e:
            logger.error(f"Instant response error: {e}")
        finally:
            self.response_active = False
            self.prediction_ready = False
            self.response_generator = None
            
    def cleanup(self):
        """Clean up resources"""
        logger.info("Shutting down ultra-fast chatbot...")
        self.is_listening = False
        self.should_cancel = True
        
        if hasattr(self, 'audio_player'):
            self.audio_player.stop()
            
        self.audio_manager.cleanup()
        self.deepgram.close()


def main():
    required_vars = ["DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY", "OPENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
        
    logger.info("🚀 Launching Ultra-Fast Voice AI...")
    chatbot = UltraFastVoiceChatbot()
    chatbot.start()


if __name__ == "__main__":
    main()