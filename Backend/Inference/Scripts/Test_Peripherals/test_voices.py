
import pyttsx3

def test_voices():
    engine = pyttsx3.init()
    voices = engine.getProperty('voices')
    
    print(f"Found {len(voices)} voices.")
    
    for i, voice in enumerate(voices):
        print(f"Voice {i}: {voice.name} - ID: {voice.id}")
        engine.setProperty('voice', voice.id)
        engine.say(f"Testing voice {i}. walk sense online.")
        engine.runAndWait()

if __name__ == "__main__":
    test_voices()
