#!/usr/bin/env python3
"""
Integrated GPIO Control Script
Combines:
- Button detection (GPIO21 - mute button)
- Button-relay control (GPIO25 button -> GPIO8 relay)  
- Pulse counter (GPIO23 enable + GPIO24 pulse)
"""

import RPi.GPIO as GPIO
import time

# Pin definitions
PHONE_HANDLE_PIN = 21     # Phone handle up/down sensor (vert jaune)
RELAY_BUTTON_PIN = 25     # Button that controls relay
RELAY_PIN = 8             # Relay output
PULSE_ENABLE_PIN = 23     # Enable pulse counting (orange/jaune)
PULSE_INPUT_PIN = 24      # Pulse input (marron rouge)

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(PHONE_HANDLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(RELAY_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.setup(PULSE_ENABLE_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(PULSE_INPUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Initialize relay to OFF
GPIO.output(RELAY_PIN, GPIO.LOW)

def main():
    print("🔧 Integrated GPIO Control System Ready!")
    print("=" * 50)
    print("📋 Functions:")
    print("  ☎️  GPIO21: Phone handle up/down sensor")
    print("  🔌 GPIO25: Relay control button -> GPIO8 relay")
    print("  📊 GPIO23: Hold to enable pulse counting")
    print("  💥 GPIO24: Pulse input (while GPIO23 held)")
    print("=" * 50)
    print("Press Ctrl+C to exit\n")
    
    # State tracking for all functions
    last_phone_handle_state = True
    last_relay_button_state = True
    last_pulse_enable_state = True
    last_pulse_state = True
    
    # Pulse counter variables
    pulse_count = 0
    counting_active = False
    
    try:
        while True:
            # Read current states
            phone_handle_state = GPIO.input(PHONE_HANDLE_PIN)
            relay_button_state = GPIO.input(RELAY_BUTTON_PIN)
            pulse_enable_state = GPIO.input(PULSE_ENABLE_PIN)
            pulse_state = GPIO.input(PULSE_INPUT_PIN)
            
            # 1. PHONE HANDLE DETECTION (GPIO21)
            # Handle picked up (goes from HIGH to LOW)
            if last_phone_handle_state == True and phone_handle_state == False:
                print("☎️  Phone handle PICKED UP!")
                
            # Handle put down (goes from LOW to HIGH)
            elif last_phone_handle_state == False and phone_handle_state == True:
                print("📞 Phone handle PUT DOWN!")
                
            # 2. RELAY CONTROL (GPIO25 -> GPIO8)
            # Button just pressed
            if last_relay_button_state == True and relay_button_state == False:
                print("🔌 Relay button PRESSED - Relay ON")
                GPIO.output(RELAY_PIN, GPIO.HIGH)
                
            # Button just released  
            elif last_relay_button_state == False and relay_button_state == True:
                print("🔌 Relay button RELEASED - Relay OFF")
                GPIO.output(RELAY_PIN, GPIO.LOW)
            
            # 3. PULSE COUNTER (GPIO23 enable + GPIO24 pulses)
            # Enable button just pressed
            if last_pulse_enable_state == True and pulse_enable_state == False:
                print("📊 Pulse counting ENABLED - start pulsing GPIO24")
                counting_active = True
                pulse_count = 0
                
            # Enable button just released
            elif last_pulse_enable_state == False and pulse_enable_state == True:
                print(f"📊 Pulse counting DISABLED - Total pulses: {pulse_count}")
                counting_active = False
                pulse_count = 0
                print()  # Empty line for readability
                
            # Count pulses only when enabled
            if counting_active:
                # Detect falling edge on pulse pin (button press)
                if last_pulse_state == True and pulse_state == False:
                    pulse_count += 1
                    print(f"💥 Pulse {pulse_count}")
            
            # Update previous states
            last_phone_handle_state = phone_handle_state
            last_relay_button_state = relay_button_state
            last_pulse_enable_state = pulse_enable_state
            last_pulse_state = pulse_state
            
            time.sleep(0.01)  # 10ms polling for all functions
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        GPIO.output(RELAY_PIN, GPIO.LOW)  # Ensure relay is off
        print("✅ Relay turned off, GPIO cleaned up")
    finally:
        GPIO.cleanup()

if __name__ == "__main__":
    main()