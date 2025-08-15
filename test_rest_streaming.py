#!/usr/bin/env python3
"""
Test the direct REST API streaming approach with audio playback
"""

import os
import sys
from dotenv import load_dotenv

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from elevenlabs_client import ElevenLabsClient
from audio_manager import AudioManager

load_dotenv()

def test_rest_streaming_with_audio():
    """Test ElevenLabs REST API streaming with actual audio playback"""
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("❌ ERROR: ELEVENLABS_API_KEY not found")
        return
    
    # Get the same audio device settings as phone chatbot
    AUDIO_INPUT_DEVICE = int(os.getenv("AUDIO_INPUT_DEVICE", "-1"))
    AUDIO_OUTPUT_DEVICE = int(os.getenv("AUDIO_OUTPUT_DEVICE", "-1"))
    
    # Use None if -1 (will use system default)
    AUDIO_INPUT_DEVICE = None if AUDIO_INPUT_DEVICE == -1 else AUDIO_INPUT_DEVICE
    AUDIO_OUTPUT_DEVICE = None if AUDIO_OUTPUT_DEVICE == -1 else AUDIO_OUTPUT_DEVICE
    
    print(f"Using audio devices - Input: {AUDIO_INPUT_DEVICE}, Output: {AUDIO_OUTPUT_DEVICE}")
    
    # Initialize clients with same settings as phone chatbot
    elevenlabs_client = ElevenLabsClient(api_key=api_key)
    audio_manager = AudioManager(
        input_device_index=AUDIO_INPUT_DEVICE,
        output_device_index=AUDIO_OUTPUT_DEVICE
    )
    
    # Test voices
    test_voices = [
        ("o7lPjDgzlF8ZloHzVPeK", "The God"),
        ("aCopqDQNLq4x1DlXCyDz", "The Jester God"),
        ("XB0fDUnXU5powFXDhCwa", "The Spirit of Fey"),
    ]
    
    test_text = "Hello, I am testing the voice streaming functionality."
    
    print("Testing ElevenLabs REST API Streaming with Audio Playback")
    print("=" * 60)
    
    for voice_id, name in test_voices:
        print(f"\n🎭 Testing {name} (Voice: {voice_id})")
        
        try:
            total_bytes = 0
            chunk_count = 0
            audio_chunks = []
            
            print("   📡 Streaming audio...")
            # Test the REST API streaming
            for chunk in elevenlabs_client.stream_text_official(test_text, voice_id=voice_id):
                chunk_count += 1
                chunk_size = len(chunk)
                total_bytes += chunk_size
                audio_chunks.append(chunk)
                
                if chunk_count <= 3:  # Show first 3 chunks
                    print(f"   - Chunk {chunk_count}: {chunk_size} bytes")
            
            print(f"   ✅ Streaming: {chunk_count} chunks, {total_bytes} total bytes")
            
            # Combine all chunks and play through same audio system as phone chatbot
            if audio_chunks:
                complete_audio = b''.join(audio_chunks)
                print(f"   🔊 Playing audio ({len(complete_audio)} bytes)...")
                
                # Play through same audio manager as phone chatbot
                audio_manager.play_audio(complete_audio, format='mp3')
                
                # Wait for playback to complete
                while audio_manager.is_playing:
                    import time
                    time.sleep(0.1)
                
                print(f"   ✅ Playback completed for {name}")
            
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Cleanup
    audio_manager.cleanup()
    
    print("\n" + "=" * 60)
    print("✅ REST API streaming with audio test completed!")

if __name__ == "__main__":
    test_rest_streaming_with_audio()