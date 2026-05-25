#!/usr/bin/env python3
"""
Primavera phone chatbot — open-source services edition.

Mirrors the streaming-branch behaviour (single-personality Primavera,
context-loaded with all of her interview transcripts), but swaps every
hosted service for the open / self-hosted stack used on the fey-service
branch:

    STT   Deepgram      → smart-turn (ws://glitchbox:8200)
    TTS   ElevenLabs    → OmniVoice clone:NAME    (http://glitchbox:8000)
    LLM   Gemini cache  → local Qwen 36B          (http://glitchbox:1234)

The Gemini `cached_content` mechanism has no equivalent on the local
LLM, so Primavera's transcripts are concatenated into the system prompt
once at startup; llama.cpp / vLLM prefix-KV-cache the prefix on every
subsequent turn.
"""

import random
import os
import sys
import time
import json
import logging
import threading
import queue
import subprocess
import ctypes
from ctypes import cdll
from dotenv import load_dotenv

from smartturn_client import SmartTurnClient
from omnivoice_client import OmniVoiceClient
from conversation_manager import ConversationManager
from audio_manager import AudioManager
from config_loader import ConfigLoader


# GPIO imports
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError as e:
    GPIO_AVAILABLE = False
    print(f"Warning: RPi.GPIO not available: {e} — running in test mode")


load_dotenv()

# Audio device config (same convention as the rest of the project)
AUDIO_INPUT_DEVICE = int(os.getenv("AUDIO_INPUT_DEVICE", "-1"))
AUDIO_OUTPUT_DEVICE = int(os.getenv("AUDIO_OUTPUT_DEVICE", "-1"))
AUDIO_INPUT_DEVICE = None if AUDIO_INPUT_DEVICE == -1 else AUDIO_INPUT_DEVICE
AUDIO_OUTPUT_DEVICE = None if AUDIO_OUTPUT_DEVICE == -1 else AUDIO_OUTPUT_DEVICE

# Local-service endpoints — defaults point at the glitchbox.
# Model name + sampling params match plantoid15-raspberry/lib/plantoid/speech.py
# (GPTmagic), which is the known-working call shape against the same server.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://100.79.41.86:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen3.6-35B-A3B")

# Primavera's voice clone profile (see voice_library/profiles/primavera/)
PRIMAVERA_VOICE_ID = os.getenv("TTS_VOICE_ID", "primavera")

# OmniVoice TTS yields raw 16-bit PCM mono at 24kHz (parsed from WAV stream)
OMNIVOICE_SAMPLE_RATE = 24000

# Token budget vs. the glitchbox Qwen 36B's 65,536-token context window.
# Measured ratio on Primavera's transcripts: ~4.88 chars/token. We use 4.88
# for the transcripts cap (same text style) and a more conservative 4.5
# chars/token for the runtime budget so we don't trim too late if a turn
# happens to be token-heavy.
#
#   Transcripts:   60,000 tokens × 4.88 ≈ 292,800 chars  (system prompt corpus)
#   Trim budget:   64,000 tokens × 4.88 ≈ 312,000 chars  (start trimming above this)
#   Trim target:   61,500 tokens × 4.88 ≈ 300,000 chars  (trim back to this)
#
# At 60K tokens of transcripts there's only ~5.5K tokens of headroom under
# the 65,536 wall, so trimming fires often. Drop the transcripts cap if
# you want longer continuous conversation memory.
DEFAULT_TRANSCRIPTS_MAX_CHARS = 292_800
DEFAULT_TRIM_BUDGET_CHARS = 312_000
DEFAULT_TRIM_TARGET_CHARS = 300_000

# Suppress ALSA error messages
os.environ['ALSA_PCM_CARD'] = '1'
os.environ['ALSA_PCM_DEVICE'] = '0'

ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int,
                                     ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)

def py_error_handler(filename, line, function, err, fmt):
    pass

c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

try:
    asound = cdll.LoadLibrary('libasound.so.2')
    asound.snd_lib_error_set_handler(c_error_handler)
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# GPIO pin definitions (same as streaming branch)
PHONE_HANDLE_PIN = 21
PULSE_ENABLE_PIN = 23
PULSE_INPUT_PIN = 24


# ── Primavera system prompt + transcript loader ─────────────────────────

