#!/usr/bin/env python3
"""
Test ElevenLabs streaming with the correct API methods
"""

import os
from io import BytesIO
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

def test_convert_as_stream():
    """Test using convert_as_stream method"""
    print("🎭 Testing convert_as_stream method...")
    
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    
    test_text = "Hello, this is a test of ElevenLabs streaming functionality."
    voice_id = "o7lPjDgzlF8ZloHzVPeK"  # The God voice
    
    try:
        # Use convert_as_stream method
        audio_stream = client.text_to_speech.convert_as_stream(
            voice_id=voice_id,
            output_format="mp3_22050_32",
            text=test_text,
            model_id="eleven_multilingual_v2",
            voice_settings=VoiceSettings(
                stability=0.5,
                similarity_boost=0.75,
                style=0.0,
                use_speaker_boost=True,
                speed=1.0,
            )
        )
        
        # Collect streaming chunks
        audio_buffer = BytesIO()
        chunk_count = 0
        total_bytes = 0
        
        print("   Streaming chunks:")
        for chunk in audio_stream:
            if chunk:
                chunk_count += 1
                chunk_size = len(chunk)
                total_bytes += chunk_size
                audio_buffer.write(chunk)
                print(f"     - Chunk {chunk_count}: {chunk_size} bytes")
        
        print(f"   ✅ Success: {chunk_count} chunks, {total_bytes} total bytes")
        return True
        
    except Exception as e:
        print(f"   ❌ convert_as_stream failed: {e}")
        return False

def test_module_level_stream():
    """Test using the module-level stream function"""
    print("🎭 Testing module-level stream function...")
    
    try:
        from elevenlabs import stream
        
        # Test if this works (might need different parameters)
        print("   Stream function imported successfully")
        print(f"   Stream function: {stream}")
        return True
        
    except Exception as e:
        print(f"   ❌ Module stream failed: {e}")
        return False

def test_client_generate():
    """Test the main client generate method"""
    print("🎭 Testing client.generate() method...")
    
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    
    try:
        # Test if generate returns a generator (streaming)
        audio_gen = client.generate(
            text="Hello, this is a test.",
            voice="o7lPjDgzlF8ZloHzVPeK",
            model="eleven_multilingual_v2",
            stream=True  # Try with stream parameter
        )
        
        print(f"   Generate returned: {type(audio_gen)}")
        
        # If it's a generator, collect chunks
        if hasattr(audio_gen, '__iter__'):
            chunk_count = 0
            total_bytes = 0
            
            print("   Streaming chunks:")
            for chunk in audio_gen:
                if chunk:
                    chunk_count += 1
                    chunk_size = len(chunk)
                    total_bytes += chunk_size
                    print(f"     - Chunk {chunk_count}: {chunk_size} bytes")
            
            print(f"   ✅ Success: {chunk_count} chunks, {total_bytes} total bytes")
        else:
            print(f"   ℹ️  Generate returned single audio: {len(audio_gen)} bytes")
        
        return True
        
    except Exception as e:
        print(f"   ❌ client.generate failed: {e}")
        return False

if __name__ == "__main__":
    print("Testing ElevenLabs Streaming Methods")
    print("=" * 50)
    
    success_count = 0
    
    if test_convert_as_stream():
        success_count += 1
    
    print()
    if test_module_level_stream():
        success_count += 1
    
    print()
    if test_client_generate():
        success_count += 1
    
    print("\n" + "=" * 50)
    print(f"✅ {success_count}/3 methods worked!")