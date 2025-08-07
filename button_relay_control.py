#!/usr/bin/env python3
"""
Button-controlled relay script
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

def main():
    print("Button-Relay Control Ready!")
    print("- Press GPIO25 button to activate relay (GPIO8 HIGH)")
    print("- Release GPIO25 button to deactivate relay (GPIO8 LOW)")
    print("Press Ctrl+C to exit\n")
    
    last_button_state = True  # Button not pressed initially
    
    try:
        while True:
            current_button_state = GPIO.input(BUTTON_PIN)
            
            # Button just pressed (HIGH to LOW transition)
            if last_button_state == True and current_button_state == False:
                print("🔘 Button PRESSED - Relay ON")
                GPIO.output(RELAY_PIN, GPIO.HIGH)
                
            # Button just released (LOW to HIGH transition)
            elif last_button_state == False and current_button_state == True:
                print("🔲 Button RELEASED - Relay OFF")
                GPIO.output(RELAY_PIN, GPIO.LOW)
            
            last_button_state = current_button_state
            time.sleep(0.01)  # 10ms polling
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        GPIO.output(RELAY_PIN, GPIO.LOW)  # Ensure relay is off
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()