#!/usr/bin/env python3
"""
Interrupt-based button-relay control (more responsive)
- GPIO25: Button input (connected to GND)
- GPIO8: Relay output (HIGH when button pressed, LOW when released)
"""

import RPi.GPIO as GPIO
import time

# Pin definitions
BUTTON_PIN = 25
RELAY_PIN = 8

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(RELAY_PIN, GPIO.OUT)

# Initialize relay to OFF
GPIO.output(RELAY_PIN, GPIO.LOW)

def button_pressed(channel):
    """Callback when button is pressed"""
    print("🔘 Button PRESSED - Relay ON")
    GPIO.output(RELAY_PIN, GPIO.HIGH)

def button_released(channel):
    """Callback when button is released"""
    print("🔲 Button RELEASED - Relay OFF")
    GPIO.output(RELAY_PIN, GPIO.LOW)

def main():
    print("Interrupt-based Button-Relay Control Ready!")
    print("- Press GPIO25 button to activate relay (GPIO8 HIGH)")
    print("- Release GPIO25 button to deactivate relay (GPIO8 LOW)")
    print("Press Ctrl+C to exit\n")
    
    try:
        # Setup interrupts for both edges
        GPIO.add_event_detect(BUTTON_PIN, GPIO.FALLING, 
                             callback=button_pressed, 
                             bouncetime=50)  # Button press
        
        GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING, 
                             callback=button_released, 
                             bouncetime=50)  # Button release
        
        # Keep running
        while True:
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        GPIO.output(RELAY_PIN, GPIO.LOW)  # Ensure relay is off
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()