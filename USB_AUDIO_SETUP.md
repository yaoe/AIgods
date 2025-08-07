# USB Audio Setup for Raspberry Pi

## Option 1: USB Microphone
Plug in any USB microphone and it should work immediately. Test with:
```bash
lsusb  # Should show your USB device
arecord -l  # Should now show a capture device
```

## Option 2: USB Sound Card
Get a cheap USB sound adapter (usually $5-10) that has both mic input and audio output.

Popular options:
- Sabrent USB External Stereo Sound Adapter
- UGREEN USB Sound Card
- Any generic "USB Audio Adapter"

## Option 3: USB Headset
USB headsets with built-in sound cards work great and give you both input and output.

## After Connecting USB Audio:

1. Check it's detected:
```bash
arecord -l
# Should show something like:
# card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]
```

2. Test recording:
```bash
arecord -D plughw:1,0 -d 5 test.wav
aplay test.wav
```

3. Update the code to use the USB device (usually device 1):
```python
# In main.py
self.audio_manager = AudioManager(
    output_device_index=1,  # Headphones
    input_device_index=1    # USB mic
)
```