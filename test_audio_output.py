#!/usr/bin/env python3
"""Test audio output devices"""

import pyaudio
import numpy as np
import time

def generate_tone(frequency=440, duration=1, sample_rate=44100):
    """Generate a sine wave tone"""
    t = np.linspace(0, duration, int(sample_rate * duration))
    tone = np.sin(frequency * 2 * np.pi * t) * 0.3
    return (tone * 32767).astype(np.int16).tobytes()

def test_device(device_index, device_name):
    """Test a specific audio device"""
    p = pyaudio.PyAudio()
    
    print(f"\nTesting device {device_index}: {device_name}")
    print("You should hear a 1-second beep...")
    
    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=44100,
            output=True,
            output_device_index=device_index
        )
        
        tone = generate_tone()
        stream.write(tone)
        
        stream.stop_stream()
        stream.close()
        
        print("Done. Did you hear the beep? (y/n): ", end="")
        response = input().strip().lower()
        return response == 'y'
        
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        p.terminate()

def main():
    p = pyaudio.PyAudio()
    
    print("Available output devices:")
    devices = []
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxOutputChannels'] > 0:
            print(f"{i}: {info['name']} - {info['maxOutputChannels']} channels")
            devices.append((i, info['name']))
    
    p.terminate()
    
    # Test each device
    for device_index, device_name in devices:
        if device_index in [1, 3, 4, 5]:  # Test likely candidates
            if test_device(device_index, device_name):
                print(f"\n✓ Device {device_index} ({device_name}) works!")
                print(f"Use this device index in your code: output_device_index={device_index}")
                break
            time.sleep(0.5)

if __name__ == "__main__":
    main()