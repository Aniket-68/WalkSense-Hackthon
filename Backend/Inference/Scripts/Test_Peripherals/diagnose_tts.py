# Alternative TTS using Windows SAPI directly via comtypes
# This is a fallback if pyttsx3 fails

import sys
import os

def test_pyttsx3():
    """Test if pyttsx3 is working"""
    print("Testing pyttsx3...")
    try:
        import pyttsx3
        engine = pyttsx3.init('sapi5', debug=False)
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 1.0)
        
        voices = engine.getProperty('voices')
        print(f"Found {len(voices)} voices:")
        for i, voice in enumerate(voices):
            print(f"  {i}: {voice.name} ({voice.id})")
        
        print("\nTesting speech...")
        engine.say("Hello, this is a test of pyttsx3")
        engine.runAndWait()
        print("✓ pyttsx3 is working!")
        return True
    except Exception as e:
        print(f"✗ pyttsx3 failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_win32com():
    """Test if win32com SAPI is working"""
    print("\nTesting win32com SAPI...")
    try:
        import win32com.client
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Rate = 0  # -10 to 10
        speaker.Volume = 100  # 0 to 100
        
        voices = speaker.GetVoices()
        print(f"Found {voices.Count} voices:")
        for i in range(voices.Count):
            voice = voices.Item(i)
            print(f"  {i}: {voice.GetDescription()}")
        
        print("\nTesting speech...")
        speaker.Speak("Hello, this is a test of win32com SAPI")
        print("✓ win32com SAPI is working!")
        return True
    except Exception as e:
        print(f"✗ win32com SAPI failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_powershell():
    """Test if PowerShell Add-Type SAPI is working"""
    print("\nTesting PowerShell SAPI...")
    try:
        import subprocess
        
        ps_script = """
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = 0
$synth.Volume = 100
$synth.Speak("Hello, this is a test of PowerShell SAPI")
"""
        
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("✓ PowerShell SAPI is working!")
            return True
        else:
            print(f"✗ PowerShell SAPI failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ PowerShell SAPI failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("TTS Diagnostics for Windows")
    print("=" * 60)
    
    results = {
        "pyttsx3": test_pyttsx3(),
        "win32com": test_win32com(),
        "powershell": test_powershell()
    }
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    for method, success in results.items():
        status = "✓ WORKING" if success else "✗ FAILED"
        print(f"{method:15} : {status}")
    
    print("\nRecommendation:")
    if results["pyttsx3"]:
        print("  Use pyttsx3 (current implementation)")
    elif results["win32com"]:
        print("  Switch to win32com.client SAPI")
        print("  Install: pip install pywin32")
    elif results["powershell"]:
        print("  Switch to PowerShell subprocess method")
    else:
        print("  All TTS methods failed. Check Windows audio settings.")
