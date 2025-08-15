#!/usr/bin/env python3
"""
Debug script to see what's available in the ElevenLabs library
"""

import os
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

try:
    elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    
    print("ElevenLabs client created successfully!")
    print(f"Client type: {type(elevenlabs)}")
    print(f"Available attributes: {dir(elevenlabs)}")
    
    if hasattr(elevenlabs, 'text_to_speech'):
        tts = elevenlabs.text_to_speech
        print(f"\ntext_to_speech type: {type(tts)}")
        print(f"text_to_speech attributes: {dir(tts)}")
        
        # Check for different possible method names
        methods_to_check = ['stream', 'convert', 'generate', 'create']
        for method in methods_to_check:
            if hasattr(tts, method):
                print(f"✅ Found method: {method}")
            else:
                print(f"❌ Missing method: {method}")
    
    # Also check if there's a generate method on the main client
    if hasattr(elevenlabs, 'generate'):
        print(f"\n✅ Found generate method on main client")
        print(f"Generate method: {elevenlabs.generate}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()