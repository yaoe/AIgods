#!/usr/bin/env python3
"""
Test the direct REST API streaming approach
"""

import os
import sys
from dotenv import load_dotenv

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from elevenlabs_client import ElevenLabsClient

load_dotenv()

def test_rest_streaming():
    """Test ElevenLabs REST API streaming"""
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("❌ ERROR: ELEVENLABS_API_KEY not found")
        return
    
    # Initialize client
    client = ElevenLabsClient(api_key=api_key)
    
    # Test voices
    test_voices = [
        ("o7lPjDgzlF8ZloHzVPeK", "The God"),
        ("aCopqDQNLq4x1DlXCyDz", "The Jester God"),
    ]
    
    test_text = "Hello, this is a test of REST API streaming."
    
    print("Testing ElevenLabs REST API Streaming")
    print("=" * 50)
    
    for voice_id, name in test_voices:
        print(f"\n🎭 Testing {name} (Voice: {voice_id})")
        
        try:
            total_bytes = 0
            chunk_count = 0
            
            # Test the REST API streaming
            for chunk in client.stream_text_official(test_text, voice_id=voice_id):
                chunk_count += 1
                chunk_size = len(chunk)
                total_bytes += chunk_size
                
                if chunk_count <= 3:  # Show first 3 chunks
                    print(f"   - Chunk {chunk_count}: {chunk_size} bytes")
            
            print(f"   ✅ Success: {chunk_count} chunks, {total_bytes} total bytes")
            
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    
    print("\n" + "=" * 50)
    print("✅ REST API streaming test completed!")

if __name__ == "__main__":
    test_rest_streaming()