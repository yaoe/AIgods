#!/usr/bin/env python3
"""
Real-time streaming voice chatbot with predictive responses
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
from conversation_manager import GeminiConversationManager
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


class StreamingVoiceChatbot:
    def __init__(self):
        # Load configuration
        self.config = ConfigLoader()
        
        # Initialize components
        self.audio_manager = AudioManager()  # Use default device for now
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
        self.is_listening = False
        self.is_processing = False
        self.current_transcript = ""
        self.accumulated_transcript = ""
        self.last_final_time = 0
        
        # Streaming queues
        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        
        # Threads
        self.tts_thread = None
        self.playback_thread = None
        
    def start(self):
        """Start the streaming voice chatbot"""
        logger.info("Starting Streaming Voice Chatbot")
        logger.info(f"Personality: {self.config.personality['name']}")
        
        try:
            # Connect to Deepgram
            self.deepgram.connect()
            
            # Start streaming threads
            self.start_streaming_threads()
            
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
        if self.is_listening:
            self.deepgram.send_audio(audio_data)
            
    def handle_transcript(self, transcript: str, is_final: bool):
        """Handle transcript from Deepgram"""
        if not transcript.strip():
            return
            
        current_time = time.time()
        
        if is_final:
            logger.info(f"Final: {transcript}")
            self.accumulated_transcript += " " + transcript
            self.last_final_time = current_time
            
            # Start processing immediately on sentence boundaries
            if self._is_sentence_boundary(self.accumulated_transcript):
                self.process_accumulated_transcript()
        else:
            # Show interim results
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
        if self.is_processing or not self.accumulated_transcript.strip():
            return
            
        transcript = self.accumulated_transcript.strip()
        self.accumulated_transcript = ""
        
        # Don't process very short utterances
        if len(transcript.split()) < 2:
            return
            
        logger.info(f"Processing: {transcript}")
        self.is_processing = True
        
        # Start generating response in background
        response_thread = threading.Thread(
            target=self._generate_streaming_response,
            args=(transcript,)
        )
        response_thread.daemon = True
        response_thread.start()
        
    def _generate_streaming_response(self, transcript: str):
        """Generate and stream response"""
        try:
            # Add to conversation
            self.conversation.add_user_message(transcript)
            
            # Stream response text
            sentence_buffer = ""
            for text_chunk in self.conversation.generate_response(streaming=True):
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
                
        except Exception as e:
            logger.error(f"Error generating response: {e}")
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
        """Worker thread for text-to-speech conversion"""
        while True:
            try:
                # Get text from queue
                text = self.text_queue.get(timeout=1)
                
                if text is None:  # Shutdown signal
                    break
                    
                # Generate audio and queue it
                logger.info(f"Generating TTS for: {text[:50]}...")
                audio_data = self.elevenlabs.generate_audio(
                    text,
                    self.config.get_voice_settings()
                )
                
                self.audio_queue.put(audio_data)
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"TTS error: {e}")
                
    def _playback_worker(self):
        """Worker thread for audio playback"""
        while True:
            try:
                # Get audio from queue
                audio_data = self.audio_queue.get(timeout=1)
                
                if audio_data is None:  # Shutdown signal
                    break
                    
                # Play audio
                logger.info("Playing audio chunk...")
                self.audio_manager.play_audio(audio_data)
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Playback error: {e}")
                
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