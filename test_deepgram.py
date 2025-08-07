#!/usr/bin/env python3
"""Test Deepgram connection"""

import os
import time
import logging
from dotenv import load_dotenv

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Reduce websocket logging noise
logging.getLogger("websocket").setLevel(logging.INFO)

# Load environment
load_dotenv()

# Test basic connection
import websocket
import json

def test_deepgram():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        print("No DEEPGRAM_API_KEY found in environment")
        return
        
    print(f"API Key found: {api_key[:8]}...{api_key[-4:]}")
    
    # Test simple WebSocket connection
    url = "wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=16000&channels=1"
    
    def on_open(ws):
        print("WebSocket opened successfully!")
        ws.close()
        
    def on_error(ws, error):
        print(f"WebSocket error: {error}")
        print(f"Error type: {type(error)}")
        
    def on_close(ws, close_status_code, close_msg):
        print(f"WebSocket closed: {close_status_code} - {close_msg}")
    
    try:
        ws = websocket.WebSocketApp(
            url,
            header={
                "Authorization": f"Token {api_key}"
            },
            on_open=on_open,
            on_error=on_error,
            on_close=on_close
        )
        
        print("Attempting to connect to Deepgram...")
        ws.run_forever(ping_interval=5, ping_timeout=2)
        
    except Exception as e:
        print(f"Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_deepgram()