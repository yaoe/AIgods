#!/usr/bin/env python3
"""
Simple relay test - toggle every 2 seconds
Use this to test if your relay is working
"""

import RPi.GPIO as GPIO
import time

RELAY_PIN = 8

GPIO.setmode(GPIO.BCM)
GPIO.setup(RELAY_PIN, GPIO.OUT)

print("Relay test - GPIO8 will toggle every 2 seconds")
print("Listen for relay clicking sound")
print("Press Ctrl+C to exit")

try:
    while True:
        print("Relay ON")
        GPIO.output(RELAY_PIN, GPIO.HIGH)
        time.sleep(2)
        
        print("Relay OFF")
        GPIO.output(RELAY_PIN, GPIO.LOW)
        time.sleep(2)
        
except KeyboardInterrupt:
    print("\nExiting...")
    GPIO.output(RELAY_PIN, GPIO.LOW)
finally:
    GPIO.cleanup()