# Path to the editable system prompt. Override with PRIMAVERA_SYSTEM_PROMPT_FILE
# if you want to A/B different personas without touching config/.
SYSTEM_PROMPT_FILE = os.getenv(
    "PRIMAVERA_SYSTEM_PROMPT_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "config", "primavera_system_prompt.txt"),
)

# Inline fallback used only if the file is missing/unreadable. Keep this
# minimal — the canonical prompt lives in config/primavera_system_prompt.txt
# and that's the one you should edit.
_FALLBACK_SYSTEM_PROMPT = (
    "You are Primavera De Filippi. Answer in first person, in her style, "
    "as if speaking on the phone. Never act like an AI assistant. Keep "
    "responses to one paragraph maximum."
)


def _load_system_prompt() -> str:
    """Load the system prompt from disk; fall back to the inline minimal version."""
    try:
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            logger.info(f"Loaded system prompt from {SYSTEM_PROMPT_FILE} ({len(text):,} chars)")
            return text
        logger.warning(f"{SYSTEM_PROMPT_FILE} is empty — using fallback prompt")
    except FileNotFoundError:
        logger.warning(f"{SYSTEM_PROMPT_FILE} not found — using fallback prompt")
    except Exception as e:
        logger.warning(f"Could not read {SYSTEM_PROMPT_FILE} ({e}) — using fallback prompt")
    return _FALLBACK_SYSTEM_PROMPT


PRIMAVERA_SYSTEM_PROMPT = _load_system_prompt()


