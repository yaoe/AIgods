#!/usr/bin/env python3
"""
Test script for ElevenLabs streaming functionality using official API
"""

import os
from typing import IO
from io import BytesIO
from dotenv import load_dotenv
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

elevenlabs = ElevenLabs(
    api_key=ELEVENLABS_API_KEY,
)

def text_to_speech_stream(text: str, voice_id: str = "pNInz6obpgDQGcFmaJgB") -> IO[bytes]:
    """Test the official ElevenLabs streaming API"""
    print(f"🎭 Testing voice: {voice_id}")
    
    # Perform the text-to-speech conversion
    response = elevenlabs.text_to_speech.stream(
        voice_id=voice_id,
        output_format="mp3_22050_32",
        text=text,
        model_id="eleven_multilingual_v2",
        # Optional voice settings that allow you to customize the output
        voice_settings=VoiceSettings(
            stability=0.5,
            similarity_boost=0.75,
            style=0.0,
            use_speaker_boost=True,
            speed=1.0,
        ),
    )
    
    # Create a BytesIO object to hold the audio data in memory
    audio_stream = BytesIO()
    chunk_count = 0
    total_bytes = 0
    
    # Write each chunk of audio data to the stream
    print("   Streaming chunks:")
    for chunk in response:
        if chunk:
            chunk_count += 1
            chunk_size = len(chunk)
            total_bytes += chunk_size
            audio_stream.write(chunk)
            print(f"     - Chunk {chunk_count}: {chunk_size} bytes")
    
    print(f"   ✅ Total: {chunk_count} chunks, {total_bytes} bytes")
    
    # Reset stream position to the beginning
    audio_stream.seek(0)
    
    # Return the stream for further use
    return audio_stream

def test_all_voices():
    """Test streaming with all personality voices"""
    
    if not ELEVENLABS_API_KEY:
        print("❌ ERROR: ELEVENLABS_API_KEY not found in environment")
        return
    
    # Test voices from the personalities
    test_voices = [
        ("o7lPjDgzlF8ZloHzVPeK", "The God"),
        ("aCopqDQNLq4x1DlXCyDz", "The Jester God"), 
        ("XB0fDUnXU5powFXDhCwa", "The Spirit of Fey"),
        ("0QIFTpJI5nddBLeqGnBS", "Shiva"),
        ("5g2h5kYnQtKFFdPm8PpK", "The God of Lust"),
        ("8t4LrVRcHjQaMzk17Z4d", "The Rational God"),
        ("aasaQJUbfB45vQBAlBQm", "The Pirate God"),
        ("7NsaqHdLuKNFvEfjpUno", "The Animist God"),
        ("YCTl15HImNzEMB91OWU4", "The AI Overlord"),
        ("aNLsxoRcV9h89A9dA6J5", "The Freudian God")
    ]
    
    test_text = "Hello, this is a test of the streaming functionality."
    
    print("Testing ElevenLabs Official Streaming API")
    print("=" * 60)
    
    for voice_id, name in test_voices:
        print(f"\n🎭 Testing {name}")
        try:
            audio_stream = text_to_speech_stream(test_text, voice_id)
            print(f"   ✅ Success: Audio stream created ({audio_stream.getbuffer().nbytes} bytes total)")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Test completed!")

if __name__ == "__main__":
    test_all_voices()