import asyncio
import threading
import queue
import time
import logging
from typing import Callable, Optional
from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents
from deepgram.clients.live.v1 import LiveOptions

logger = logging.getLogger(__name__)


class DeepgramClientV3:
    def __init__(self, api_key: str, on_transcript: Callable[[str, bool], None]):
        self.api_key = api_key
        self.on_transcript = on_transcript
        self.dg_connection = None
        self.is_connected = False
        self.audio_queue = queue.Queue()
        self.loop = None
        self.thread = None
        
    def connect(self):
        """Connect to Deepgram using v3 SDK"""
        # Start async event loop in separate thread
        self.thread = threading.Thread(target=self._run_async_loop)
        self.thread.daemon = True
        self.thread.start()
        
        # Wait for connection
        timeout = 5
        start = time.time()
        while not self.is_connected and time.time() - start < timeout:
            time.sleep(0.1)
            
        if not self.is_connected:
            raise Exception("Failed to connect to Deepgram")
            
    def _run_async_loop(self):
        """Run the async event loop in a separate thread"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._async_connect())
        
    async def _async_connect(self):
        """Async connection to Deepgram"""
        try:
            # Create Deepgram client
            config = DeepgramClientOptions(options={"keepalive": "true"})
            self.deepgram = DeepgramClient(self.api_key, config)
            
            # Create live transcription connection
            self.dg_connection = self.deepgram.listen.live.v("1")
            
            # Configure callbacks
            self.dg_connection.on(LiveTranscriptionEvents.Open, self._on_open)
            self.dg_connection.on(LiveTranscriptionEvents.Transcript, self._on_message)
            self.dg_connection.on(LiveTranscriptionEvents.Error, self._on_error)
            self.dg_connection.on(LiveTranscriptionEvents.Close, self._on_close)
            
            # Set options
            options = LiveOptions(
                model="nova-2",
                language="en-US",
                encoding="linear16",
                sample_rate=16000,
                channels=1,
                punctuate=True,
                interim_results=True,
                utterance_end_ms=1000,
                vad_events=True
            )
            
            # Start the connection
            await self.dg_connection.start(options)
            
            # Start sending audio
            await self._send_audio_loop()
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.is_connected = False
            
    async def _send_audio_loop(self):
        """Send audio data to Deepgram"""
        while self.is_connected:
            try:
                # Get audio from queue (non-blocking with timeout)
                audio_data = await asyncio.get_event_loop().run_in_executor(
                    None, self.audio_queue.get, True, 0.1
                )
                if self.dg_connection:
                    self.dg_connection.send(audio_data)
            except queue.Empty:
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Error sending audio: {e}")
                
    def _on_open(self, *args, **kwargs):
        logger.info("Connected to Deepgram")
        self.is_connected = True
        
    def _on_message(self, *args, **kwargs):
        try:
            result = kwargs.get("result", {})
            
            if result.get("type") == "Results":
                alternatives = result.get("channel", {}).get("alternatives", [])
                if alternatives:
                    transcript = alternatives[0].get("transcript", "")
                    is_final = result.get("is_final", False)
                    
                    if transcript.strip():
                        # Call the callback in the main thread
                        self.on_transcript(transcript, is_final)
                        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
    def _on_error(self, *args, **kwargs):
        error = kwargs.get("error", "Unknown error")
        logger.error(f"Deepgram error: {error}")
        
    def _on_close(self, *args, **kwargs):
        logger.info("Deepgram connection closed")
        self.is_connected = False
        
    def send_audio(self, audio_data: bytes):
        """Send audio data to Deepgram"""
        if self.is_connected:
            self.audio_queue.put(audio_data)
            
    def close(self):
        """Close the connection"""
        self.is_connected = False
        if self.dg_connection:
            asyncio.run_coroutine_threadsafe(
                self.dg_connection.finish(), 
                self.loop
            ).result()
        if self.loop:
            self.loop.call_soon_threadsafe(self.loop.stop)