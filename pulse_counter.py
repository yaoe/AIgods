#!/usr/bin/env python3
"""
Pulse counter with enable/disable control
- GPIO23: Enable pin (hold down to count)
- GPIO24: Pulse pin (count pulses while GPIO23 is pressed)
"""

import RPi.GPIO as GPIO
import time

# Pin definitions
ENABLE_PIN = 23  # Hold this down to enable counting // interupt (orange/jaune)
PULSE_PIN = 24   # Pulses to count // pulase (marron rouge)

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(ENABLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PULSE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def main():
    print("Pulse Counter Ready!")
    print("- Hold GPIO23 button to enable counting")
    print("- Pulse GPIO24 while holding GPIO23")
    print("- Release GPIO23 to see total count")
    print("Press Ctrl+C to exit\n")
    
    pulse_count = 0
    counting_active = False
    last_pulse_state = True
    last_enable_state = True
    
    try:
        while True:
            enable_state = GPIO.input(ENABLE_PIN)
            pulse_state = GPIO.input(PULSE_PIN)
            
            # Check if enable button was just pressed
            if last_enable_state == True and enable_state == False:
                print("🟢 Counting ENABLED - start pulsing GPIO24")
                counting_active = True
                pulse_count = 0
                
            # Check if enable button was just released
            elif last_enable_state == False and enable_state == True:
                print(f"🔴 Counting DISABLED - Total pulses: {pulse_count}")
                counting_active = False
                pulse_count = 0
                
            # Count pulses only when enabled
            if counting_active:
                # Detect falling edge on pulse pin (button press)
                if last_pulse_state == True and pulse_state == False:
                    pulse_count += 1
                    print(f"💥 Pulse {pulse_count}")
            
            last_enable_state = enable_state
            last_pulse_state = pulse_state
            time.sleep(0.01)  # 10ms polling
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()