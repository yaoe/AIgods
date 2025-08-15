#!/usr/bin/env python3
"""
Simple test to find the correct ElevenLabs API method
"""

import os
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Try different import patterns
try:
    # Pattern 1: Direct import
    from elevenlabs import generate, Voice, VoiceSettings
    print("✅ Pattern 1: Direct import successful")
    
    # Test with direct generate function
    print("🎭 Testing direct generate function...")
    
    audio = generate(
        text="Hello, this is a test of ElevenLabs.",
        voice=Voice(voice_id="o7lPjDgzlF8ZloHzVPeK"),
        model="eleven_multilingual_v2"
    )
    print(f"✅ Direct generate worked! Audio length: {len(audio)} bytes")
    
except ImportError as e:
    print(f"❌ Pattern 1 failed: {e}")
    
    # Pattern 2: Client import
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import VoiceSettings
        
        print("✅ Pattern 2: Client import successful")
        
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        print(f"Client methods: {[m for m in dir(client) if not m.startswith('_')]}")
        
        # Try different methods
        if hasattr(client, 'generate'):
            print("🎭 Testing client.generate()...")
            audio = client.generate(
                text="Hello, this is a test.",
                voice="o7lPjDgzlF8ZloHzVPeK",
                model="eleven_multilingual_v2"
            )
            print(f"✅ Client generate worked! Audio length: {len(audio)} bytes")
        
    except Exception as e2:
        print(f"❌ Pattern 2 failed: {e2}")

# Pattern 3: Check what's actually available
try:
    import elevenlabs
    print(f"\n📋 ElevenLabs module contents: {dir(elevenlabs)}")
    
    # Check version
    if hasattr(elevenlabs, '__version__'):
        print(f"📌 ElevenLabs version: {elevenlabs.__version__}")
    
except Exception as e:
    print(f"❌ Could not import elevenlabs: {e}")