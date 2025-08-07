#!/usr/bin/env python3
"""
Simple button detection script for Raspberry Pi
Button connected between GND (pin 6) and GPIO23 (pin 16)
"""

import RPi.GPIO as GPIO
import time

# Setup
BUTTON_PIN = 23
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def button_pressed():
    """Callback when button is pressed"""
    print("Button pressed!")

def main():
    print("Button detection running...")
    print("Press the button (GPIO23 to GND)")
    print("Press Ctrl+C to exit")
    
    try:
        # Add event detection
        GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, 
                             callback=lambda channel: button_pressed(),
                             bouncetime=200)  # 200ms debounce
        
        # Keep running
        while True:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()