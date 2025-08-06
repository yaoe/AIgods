import json
import websocket
import threading
import queue
import time
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)


class DeepgramClient:
    def __init__(self, api_key: str, on_transcript: Callable[[str, bool], None]):
        self.api_key = api_key
        self.on_transcript = on_transcript
        self.ws: Optional[websocket.WebSocketApp] = None
        self.audio_queue = queue.Queue()
        self.is_connected = False
        self.keep_alive_thread: Optional[threading.Thread] = None
        
    def connect(self):
        url = "wss://api.deepgram.com/v1/listen"
        params = {
            "encoding": "linear16",
            "sample_rate": "16000",
            "channels": "1",
            "model": "nova-2",
            "language": "en",
            "punctuate": "true",
            "interim_results": "true",
            "utterance_end_ms": "1000",
            "vad_events": "true"
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{query_string}"
        
        self.ws = websocket.WebSocketApp(
            full_url,
            header={
                "Authorization": f"Token {self.api_key}"
            },
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )
        
        # Start WebSocket in separate thread
        ws_thread = threading.Thread(target=self.ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()
        
        # Wait for connection
        timeout = 5
        start = time.time()
        while not self.is_connected and time.time() - start < timeout:
            time.sleep(0.1)
            
        if not self.is_connected:
            raise Exception("Failed to connect to Deepgram")
            
    def _on_open(self, ws):
        logger.info("Connected to Deepgram")
        self.is_connected = True
        
        # Start keep-alive thread
        self.keep_alive_thread = threading.Thread(target=self._keep_alive)
        self.keep_alive_thread.daemon = True
        self.keep_alive_thread.start()
        
        # Start audio sender thread
        audio_thread = threading.Thread(target=self._send_audio)
        audio_thread.daemon = True
        audio_thread.start()
        
    def _on_message(self, ws, message):
        try:
            response = json.loads(message)
            
            if response.get("type") == "Results":
                alternatives = response.get("channel", {}).get("alternatives", [])
                if alternatives:
                    transcript = alternatives[0].get("transcript", "")
                    is_final = response.get("is_final", False)
                    
                    if transcript.strip():
                        self.on_transcript(transcript, is_final)
                        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
    def _on_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
        
    def _on_close(self, ws, close_status_code, close_msg):
        logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.is_connected = False
        
    def _keep_alive(self):
        while self.is_connected:
            try:
                self.ws.send(json.dumps({"type": "KeepAlive"}))
                time.sleep(10)
            except Exception as e:
                logger.error(f"Keep-alive error: {e}")
                break
                
    def _send_audio(self):
        while self.is_connected:
            try:
                audio_data = self.audio_queue.get(timeout=0.1)
                if self.ws and self.is_connected:
                    self.ws.send(audio_data, opcode=websocket.ABNF.OPCODE_BINARY)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error sending audio: {e}")
                
    def send_audio(self, audio_data: bytes):
        if self.is_connected:
            self.audio_queue.put(audio_data)
            
    def close(self):
        self.is_connected = False
        if self.ws:
            self.ws.close()