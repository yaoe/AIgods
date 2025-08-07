#!/usr/bin/env python3
"""Test audio setup on Raspberry Pi"""

import pyaudio
import numpy as np
import time

def test_audio():
    try:
        # Suppress JACK warnings
        p = pyaudio.PyAudio()
        
        print(f"PyAudio version: {pyaudio.get_portaudio_version_text()}")
        print(f"Default input device: {p.get_default_input_device_info()['name']}")
        print(f"Default output device: {p.get_default_output_device_info()['name']}")
        
        print("\nAvailable audio devices:")
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            print(f"{i}: {info['name']} - {info['maxInputChannels']} in, {info['maxOutputChannels']} out")
        
        # Test recording
        print("\nTesting recording for 2 seconds...")
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024
        )
        
        frames = []
        for i in range(0, int(16000 / 1024 * 2)):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
        
        stream.stop_stream()
        stream.close()
        
        # Check if we got audio
        audio_data = b''.join(frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        max_amplitude = np.max(np.abs(audio_array))
        
        print(f"Recording complete. Max amplitude: {max_amplitude}")
        if max_amplitude < 100:
            print("WARNING: Very low audio level detected. Check microphone.")
        else:
            print("Audio recording appears to be working.")
            
        p.terminate()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_audio()