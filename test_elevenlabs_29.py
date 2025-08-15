#!/usr/bin/env python3
"""
Test ElevenLabs 2.9+ official streaming API
"""

import os
from dotenv import load_dotenv
from elevenlabs import stream
from elevenlabs.client import ElevenLabs

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

def test_official_api():
    """Test the exact API pattern from ElevenLabs 2.9+ docs"""
    
    if not ELEVENLABS_API_KEY:
        print("❌ ERROR: ELEVENLABS_API_KEY not found")
        return
    
    print("Testing ElevenLabs 2.9+ Official Streaming API")
    print("=" * 50)
    
    try:
        # Initialize client (with API key)
        elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        
        print("🎭 Testing The God voice...")
        
        # Create audio stream using official API
        audio_stream = elevenlabs.text_to_speech.stream(
            text="Hello, this is a test of the official ElevenLabs streaming API.",
            voice_id="o7lPjDgzlF8ZloHzVPeK",  # The God voice
            model_id="eleven_multilingual_v2"
        )
        
        print("✅ Audio stream created successfully!")
        
        # Option 2: Process the audio bytes manually (for our use case)
        chunk_count = 0
        total_bytes = 0
        
        print("📡 Processing audio chunks...")
        for chunk in audio_stream:
            if isinstance(chunk, bytes):
                chunk_count += 1
                total_bytes += len(chunk)
                
                if chunk_count <= 3:
                    print(f"   - Chunk {chunk_count}: {len(chunk)} bytes")
        
        print(f"✅ Streaming completed: {chunk_count} chunks, {total_bytes} total bytes")
        
        # Test multiple voices
        test_voices = [
            ("aCopqDQNLq4x1DlXCyDz", "The Jester God"),
            ("XB0fDUnXU5powFXDhCwa", "The Spirit of Fey"),
        ]
        
        for voice_id, name in test_voices:
            print(f"\n🎭 Testing {name}...")
            
            audio_stream = elevenlabs.text_to_speech.stream(
                text="Testing voice streaming.",
                voice_id=voice_id,
                model_id="eleven_multilingual_v2"
            )
            
            chunk_count = 0
            for chunk in audio_stream:
                if isinstance(chunk, bytes):
                    chunk_count += 1
            
            print(f"✅ {name}: {chunk_count} chunks received")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("✅ ElevenLabs 2.9+ API test completed!")

if __name__ == "__main__":
    test_official_api()