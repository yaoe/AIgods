#!/usr/bin/env python3
"""Test Deepgram speech recognition with live microphone input"""

import os
import time
import json
import pyaudio
import threading
import websocket
from dotenv import load_dotenv

# Load environment
load_dotenv()

class DeepgramSpeechTest:
    def __init__(self):
        self.api_key = os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("No DEEPGRAM_API_KEY found in environment")
        
        self.ws = None
        self.audio_stream = None
        self.p = None
        self.is_recording = False
        self.transcripts = []
        
    def on_open(self, ws):
        print("✓ Connected to Deepgram")
        print("🎤 Speak now! (Recording for 10 seconds)")
        self.start_audio_recording()
        
    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if 'channel' in data:
                transcript = data['channel']['alternatives'][0]['transcript']
                if transcript.strip():
                    confidence = data['channel']['alternatives'][0]['confidence']
                    print(f"📝 Transcript: '{transcript}' (confidence: {confidence:.2f})")
                    self.transcripts.append(transcript)
        except Exception as e:
            print(f"Error parsing message: {e}")
            
    def on_error(self, ws, error):
        print(f"❌ WebSocket error: {error}")
        
    def on_close(self, ws, close_status_code, close_msg):
        print("🔌 WebSocket closed")
        self.stop_audio_recording()
        
    def start_audio_recording(self):
        """Start recording audio and streaming to Deepgram"""
        self.is_recording = True
        
        def audio_thread():
            try:
                self.p = pyaudio.PyAudio()
                
                # Find working input device
                input_device = None
                for i in range(self.p.get_device_count()):
                    info = self.p.get_device_info_by_index(i)
                    if info['maxInputChannels'] > 0:
                        input_device = i
                        break
                        
                if input_device is None:
                    print("❌ No input device found")
                    return
                    
                print(f"🎙️  Using input device: {self.p.get_device_info_by_index(input_device)['name']}")
                
                self.audio_stream = self.p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    input_device_index=input_device,
                    frames_per_buffer=1024
                )
                
                # Record for 10 seconds
                start_time = time.time()
                while self.is_recording and (time.time() - start_time) < 10:
                    data = self.audio_stream.read(1024, exception_on_overflow=False)
                    if self.ws and self.ws.sock and self.ws.sock.connected:
                        self.ws.send(data, websocket.ABNF.OPCODE_BINARY)
                    time.sleep(0.01)
                    
                # Signal end of audio
                if self.ws and self.ws.sock and self.ws.sock.connected:
                    self.ws.send('{"type": "CloseStream"}')
                    
            except Exception as e:
                print(f"❌ Audio error: {e}")
            finally:
                self.stop_audio_recording()
                
        threading.Thread(target=audio_thread, daemon=True).start()
        
    def stop_audio_recording(self):
        """Stop audio recording"""
        self.is_recording = False
        if self.audio_stream:
            try:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
            except:
                pass
        if self.p:
            try:
                self.p.terminate()
            except:
                pass
                
    def test_speech_recognition(self):
        """Run the speech recognition test"""
        print(f"🔑 API Key: {self.api_key[:8]}...{self.api_key[-4:]}")
        
        url = "wss://api.deepgram.com/v1/listen?encoding=linear16&sample_rate=16000&channels=1&interim_results=false"
        
        try:
            self.ws = websocket.WebSocketApp(
                url,
                header={
                    "Authorization": f"Token {self.api_key}"
                },
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            
            print("🔄 Connecting to Deepgram...")
            self.ws.run_forever()
            
            # Wait a moment for final results
            time.sleep(2)
            
            # Show results
            print("\n" + "="*50)
            print("📊 SPEECH RECOGNITION TEST RESULTS")
            print("="*50)
            
            if self.transcripts:
                print("✅ SUCCESS! Deepgram recognized your speech:")
                for i, transcript in enumerate(self.transcripts, 1):
                    print(f"  {i}. {transcript}")
                print(f"\n🎯 Total transcripts received: {len(self.transcripts)}")
            else:
                print("❌ FAILED: No speech was recognized")
                print("\n🔧 Troubleshooting:")
                print("  • Make sure you spoke clearly during the test")
                print("  • Check your microphone is working: python3 test_audio_input.py")
                print("  • Verify your API key is valid")
                print("  • Try speaking louder or closer to the microphone")
                
        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stop_audio_recording()

def main():
    try:
        test = DeepgramSpeechTest()
        test.test_speech_recognition()
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("💡 Make sure DEEPGRAM_API_KEY is set in your .env file")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    main()