#!/usr/bin/env python3
"""
Script to list all available audio input and output devices
"""

import pyaudio

def list_audio_devices():
    """List all available audio devices with their indices"""
    p = pyaudio.PyAudio()
    
    print("=" * 60)
    print("AUDIO DEVICES")
    print("=" * 60)
    
    # Get default devices info
    try:
        default_input = p.get_default_input_device_info()
        print(f"\nDefault Input Device: {default_input['name']} (Index: {default_input['index']})")
    except:
        print("\nNo default input device found")
    
    try:
        default_output = p.get_default_output_device_info()
        print(f"Default Output Device: {default_output['name']} (Index: {default_output['index']})")
    except:
        print("No default output device found")
    
    print("\n" + "-" * 60)
    print("ALL AVAILABLE DEVICES:")
    print("-" * 60)
    
    # List all devices
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        
        # Determine device type
        device_type = []
        if info['maxInputChannels'] > 0:
            device_type.append("INPUT")
        if info['maxOutputChannels'] > 0:
            device_type.append("OUTPUT")
        
        print(f"\nDevice {i}: {info['name']}")
        print(f"  Type: {', '.join(device_type)}")
        print(f"  Host API: {p.get_host_api_info_by_index(info['hostApi'])['name']}")
        print(f"  Sample Rate: {info['defaultSampleRate']} Hz")
        print(f"  Input Channels: {info['maxInputChannels']}")
        print(f"  Output Channels: {info['maxOutputChannels']}")
        
        # Check if it's likely a USB device (common USB audio device names)
        name_lower = info['name'].lower()
        if any(usb_hint in name_lower for usb_hint in ['usb', 'c-media', 'plantronics', 'logitech', 'webcam']):
            print("  ** Likely USB Device **")
        
        # Check if it's likely a 3.5mm jack (common names)
        if any(jack_hint in name_lower for jack_hint in ['headphone', 'speaker', 'realtek', 'built-in', 'analog', 'hda']):
            print("  ** Likely 3.5mm Jack Device **")
    
    p.terminate()
    
    print("\n" + "=" * 60)
    print("To use a specific device, set the device index in AudioManager:")
    print("  audio_manager = AudioManager(input_device_index=X, output_device_index=Y)")
    print("=" * 60)


if __name__ == "__main__":
    list_audio_devices()