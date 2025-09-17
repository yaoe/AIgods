from elevenlabs import stream
from elevenlabs.client import ElevenLabs
elevenlabs = ElevenLabs()
audio_stream = elevenlabs.text_to_speech.stream(
    text="This is a test",
    voice_id="JBFqnCBsd6RMkjVDRZzb",
    model_id="eleven_multilingual_v2"
)
# option 1: play the streamed audio locally
stream(audio_stream)
