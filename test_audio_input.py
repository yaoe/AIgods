#!/usr/bin/env python3
"""Test audio input devices on Raspberry Pi"""

import pyaudio
import numpy as np
import time

def test_input_device(device_index, device_name, p):
    """Test a specific input device"""
    print(f"\nTesting input device {device_index}: {device_name}")
    print("Speak into your microphone for 3 seconds...")
    
    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=1024
        )
        
        frames = []
        for i in range(0, int(16000 / 1024 * 3)):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
            
            # Show real-time level
            audio_chunk = np.frombuffer(data, dtype=np.int16)
            level = np.max(np.abs(audio_chunk))
            bars = '=' * int(level / 1000)
            print(f"\rLevel: {bars:<50}", end="", flush=True)
        
        print()  # New line
        stream.stop_stream()
        stream.close()
        
        # Check if we got audio
        audio_data = b''.join(frames)
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        max_amplitude = np.max(np.abs(audio_array))
        avg_amplitude = np.mean(np.abs(audio_array))
        
        print(f"Max amplitude: {max_amplitude}, Average: {avg_amplitude:.0f}")
        
        if max_amplitude > 500:
            print("✓ This device appears to be working!")
            return True
        else:
            print("✗ No significant audio detected")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    # Suppress JACK warnings
    p = pyaudio.PyAudio()
    
    print("Available input devices:")
    input_devices = []
    
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            print(f"{i}: {info['name']} - {info['maxInputChannels']} channels")
            input_devices.append((i, info['name']))
    
    if not input_devices:
        print("\nNo input devices found! Please check your microphone connection.")
        p.terminate()
        return
    
    print("\nTesting each input device...")
    print("Make sure to speak or make noise during the test!\n")
    
    working_device = None
    for device_index, device_name in input_devices:
        if test_input_device(device_index, device_name, p):
            working_device = device_index
            break
        time.sleep(0.5)
    
    p.terminate()
    
    if working_device is not None:
        print(f"\n✓ Use input_device_index={working_device} in your code")
        print("\nTo use this device, update your AudioManager initialization:")
        print(f"AudioManager(output_device_index=1, input_device_index={working_device})")
    else:
        print("\n✗ No working input device found")
        print("\nTroubleshooting:")
        print("1. Check your microphone is properly connected")
        print("2. Try: sudo apt-get install pulseaudio")
        print("3. Try: alsamixer (and unmute/increase mic volume)")
        print("4. For USB devices, check: lsusb")

if __name__ == "__main__":
    main()