#!/usr/bin/env python3
"""List all audio devices on the system"""

import pyaudio

def list_audio_devices():
    p = pyaudio.PyAudio()
    
    print("=" * 60)
    print("AUDIO DEVICES AVAILABLE:")
    print("=" * 60)
    
    # Get default devices
    try:
        default_input = p.get_default_input_device_info()
        default_output = p.get_default_output_device_info()
        print(f"\nDefault Input Device: {default_input['name']} (Index: {default_input['index']})")
        print(f"Default Output Device: {default_output['name']} (Index: {default_output['index']})")
    except:
        print("\nCould not get default devices")
    
    print("\n" + "-" * 60)
    print("ALL DEVICES:")
    print("-" * 60)
    
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        print(f"\nDevice {i}: {info['name']}")
        print(f"  - Max Input Channels: {info['maxInputChannels']}")
        print(f"  - Max Output Channels: {info['maxOutputChannels']}")
        print(f"  - Default Sample Rate: {info['defaultSampleRate']}")
        
        # Mark device capabilities
        capabilities = []
        if info['maxInputChannels'] > 0:
            capabilities.append("INPUT")
        if info['maxOutputChannels'] > 0:
            capabilities.append("OUTPUT")
        print(f"  - Capabilities: {', '.join(capabilities)}")
    
    p.terminate()

if __name__ == "__main__":
    list_audio_devices()