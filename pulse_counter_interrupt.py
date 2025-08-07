#!/usr/bin/env python3
"""
Interrupt-based pulse counter (more accurate for fast pulses)
- GPIO23: Enable pin (hold down to count)
- GPIO24: Pulse pin (count pulses while GPIO23 is pressed)
"""

import RPi.GPIO as GPIO
import time

# Pin definitions
ENABLE_PIN = 23
PULSE_PIN = 24

# Global variables
pulse_count = 0
counting_active = False

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(ENABLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PULSE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def pulse_detected(channel):
    """Interrupt callback for pulse detection"""
    global pulse_count, counting_active
    
    if counting_active:
        pulse_count += 1
        print(f"💥 Pulse {pulse_count}")

def main():
    global pulse_count, counting_active
    
    print("Interrupt-based Pulse Counter Ready!")
    print("- Hold GPIO23 button to enable counting")
    print("- Pulse GPIO24 while holding GPIO23")
    print("- Release GPIO23 to see total count")
    print("Press Ctrl+C to exit\n")
    
    # Setup interrupt for pulse detection
    GPIO.add_event_detect(PULSE_PIN, GPIO.FALLING, 
                         callback=pulse_detected, 
                         bouncetime=50)  # 50ms debounce
    
    last_enable_state = True
    
    try:
        while True:
            enable_state = GPIO.input(ENABLE_PIN)
            
            # Check enable button state changes
            if last_enable_state == True and enable_state == False:
                print("🟢 Counting ENABLED - start pulsing GPIO24")
                counting_active = True
                pulse_count = 0
                
            elif last_enable_state == False and enable_state == True:
                print(f"🔴 Counting DISABLED - Total pulses: {pulse_count}")
                counting_active = False
                print()  # Empty line for readability
                
            last_enable_state = enable_state
            time.sleep(0.05)  # Check enable state every 50ms
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()