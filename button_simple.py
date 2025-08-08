#!/usr/bin/env python3
"""
Even simpler button detection - polling version
"""

import RPi.GPIO as GPIO
import time

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(21, GPIO.IN, pull_up_down=GPIO.PUD_UP) # mute button (vert jaune)

print("Button test ready. Press button to see message.")

try:
    last_state = True
    while True:
        current_state = GPIO.input(21)
        
        # Button pressed (goes from HIGH to LOW)
        if last_state == True and current_state == False:
            print("🔘 Button pressed!")
            
        last_state = current_state
        time.sleep(0.05)  # Check every 50ms
        
except KeyboardInterrupt:
    print("\nBye!")
finally:
    GPIO.cleanup()
