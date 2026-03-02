"""Simple TTS test to diagnose issues"""
import sys
import os
import time

# Add project root to path - go up two levels from Test_Peripherals to Inference
inference_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, inference_root)

from Interaction_Layer.tts import TTSEngine

print("Initializing TTS Engine...")
tts = TTSEngine()

print("Waiting for TTS thread to start...")
time.sleep(2)

print("Testing TTS with simple message...")
tts.speak("Hello, this is a test message")

print("Waiting for speech to complete...")
time.sleep(5)

print("Testing TTS with longer message...")
tts.speak("This is a longer test message to verify that text to speech is working correctly")

print("Waiting for speech to complete...")
time.sleep(5)

print("Test complete!")