def _load_primavera_transcripts(transcripts_dir: str = "Cache transcripts",
                                max_chars: int | None = None) -> str:
    """Flatten every transcript JSON in `transcripts_dir` into one corpus string.

    Each file is expected to look like:
        [{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]}]
    Other shapes are tolerated by walking the JSON and pulling any
    {role, content} pairs found.
    """
    if not os.path.isdir(transcripts_dir):
        logger.warning(f"Transcripts directory '{transcripts_dir}' not found — Primavera will have no context")
        return ""

    blocks: list[str] = []
    total_chars = 0
    for filename in sorted(os.listdir(transcripts_dir)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(transcripts_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Could not read {filename}: {e}")
            continue

        # Pull every {role, content} pair, regardless of nesting depth
        pairs: list[tuple[str, str]] = []

        def walk(node):
            if isinstance(node, dict):
                if "role" in node and "content" in node and isinstance(node["content"], str):
                    pairs.append((node["role"], node["content"]))
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)

        if not pairs:
            continue

        lines = [f"--- TRANSCRIPT: {filename} ---"]
        for role, content in pairs:
            tag = "Assistant" if role == "assistant" else "User"
            lines.append(f"{tag}: {content}")
        block = "\n".join(lines)

        if max_chars is not None and total_chars + len(block) > max_chars:
            logger.info(f"Reached max_chars={max_chars}, stopping at {filename}")
            break

        blocks.append(block)
        total_chars += len(block)

    logger.info(f"Loaded {len(blocks)} Primavera transcripts ({total_chars:,} chars)")
    return "\n\n".join(blocks)


def build_primavera_personality() -> dict:
    """Build the personality dict consumed by ConversationManager."""
    # Cap the transcripts corpus so it fits the LLM's context window.
    # Default: 244,000 chars ≈ 50,000 tokens, leaving room for system
    # instruction, conversation history, and generation under a 65K window.
    max_chars_env = os.getenv("PRIMAVERA_CONTEXT_MAX_CHARS", "").strip()
    max_chars = (int(max_chars_env) if max_chars_env.isdigit() and int(max_chars_env) > 0
                 else DEFAULT_TRANSCRIPTS_MAX_CHARS)

    transcripts_corpus = _load_primavera_transcripts(
        transcripts_dir=os.getenv("PRIMAVERA_TRANSCRIPTS_DIR", "Cache transcripts"),
        max_chars=max_chars,
    )

    if transcripts_corpus:
        system_message = (
            f"{PRIMAVERA_SYSTEM_PROMPT}\n\n"
            f"=== PAST INTERVIEWS AND TALKS (your own voice as 'Assistant') ===\n\n"
            f"{transcripts_corpus}"
        )
    else:
        system_message = PRIMAVERA_SYSTEM_PROMPT

    return {
        "name": "Primavera",
        "profile_id": PRIMAVERA_VOICE_ID,
        "system_message": system_message,
        "voice_settings": {},
        "conversation_style": {
            "max_response_length": 250,
            "temperature": 0.8,
            "interruption_acknowledgment": "Oh, sorry, go ahead?",
            "thinking_sounds": ["Hmm...", "Let me think...", "Well..."],
        },
    }


# ── Main chatbot ────────────────────────────────────────────────────────


class PrimaveraOpenSourceChatbot:

    def __init__(self):
        self.config = ConfigLoader()

        logger.info(f"Audio Config - Input Device: {AUDIO_INPUT_DEVICE}, Output Device: {AUDIO_OUTPUT_DEVICE}")
        self.audio_manager = AudioManager(
            input_device_index=AUDIO_INPUT_DEVICE,
            output_device_index=AUDIO_OUTPUT_DEVICE
        )

        self._ensure_audio_setup()
        self._debug_audio_devices()

        # Build Primavera's personality with all transcripts loaded
        primavera_personality = build_primavera_personality()

        # Open-source stack: smart-turn STT, OmniVoice TTS clone, local Qwen LLM
        self.smartturn = SmartTurnClient(on_transcript=self.handle_transcript)
        self.tts = OmniVoiceClient(voice_id=PRIMAVERA_VOICE_ID)
        # Sampling params matched to plantoid15-raspberry/lib/plantoid/speech.py:GPTmagic.
        # enable_thinking=False is the load-bearing one — without it Qwen burns
        # the entire max_tokens budget on hidden reasoning and returns empty
        # visible content.
        self.conversation = ConversationManager(
            personality_config=primavera_personality,
            base_url=LLM_BASE_URL,
            model=LLM_MODEL,
            extra_body={
                "repetition_penalty": 1.15,
                "frequency_penalty": 0.5,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )

        # Context-window trimming thresholds (env-overridable)
        self._trim_budget_chars = int(os.getenv(
            "PRIMAVERA_TRIM_BUDGET_CHARS", str(DEFAULT_TRIM_BUDGET_CHARS)))
        self._trim_target_chars = int(os.getenv(
            "PRIMAVERA_TRIM_TARGET_CHARS", str(DEFAULT_TRIM_TARGET_CHARS)))
        if self._trim_target_chars >= self._trim_budget_chars:
            logger.warning(
                f"TRIM_TARGET ({self._trim_target_chars}) must be < TRIM_BUDGET "
                f"({self._trim_budget_chars}); using budget − 10%."
            )
            self._trim_target_chars = int(self._trim_budget_chars * 0.9)
        logger.info(
            f"Context trim: budget={self._trim_budget_chars:,} chars, "
            f"target={self._trim_target_chars:,} chars"
        )

        # State management
        self.phone_active = False
        self.dial_tone_playing = False
        self.ringback_playing = False
        self.conversation_active = False

        self.is_listening = False
        self.is_processing = False
        self.is_ai_speaking = False
        self.processing_lock = threading.Lock()
        self.current_transcript = ""
        self.accumulated_transcript = ""
        self.last_final_time = 0

        # GPIO setup
        if GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(PHONE_HANDLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(PULSE_ENABLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.setup(PULSE_INPUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.last_phone_state = True
        self.last_pulse_enable_state = True
        self.last_pulse_state = True
        self.pulse_count = 0
        self.counting_active = False

        self.processing_tick_active = False

        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()

        self.tts_thread = None
        self.playback_thread = None

    def start(self):
        logger.info("📞 Primavera (open-source) Phone Chatbot Ready!")
        logger.info("Pick up the phone to begin...")
        logger.info(f"LLM: {LLM_MODEL} @ {LLM_BASE_URL}")

        self._generate_dial_tone()
        self._generate_ringback_tone()

        try:
            if GPIO_AVAILABLE:
                self._gpio_loop()
            else:
                self._test_loop()
        except KeyboardInterrupt:
            logger.info("\nShutting down...")
        finally:
            self.cleanup()

    def _test_loop(self):
        print("\nTest mode - use keyboard commands:")
        print("  p: Pick up phone")
        print("  h: Hang up phone")
        print("  1-9,0: Dial any number (single-personality, dial just starts the call)")
        print("  q: Quit")

        while True:
            cmd = input("\nCommand: ").strip().lower()

            if cmd == 'p':
                self._handle_phone_pickup()
            elif cmd == 'h':
                self._handle_phone_hangup()
            elif cmd in '1234567890':
                self._stop_dial_tone()
                self._start_conversation()
            elif cmd == 'q':
                break

    def _gpio_loop(self):
        while True:
            phone_state = GPIO.input(PHONE_HANDLE_PIN)
            pulse_enable_state = GPIO.input(PULSE_ENABLE_PIN)
            pulse_state = GPIO.input(PULSE_INPUT_PIN)

            if self.last_phone_state and not phone_state:
                self._handle_phone_pickup()
            elif not self.last_phone_state and phone_state:
                self._handle_phone_hangup()

            # Any dial pulse on the rotary starts Primavera's call
            if self.phone_active and not self.conversation_active:
                if self.last_pulse_enable_state and not pulse_enable_state:
                    logger.info("📞 Dialing started...")
                    self.counting_active = True
                    self.pulse_count = 0
                    self._stop_dial_tone()
                elif not self.last_pulse_enable_state and pulse_enable_state:
                    if self.counting_active:
                        self.counting_active = False
                        self._start_conversation()

                if self.counting_active and self.last_pulse_state and not pulse_state:
                    self.pulse_count += 1
                    logger.info(f"Pulse {self.pulse_count}")

            self.last_phone_state = phone_state
            self.last_pulse_enable_state = pulse_enable_state
            self.last_pulse_state = pulse_state

            time.sleep(0.01)

    def _play_greeting(self):
        """Play the greeting on pickup.

        - If GREETING_TEXT env var is set (non-empty), TTS it through the
          active voice clone — used by per-persona launchers (e.g. Logina).
        - Otherwise, fall back to the original random-WAV behaviour from
          ./Voice samples/greetings/ — preserves the pre-recorded
          Primavera greetings when no explicit text is configured.
        """
        greeting_text = os.getenv("GREETING_TEXT", "").strip()

        if not greeting_text:
            self._play_random_sound('./Voice samples/greetings/')
            return

        logger.info(f"Speaking greeting: {greeting_text}")

        audio_chunks = []
        for chunk in self.tts.stream_text(greeting_text, voice_id=PRIMAVERA_VOICE_ID):
            audio_chunks.append(chunk)

        if not audio_chunks:
            logger.warning(
                "Greeting TTS produced no audio — caller will hear silence on pickup"
            )
            return

        audio_data = b''.join(audio_chunks)
        # Block the mic-path from picking up the greeting echo as user speech
        self.is_ai_speaking = True
        try:
            self.audio_manager.play_audio(
                audio_data, format='raw', sample_rate=OMNIVOICE_SAMPLE_RATE
            )
        finally:
            self.is_ai_speaking = False

    def _play_random_sound(self, folder_path):
        wav_files = [f for f in os.listdir(folder_path) if f.endswith('.wav')]
        if not wav_files:
            logger.warning(f"No .wav files in {folder_path}")
            return
        selected_file = random.choice(wav_files)
        full_path = os.path.join(folder_path, selected_file)
        logger.info(f"Playing: {selected_file}")
        with open(full_path, "rb") as f:
            audio_bytes = f.read()
        self.audio_manager.play_audio(audio_bytes, format='wav')

    def _start_conversation(self):
        if self.conversation_active:
            return
        self.conversation_active = True

        logger.info("Setting up connection...")
        self._play_ringback_tone()

        try:
            # Connect smart-turn (retry up to 3 times)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    logger.info(f"Connecting to smart-turn (attempt {attempt + 1}/{max_retries})...")
                    self.smartturn.connect()
                    break
                except Exception as e:
                    logger.error(f"Smart-turn connection attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        logger.info("Retrying in 2 seconds...")
                        time.sleep(2)
                    else:
                        raise Exception(f"Failed to connect to smart-turn after {max_retries} attempts")

            self.start_streaming_threads()

            self.is_listening = True
            self.audio_manager.start_recording(self.handle_audio_chunk)

            logger.info("Ready! Stopping ringback and playing greeting...")
            self._stop_ringback_tone()
            time.sleep(0.5)

            self._play_greeting()

            logger.info("Listening for user speech...")

        except Exception as e:
            logger.error(f"Error starting conversation: {e}")
            self._stop_ringback_tone()
            logger.info("Playing error tone...")
            self._play_error_tone()
            self.conversation_active = False

    def _handle_phone_pickup(self):
        logger.info("☎️  Phone picked up!")
        self.phone_active = True
        self._play_dial_tone()

    def _handle_phone_hangup(self):
        logger.info("📞 Phone hung up - shutting down everything!")
        self.phone_active = False
        self.conversation_active = False

        self._stop_dial_tone()
        self._stop_ringback_tone()
        self._stop_processing_tick()

        self.is_listening = False
        self.is_processing = False
        self.is_ai_speaking = False
        self.accumulated_transcript = ""
        self.current_transcript = ""

        # Clear chat history but keep the system message (transcripts) so the
        # next pickup doesn't have to re-prefix-cache the whole corpus.
        self.conversation.clear_history(keep_system=True)

        self.audio_manager.stop_recording()
        self.audio_manager.interrupt_playback()

        try:
            self.smartturn.close()
        except Exception:
            pass

        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
            except Exception:
                pass
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except Exception:
                pass

        logger.info("✅ System reset - ready for next pickup")

    def _generate_dial_tone(self):
        if not os.path.exists('sounds/dial_tone.wav'):
            logger.info("Generating dial tone...")
            subprocess.run([sys.executable, 'generate_dial_tone.py'])

    def _generate_ringback_tone(self):
        if os.path.exists('sounds/ringback_tone.wav'):
            return
        logger.info("Generating ringback tone...")
        import numpy as np
        import wave

        sample_rate = 16000
        t_beep = np.linspace(0, 0.4, int(sample_rate * 0.4), False)
        beep1 = np.sin(2 * np.pi * 440 * t_beep)
        beep2 = np.sin(2 * np.pi * 480 * t_beep)
        beep = (beep1 + beep2) * 0.3

        fade_samples = int(0.01 * sample_rate)
        beep[:fade_samples] *= np.linspace(0, 1, fade_samples)
        beep[-fade_samples:] *= np.linspace(1, 0, fade_samples)

        silence = np.zeros(int(sample_rate * 1.2))
        ringback = np.concatenate([beep, beep, silence])
        ringback_audio = (ringback * 32767).astype(np.int16)

        os.makedirs('sounds', exist_ok=True)
        with wave.open('sounds/ringback_tone.wav', 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(ringback_audio.tobytes())

        logger.info("Ringback tone generated")

    def _play_dial_tone(self):
        if self.dial_tone_playing:
            return
        self.dial_tone_playing = True

        def play_loop():
            while self.dial_tone_playing and self.phone_active:
                try:
                    if not self.phone_active:
                        break
                    with open('sounds/dial_tone.wav', 'rb') as f:
                        audio_data = f.read()
                    self.audio_manager.play_audio(audio_data, format='wav')
                    if self.dial_tone_playing and self.phone_active:
                        time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error playing dial tone: {e}")
                    break

        threading.Thread(target=play_loop, daemon=True).start()

    def _stop_dial_tone(self):
        self.dial_tone_playing = False
        logger.info("Dial tone stopped")

    def _play_ringback_tone(self):
        if self.ringback_playing:
            return
        self.ringback_playing = True

        def play_loop():
            while self.ringback_playing and self.phone_active:
                try:
                    if not self.phone_active or not self.ringback_playing:
                        break
                    with open('sounds/ringback_tone.wav', 'rb') as f:
                        audio_data = f.read()
                    self.audio_manager.play_audio(audio_data, format='wav')
                except Exception as e:
                    logger.error(f"Error playing ringback tone: {e}")
                    break

        threading.Thread(target=play_loop, daemon=True).start()

    def _stop_ringback_tone(self):
        self.ringback_playing = False
        logger.info("Ringback tone stopped")

    def _play_error_tone(self):
        try:
            import numpy as np
            import wave
            import io

            sample_rate = 16000
            duration = 3.0

            t = np.linspace(0, duration, int(sample_rate * duration), False)
            beep1 = np.sin(2 * np.pi * 480 * t)
            beep2 = np.sin(2 * np.pi * 620 * t)
            tone = (beep1 + beep2) * 0.3

            for i in range(len(tone)):
                if int(i / sample_rate * 4) % 2 == 1:
                    tone[i] = 0

            error_audio = (tone * 32767).astype(np.int16)

            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, 'w') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(error_audio.tobytes())
            wav_buffer.seek(0)
            self.audio_manager.play_audio(wav_buffer.read(), format='wav')
        except Exception as e:
            logger.error(f"Error playing error tone: {e}")

    def start_streaming_threads(self):
        self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.tts_thread.start()
        self.playback_thread = threading.Thread(target=self._playback_worker, daemon=True)
        self.playback_thread.start()

    def handle_audio_chunk(self, audio_data: bytes):
        if self.is_listening and not self.is_ai_speaking:
            self.smartturn.send_audio(audio_data)

    def handle_transcript(self, transcript: str, is_final: bool):
        if self.is_ai_speaking or not transcript.strip():
            return

        current_time = time.time()

        if is_final:
            logger.info(f"Final: {transcript}")
            if not self.is_ai_speaking:
                self.accumulated_transcript += " " + transcript
                self.last_final_time = current_time
                # smart-turn already does turn detection, so a final transcript
                # is enough to trigger processing on its own.
                self.process_accumulated_transcript()
        else:
            if not self.is_ai_speaking:
                self.current_transcript = transcript

    def _trim_conversation_if_needed(self):
        """Drop oldest user/assistant pairs once the request approaches the
        context window. The system message (index 0) is always preserved
        because it holds the loaded transcript corpus.

        Trimming happens in pairs to keep the user→assistant alternation
        intact, and stops once total chars drop below TRIM_TARGET_CHARS.
        """
        messages = self.conversation.messages
        if len(messages) <= 1:
            return

        def total_chars() -> int:
            return sum(len(m.content) for m in messages)

        current = total_chars()
        if current <= self._trim_budget_chars:
            return

        logger.info(
            f"⚠ Context trim: {current:,} chars > budget {self._trim_budget_chars:,} "
            f"— dropping oldest history"
        )

        dropped = 0
        # Always keep system @ index 0. Drop pairs from index 1.
        while total_chars() > self._trim_target_chars and len(messages) >= 3:
            old_user = messages.pop(1)
            old_assistant = messages.pop(1) if len(messages) >= 2 else None
            dropped += 1 + (1 if old_assistant else 0)
            logger.info(
                f"  dropped {old_user.role}({len(old_user.content)}ch)"
                + (f" + {old_assistant.role}({len(old_assistant.content)}ch)" if old_assistant else "")
            )

        logger.info(
            f"  trim done: {len(messages)} messages, {total_chars():,} chars "
            f"(dropped {dropped})"
        )

    def process_accumulated_transcript(self):
        with self.processing_lock:
            if self.is_ai_speaking or self.is_processing or not self.accumulated_transcript.strip():
                return

            transcript = self.accumulated_transcript.strip()
            self.accumulated_transcript = ""

            if len(transcript.split()) < 2:
                return

            logger.info(f"Processing: {transcript}")
            self.is_processing = True
            self.is_ai_speaking = True

        self._start_processing_tick()

        response_thread = threading.Thread(
            target=self._generate_streaming_response_with_monitor,
            args=(transcript,),
            daemon=True,
        )
        response_thread.start()

    def _generate_streaming_response_with_monitor(self, transcript: str):
        thread_timeout = 60.0
        generation_thread = threading.Thread(
            target=self._generate_streaming_response,
            args=(transcript,),
            daemon=True,
        )
        generation_thread.start()
        generation_thread.join(thread_timeout)

        if generation_thread.is_alive():
            logger.error(f"Response generation thread timed out after {thread_timeout} seconds")
            self.is_processing = False
            self._stop_processing_tick()
            self.text_queue.put("I'm sorry, I'm having trouble responding right now.")

    def _generate_streaming_response(self, transcript: str):
        response_timeout = 45.0
        start_time = time.time()

        try:
            self.conversation.add_user_message(transcript)
            self._trim_conversation_if_needed()

            sentence_buffer = ""
            for text_chunk in self.conversation.generate_response(streaming=True):
                if time.time() - start_time > response_timeout:
                    logger.warning("Response generation timed out")
                    self.text_queue.put("I'm sorry, I'm taking too long to respond.")
                    break
                sentence_buffer += text_chunk

            queued = False
            if sentence_buffer.strip():
                # Strip stage directions / parentheticals like fey-service does
                import re
                cleaned = re.sub(r'\*[^*]*\*', '', sentence_buffer)
                cleaned = re.sub(r'\([^)]*\)', '', cleaned)
                cleaned = re.sub(r'^Assistant:\s*', '', cleaned)
                cleaned = re.split(r'\nUser:', cleaned)[0]
                cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
                if cleaned:
                    self.text_queue.put(cleaned)
                    queued = True

            if not queued:
                # Empty / filtered-to-empty response. Nothing will reach the
                # audio queue, so the playback worker won't clear our state.
                # Reset here, otherwise the tick loops forever and
                # is_ai_speaking stays True (bot goes deaf).
                logger.warning("LLM produced no usable response — resetting state")
                self._stop_processing_tick()
                self.is_ai_speaking = False

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            self.text_queue.put("I'm sorry, I encountered an issue. Can you please try again?")
        finally:
            self.is_processing = False

    def _tts_worker(self):
        """Pull text chunks, synthesize via Qwen-TTS, queue PCM for playback."""
        while True:
            try:
                text = self.text_queue.get(timeout=1)
                if text is None:
                    break

                logger.info(f"Streaming OmniVoice TTS for: {text[:80]}...")
                audio_chunks = []
                chunk_count = 0

                for chunk in self.tts.stream_text(text, voice_id=PRIMAVERA_VOICE_ID):
                    audio_chunks.append(chunk)
                    chunk_count += 1
                    if chunk_count == 1:
                        logger.info(f"First audio chunk received ({len(chunk)} bytes)!")

                audio_data = b''.join(audio_chunks)
                logger.info(f"TTS complete: {chunk_count} chunks, {len(audio_data)} bytes total")
                self.audio_queue.put(('pcm', audio_data))

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"TTS error: {e}")

    def _playback_worker(self):
        while True:
            try:
                queue_item = self.audio_queue.get(timeout=1)
                if queue_item is None:
                    break

                audio_format, audio_data = queue_item

                self._stop_processing_tick()

                was_listening = self.is_listening
                if was_listening:
                    self.is_listening = False
                    logger.info("🔇 Stopped listening during AI speech")

                self.accumulated_transcript = ""
                self.current_transcript = ""

                logger.info(f"Playing audio chunk (format: {audio_format}, {len(audio_data)} bytes)...")

                # Rough duration estimate for the timeout
                if audio_format == 'pcm':
                    # 16-bit mono @ 24kHz
                    estimated_duration = (len(audio_data) / (OMNIVOICE_SAMPLE_RATE * 2)) + 5.0
                else:
                    estimated_duration = (len(audio_data) / 3000) + 5.0

                logger.info(f"Estimated duration: {estimated_duration:.1f}s")

                success = self._play_audio_with_timeout(
                    audio_data, timeout=estimated_duration, format=audio_format
                )

                if not success:
                    logger.error("Audio playback failed or timed out — waiting before resuming")
                    time.sleep(2.0)

                self.is_ai_speaking = False
                self.is_processing = False
                if was_listening:
                    self.is_listening = True
                    logger.info("🎤 Resumed listening after AI speech")

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Playback error: {e}")
                self.is_ai_speaking = False
                self.is_processing = False

    def _play_audio_with_timeout(self, audio_data: bytes, timeout: float = 10.0, format: str = 'pcm'):
        """Play audio with timeout protection."""
        exception = [None]

        def play_audio():
            try:
                if format == 'pcm':
                    # OmniVoice gives us raw 16-bit PCM mono @ 24kHz (extracted from WAV stream)
                    self.audio_manager.play_audio(
                        audio_data, format='raw', sample_rate=OMNIVOICE_SAMPLE_RATE
                    )
                else:
                    self.audio_manager.play_audio(audio_data, format=format)
            except Exception as e:
                exception[0] = e

        playback_thread = threading.Thread(target=play_audio, daemon=True)
        playback_thread.start()
        playback_thread.join(timeout)

        if playback_thread.is_alive():
            logger.error(f"Audio playback timed out after {timeout:.1f}s")
            return False
        if exception[0]:
            logger.error(f"Audio playback error: {exception[0]}")
            return False
        return True

    def cleanup(self):
        logger.info("Shutting down...")
        self.is_listening = False
        self.text_queue.put(None)
        self.audio_queue.put(None)
        self.audio_manager.cleanup()
        try:
            self.smartturn.close()
        except Exception:
            pass
        if GPIO_AVAILABLE:
            GPIO.cleanup()

    def _ensure_audio_setup(self):
        try:
            time.sleep(1)
            subprocess.run(['amixer', 'cset', 'numid=3', '1'],
                           check=False, capture_output=True)
            subprocess.run(['amixer', '-c', '1', 'sset', 'PCM', '100%'],
                           check=False, capture_output=True)
            result = subprocess.run(['amixer', '-c', '1', 'sget', 'PCM'],
                                    capture_output=True, text=True, check=False)
            if '100%' in result.stdout:
                logger.info("🔊 Audio configured: 3.5mm jack at 100% volume")
            else:
                logger.warning("⚠️ Volume setting may not have worked (may be running on Mac)")
        except Exception as e:
            logger.error(f"Error setting up audio: {e}")

    def _debug_audio_devices(self):
        try:
            logger.info("=== AUDIO DEVICES DEBUG ===")
            logger.info("Available output devices:")
            for device in self.audio_manager.get_output_devices():
                logger.info(f"  {device['index']}: {device['name']} ({device['channels']} channels)")
            logger.info("Available input devices:")
            for device in self.audio_manager.get_input_devices():
                logger.info(f"  {device['index']}: {device['name']} ({device['channels']} channels)")
            logger.info(f"Selected input device: {AUDIO_INPUT_DEVICE}")
            logger.info(f"Selected output device: {AUDIO_OUTPUT_DEVICE}")
            logger.info("===========================")
        except Exception as e:
            logger.error(f"Error debugging audio devices: {e}")

    def _start_processing_tick(self):
        if self.processing_tick_active:
            return
        self.processing_tick_active = True
        threading.Thread(target=self._play_processing_tick, daemon=True).start()

    def _stop_processing_tick(self):
        self.processing_tick_active = False

    def _play_processing_tick(self):
        try:
            import numpy as np
            from pydub import AudioSegment
            import io

            sample_rate = 16000
            duration = 0.08
            frequency = 220

            t = np.linspace(0, duration, int(sample_rate * duration), False)
            tick_tone = np.sin(2 * np.pi * frequency * t) * 0.6

            fade_samples = int(0.005 * sample_rate)
            tick_tone[:fade_samples] *= np.linspace(0, 1, fade_samples)
            tick_tone[-fade_samples:] *= np.linspace(1, 0, fade_samples)

            tick_audio = (tick_tone * 32767).astype(np.int16)

            audio_segment = AudioSegment(
                data=tick_audio.tobytes(),
                sample_width=2,
                frame_rate=sample_rate,
                channels=1,
            )

            wav_buffer = io.BytesIO()
            audio_segment.export(wav_buffer, format="wav")
            wav_buffer.seek(0)
            tick_wav = wav_buffer.read()

            try:
                with open("/tmp/debug_tick.wav", "wb") as f:
                    f.write(tick_wav)
            except Exception:
                pass

            tick_count = 0
            while self.processing_tick_active:
                tick_count += 1
                logger.info(f"🔊 TICK #{tick_count}")
                if sys.platform == 'linux':
                    subprocess.Popen(['aplay', '-D', 'plughw:1,0', '/tmp/debug_tick.wav'],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(['afplay', '/tmp/debug_tick.wav'],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                time.sleep(0.8)

        except Exception as e:
            logger.error(f"Error playing processing tick: {e}")


def main():
    logger.info(f"Primavera open-source — LLM={LLM_MODEL} @ {LLM_BASE_URL}")
    logger.info("Override with LLM_BASE_URL / LLM_MODEL env vars if needed.")
    chatbot = PrimaveraOpenSourceChatbot()
    chatbot.start()


if __name__ == "__main__":
    main()
