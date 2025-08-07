#!/usr/bin/env python3
"""Test ElevenLabs audio format"""

import os
from dotenv import load_dotenv
from src.elevenlabs_client import ElevenLabsClient
from pydub import AudioSegment
import io

load_dotenv()

def test_elevenlabs_audio():
    client = ElevenLabsClient(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        voice_id=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    )
    
    # Generate test audio
    print("Generating test audio...")
    audio_data = client.generate_audio("Hello, this is a test!")
    
    print(f"Raw audio data size: {len(audio_data)} bytes")
    
    # Analyze the audio
    try:
        audio_segment = AudioSegment.from_mp3(io.BytesIO(audio_data))
        
        print(f"Original format:")
        print(f"  Frame rate: {audio_segment.frame_rate} Hz")
        print(f"  Channels: {audio_segment.channels}")
        print(f"  Sample width: {audio_segment.sample_width} bytes")
        print(f"  Duration: {len(audio_segment)} ms")
        
        # Convert to our target format
        converted = audio_segment.set_frame_rate(16000)
        converted = converted.set_channels(1)
        converted = converted.set_sample_width(2)
        
        print(f"\nConverted format:")
        print(f"  Frame rate: {converted.frame_rate} Hz")
        print(f"  Channels: {converted.channels}")
        print(f"  Sample width: {converted.sample_width} bytes")
        print(f"  Duration: {len(converted)} ms")
        print(f"  PCM data size: {len(converted.raw_data)} bytes")
        
        # Test PyAudio compatibility
        import pyaudio
        p = pyaudio.PyAudio()
        
        print(f"\nTesting PyAudio stream...")
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                output=True,
                frames_per_buffer=1024
            )
            print("✓ PyAudio stream opened successfully")
            
            # Test writing a small chunk
            chunk = converted.raw_data[:1024]
            stream.write(chunk)
            print("✓ Audio chunk written successfully")
            
            stream.close()
            
        except Exception as e:
            print(f"✗ PyAudio error: {e}")
            
        p.terminate()
        
    except Exception as e:
        print(f"Error analyzing audio: {e}")

if __name__ == "__main__":
    test_elevenlabs_audio()