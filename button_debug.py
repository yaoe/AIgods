#!/usr/bin/env python3
"""
Debug button connection - shows current state
"""

import RPi.GPIO as GPIO
import time

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(23, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("Button debug - showing GPIO23 state every second")
print("Should show 1 normally, 0 when pressed")
print("Press Ctrl+C to exit")

try:
    while True:
        state = GPIO.input(23)
        print(f"GPIO23 state: {state} ({'HIGH' if state else 'LOW'})")
        time.sleep(1)
        
except KeyboardInterrupt:
    print("\nBye!")
finally:
    GPIO.cleanup()