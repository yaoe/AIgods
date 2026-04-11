import asyncio
import json
import threading
import queue
from typing import Callable, Optional
import logging

try:
    import websockets
except ImportError:
    websockets = None

logger = logging.getLogger(__name__)

# Smart-turn servers (MacBook first, Glitchbox fallback)
SERVERS = [
    ("MacBook",   "ws://100.67.155.96:8200/v1/listen"),
    ("Glitchbox", "ws://100.79.41.86:8200/v1/listen"),
]


class SmartTurnClient:
    """
    Speech recognition client using smart-turn servers.
    Drop-in replacement for DeepgramClient with same interface:
      - connect(), send_audio(bytes), close()
      - Calls on_transcript(text, is_final) callback
    """

    def __init__(self, on_transcript: Callable[[str, bool], None]):
        self.on_transcript = on_transcript
        self.is_connected = False
        self.audio_queue: queue.Queue = queue.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ws = None
        self._server_name = None

    def connect(self):
        """Connect to first available smart-turn server (blocking)."""
        if websockets is None:
            raise ImportError("Install websockets: pip install websockets")

        ready = threading.Event()
        error_holder = [None]

        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._connect_and_stream(ready, error_holder))

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()

        # Wait up to 10s for connection
        if not ready.wait(timeout=10):
            raise Exception("Failed to connect to any smart-turn server")
        if error_holder[0]:
            raise error_holder[0]

    async def _connect_and_stream(self, ready: threading.Event, error_holder: list):
        """Try each server, then run send/recv loops."""
        for name, uri in SERVERS:
            try:
                self._ws = await asyncio.wait_for(
                    websockets.connect(uri), timeout=5
                )
                self._server_name = name
                self.is_connected = True
                logger.info(f"Smart-turn connected to {name}")
                ready.set()
                break
            except Exception as e:
                logger.warning(f"Smart-turn {name} failed: {e}")
                continue

        if not self.is_connected:
            error_holder[0] = Exception("All smart-turn servers unavailable")
            ready.set()
            return

        # Run send and receive concurrently
        try:
            await asyncio.gather(
                self._send_loop(),
                self._recv_loop(),
            )
        except Exception as e:
            if self.is_connected:
                logger.error(f"Smart-turn stream error: {e}")
        finally:
            self.is_connected = False

    async def _send_loop(self):
        """Drain audio_queue and send bytes over websocket."""
        while self.is_connected:
            try:
                # Non-blocking check with small sleep to avoid busy-wait
                try:
                    data = self.audio_queue.get_nowait()
                    await self._ws.send(data)
                except queue.Empty:
                    await asyncio.sleep(0.005)
            except Exception as e:
                if self.is_connected:
                    logger.error(f"Smart-turn send error: {e}")
                break

    async def _recv_loop(self):
        """Receive events from smart-turn server."""
        while self.is_connected:
            try:
                msg = await self._ws.recv()
                event = json.loads(msg)

                if event["event"] == "speech_start":
                    logger.info("Smart-turn: speech detected")

                elif event["event"] == "incomplete":
                    prob = event.get("probability", 0)
                    logger.debug(f"Smart-turn: still talking (prob={prob:.2f})")

                elif event["event"] == "transcription":
                    text = event.get("text", "").strip()
                    if text:
                        logger.info(f"Smart-turn transcript: {text}")
                        self.on_transcript(text, True)

            except Exception as e:
                if self.is_connected:
                    logger.error(f"Smart-turn recv error: {e}")
                break

    def send_audio(self, audio_data: bytes):
        """Queue raw PCM audio for sending (thread-safe)."""
        if self.is_connected:
            self.audio_queue.put(audio_data)

    def close(self):
        """Disconnect from server."""
        self.is_connected = False
        if self._ws and self._loop:
            asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
