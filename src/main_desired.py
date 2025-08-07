#!/usr/bin/env python3
"""
Voice chatbot with the exact desired mechanism:
1. Listen to user speech
2. Generate possible responses while user speaks (based on partial transcripts)
3. When user stops speaking, send final response to ElevenLabs
4. Stream ElevenLabs audio as it arrives
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
    level=logging.DEBUG,  # Enable debug logging to see silence detection
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Reduce noise from other modules
logging.getLogger("websocket").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class DesiredVoiceChatbot:
    def __init__(self):
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
        self.is_user_speaking = False
        self.last_speech_time = 0
        self.silence_threshold = 1.2  # seconds of silence before responding
        
        # Response generation
        self.current_transcript = ""
        self.accumulated_transcript = ""  # Build up full sentence
        self.is_generating = False
        self.generated_response = ""
        self.generation_thread = None
        
        # Audio streaming
        self.is_playing_audio = False
        
    def start(self):
        """Start the voice chatbot"""
        logger.info("Starting Desired Voice Chatbot")
        logger.info("Mechanism: Generate while listening, respond when silent, stream audio")
        
        try:
            # Connect to Deepgram
            self.deepgram.connect()
            
            # Start silence detection
            silence_thread = threading.Thread(target=self._monitor_silence)
            silence_thread.daemon = True
            silence_thread.start()
            
            # Start listening
            self.is_listening = True
            self.audio_manager.start_recording(self.handle_audio_chunk)
            
            logger.info("Ready! Start speaking...")
            
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
        if self.is_listening and not self.is_playing_audio:
            self.deepgram.send_audio(audio_data)
            
    def handle_transcript(self, transcript: str, is_final: bool):
        """Handle transcripts and trigger predictive generation"""
        if not transcript.strip():
            return
            
        # Update speech timing
        self.last_speech_time = time.time()
        self.is_user_speaking = True
        
        if is_final:
            logger.info(f"Final: {transcript}")
            # Accumulate final transcripts to build full sentence
            if self.accumulated_transcript:
                self.accumulated_transcript += " " + transcript
            else:
                self.accumulated_transcript = transcript
                
            self.current_transcript = self.accumulated_transcript
            logger.info(f"📝 Accumulated so far: '{self.accumulated_transcript}'")
            
            # Start generating response based on accumulated transcript
            self.start_predictive_generation(self.accumulated_transcript)
        else:
            # Show partial transcript
            logger.debug(f"Partial: {transcript}")
            
            # Generate based on partial transcript if it's substantial
            working_transcript = self.accumulated_transcript + " " + transcript if self.accumulated_transcript else transcript
            if len(working_transcript.split()) >= 5:  # At least 5 words
                self.start_predictive_generation(working_transcript)
                
    def start_predictive_generation(self, transcript: str):
        """Start generating response based on current transcript"""
        # Cancel any existing generation
        if self.generation_thread and self.generation_thread.is_alive():
            logger.debug("Cancelling previous generation for new input")
            # Let it finish naturally, we'll just override the result
            
        # Start new generation
        self.is_generating = True
        self.generation_thread = threading.Thread(
            target=self._generate_response,
            args=(transcript,)
        )
        self.generation_thread.daemon = True
        self.generation_thread.start()
        
    def _generate_response(self, transcript: str):
        """Generate response in background while user might still be speaking"""
        try:
            logger.info(f"🧠 Generating response for: '{transcript[:30]}...'")
            
            # Temporarily add user message to get context
            original_message_count = len(self.conversation.messages)
            self.conversation.add_user_message(transcript)
            
            # Generate complete response
            response_parts = []
            for chunk in self.conversation.generate_response(streaming=True):
                response_parts.append(chunk)
                
            self.generated_response = ''.join(response_parts)
            
            # Remove the temporary message (we'll add it properly when user stops speaking)
            if len(self.conversation.messages) > original_message_count:
                self.conversation.messages.pop()
                
            logger.info(f"✅ Response ready: '{self.generated_response[:50]}...'")
            
        except Exception as e:
            logger.error(f"Response generation error: {e}")
        finally:
            self.is_generating = False
            
    def _monitor_silence(self):
        """Monitor for silence and trigger response when user stops speaking"""
        while self.is_listening:
            time.sleep(0.1)
            
            if self.is_user_speaking and not self.is_playing_audio:
                silence_duration = time.time() - self.last_speech_time
                
                # Debug: Show silence duration every second
                if int(silence_duration) != int(silence_duration - 0.1):
                    logger.debug(f"⏱️  Silence: {silence_duration:.1f}s (threshold: {self.silence_threshold}s)")
                
                if silence_duration > self.silence_threshold:
                    logger.info(f"🔇 Silence detected ({silence_duration:.1f}s) - user finished speaking")
                    self.is_user_speaking = False
                    
                    # User stopped speaking - now respond with generated response
                    self.respond_to_user()
                    
    def respond_to_user(self):
        """Respond to user with the pre-generated response"""
        if not self.current_transcript.strip():
            return
            
        # Wait a moment for generation to complete if still in progress
        if self.is_generating and self.generation_thread:
            logger.info("⏳ Waiting for response generation to complete...")
            self.generation_thread.join(timeout=3.0)
            
        if not self.generated_response:
            logger.warning("No response generated, skipping")
            return
            
        # Now properly add the user message to conversation history
        self.conversation.add_user_message(self.current_transcript)
        
        logger.info(f"🎯 Final response: {self.generated_response}")
        
        # Send to ElevenLabs and stream the result
        self.stream_response_audio(self.generated_response)
        
        # Add AI response to conversation history
        from conversation_manager import Message
        self.conversation.messages.append(
            Message(role="assistant", content=self.generated_response)
        )
        
        # Reset for next interaction
        self.current_transcript = ""
        self.accumulated_transcript = ""  # Reset accumulated transcript
        self.generated_response = ""
        
    def stream_response_audio(self, response_text: str):
        """Send response to ElevenLabs and stream the audio"""
        try:
            self.is_playing_audio = True
            logger.info("🔊 Streaming audio from ElevenLabs...")
            
            # Stream audio chunks as they arrive from ElevenLabs
            def audio_callback(chunk: bytes):
                # Play this chunk immediately
                if chunk:
                    # Create a temporary audio player for this chunk
                    threading.Thread(
                        target=self._play_audio_chunk, 
                        args=(chunk,),
                        daemon=True
                    ).start()
            
            # Generate audio and stream it
            for chunk in self.elevenlabs.stream_text(response_text, self.config.get_voice_settings()):
                audio_callback(chunk)
                
        except Exception as e:
            logger.error(f"Audio streaming error: {e}")
        finally:
            # Wait a moment for final chunks to play
            time.sleep(0.5)
            self.is_playing_audio = False
            logger.info("🔇 Audio streaming complete")
            
    def _play_audio_chunk(self, chunk: bytes):
        """Play a single audio chunk"""
        try:
            self.audio_manager.play_audio(chunk)
        except Exception as e:
            logger.error(f"Chunk playback error: {e}")
            
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
        logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
        
    chatbot = DesiredVoiceChatbot()
    chatbot.start()


if __name__ == "__main__":
    main()