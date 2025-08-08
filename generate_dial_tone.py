#!/usr/bin/env python3
"""Generate a dial tone audio file"""

import numpy as np
import wave

def generate_dial_tone(duration=3.0, sample_rate=44100):
    """Generate US dial tone (350Hz + 440Hz)"""
    t = np.linspace(0, duration, int(sample_rate * duration))
    
    # US dial tone frequencies
    freq1 = 350  # Hz
    freq2 = 440  # Hz
    
    # Generate sine waves
    tone = np.sin(2 * np.pi * freq1 * t) + np.sin(2 * np.pi * freq2 * t)
    
    # Normalize to prevent clipping
    tone = tone / 2.0
    
    # Convert to 16-bit PCM
    audio = (tone * 32767).astype(np.int16)
    
    # Save as WAV file
    with wave.open('sounds/dial_tone.wav', 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)   # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio.tobytes())
    
    print("Dial tone generated: sounds/dial_tone.wav")

if __name__ == "__main__":
    import os
    os.makedirs("sounds", exist_ok=True)
    generate_dial_tone()