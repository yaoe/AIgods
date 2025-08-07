#!/bin/bash
# Script to set audio output on Raspberry Pi

echo "Setting audio output to headphones..."

# Method 1: Using raspi-config command
# 1 = Auto, 2 = Headphones, 3 = HDMI
sudo raspi-config nonint do_audio 2

# Method 2: Using amixer (alternative)
# amixer cset numid=3 1  # 0=auto, 1=headphones, 2=hdmi

# Method 3: For newer Raspberry Pi OS with PulseAudio
# pacmd set-default-sink alsa_output.platform-bcm2835_audio.analog-stereo

echo "Audio output set to headphones"
echo "Current audio devices:"
aplay -l