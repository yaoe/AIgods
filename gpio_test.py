#!/usr/bin/env python3
"""
Test multiple GPIO pins to find working ones
"""

import RPi.GPIO as GPIO
import time

# Test these pins
TEST_PINS = [23, 24, 25, 21]

GPIO.setmode(GPIO.BCM)

print("Testing multiple GPIO pins...")
print("Connect your button to GND and try each pin:")

for pin in TEST_PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    print(f"GPIO{pin}: {GPIO.input(pin)}")

print("\nNow press your button and see which pin changes...")

try:
    while True:
        line = f"States: "
        for pin in TEST_PINS:
            state = GPIO.input(pin)
            line += f"GPIO{pin}:{state} "
        print(f"\r{line}", end="", flush=True)
        time.sleep(0.1)
        
except KeyboardInterrupt:
    print("\nDone!")
finally:
    GPIO.cleanup()
