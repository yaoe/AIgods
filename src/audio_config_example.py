#!/usr/bin/env python3
"""
Example of how to configure audio devices for separate input/output
Run list_audio_devices.py first to find your device indices
"""

from audio_manager import AudioManager
import logging

logging.basicConfig(level=logging.INFO)

# Example 1: Using specific devices
# After running list_audio_devices.py, you'll see output like:
# Device 0: USB Microphone (INPUT)
# Device 1: bcm2835 Headphones (OUTPUT)
# Device 2: USB Audio Device (INPUT, OUTPUT)

# Configure with separate input and output devices
audio_manager = AudioManager(
    input_device_index=0,   # USB Microphone
    output_device_index=1   # 3.5mm jack headphones
)

# Example 2: Using default devices (if not specified)
# audio_manager = AudioManager()  # Will use system defaults

# Example 3: Test the configuration
if __name__ == "__main__":
    print("Testing audio configuration...")
    
    # List available devices
    print("\nInput Devices:")
    for device in audio_manager.get_input_devices():
        print(f"  [{device['index']}] {device['name']} ({device['channels']} channels)")
    
    print("\nOutput Devices:")
    for device in audio_manager.get_output_devices():
        print(f"  [{device['index']}] {device['name']} ({device['channels']} channels)")
    
    print(f"\nConfigured Input Device: {audio_manager.input_device_index}")
    print(f"Configured Output Device: {audio_manager.output_device_index}")
    
    # Clean up
    audio_manager.cleanup()