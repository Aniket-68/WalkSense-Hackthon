# audio/speak.py
import sys
import pyttsx3
import os
import io

# Force UTF-8 for Pipes (Windows Fix)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')

def init_engine():
    """Initialize the engine once"""
    try:
        # Add project root to path so speak.py can find 'utils'
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.append(project_root)

        from Infrastructure.config import Config
        
        provider = Config.get("tts.active_provider", "pyttsx3")
        config_path = f"tts.providers.{provider}"
        
        rate = Config.get(f"{config_path}.rate", 150)
        voice_name = Config.get(f"{config_path}.voice", "default")
        
        engine = pyttsx3.init()
        engine.setProperty('rate', rate)
        engine.setProperty('volume', 1.0)
        
        # Voice Selection - Do this ONCE during init
        voices = engine.getProperty('voices')
        
        if voice_name == "default":
            # Prefer Zira > David > First Available
            selected = None
            for v in voices:
                if "zira" in v.name.lower():
                    selected = v.id
                    print(f"[TTS] Selected voice: {v.name}", file=sys.stderr)
                    break
            if not selected:
                for v in voices:
                    if "david" in v.name.lower():
                        selected = v.id
                        print(f"[TTS] Selected voice: {v.name}", file=sys.stderr)
                        break
            if selected:
                engine.setProperty('voice', selected)
        else:
            # User specified a voice name
            for v in voices:
                if voice_name.lower() in v.name.lower():
                    engine.setProperty('voice', v.id)
                    print(f"[TTS] Selected voice: {v.name}", file=sys.stderr)
                    break
        
        return engine
    except Exception as e:
        print(f"[SPEAK.PY ERROR] Init failed: {str(e)}", file=sys.stderr)
        return None

def process_input(engine):
    """Read lines from stdin and speak them"""
    sys.stdout.write("READY\n")
    sys.stdout.flush()
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            text = line.strip()
            if text:
                engine.say(text)
                engine.runAndWait()
                sys.stdout.write("DONE\n")
                sys.stdout.flush()
                
        except Exception as e:
            print(f"[SPEAK.PY ERROR] Loop failed: {str(e)}", file=sys.stderr)
            break

if __name__ == "__main__":
    # Hybrid mode: If args are provided, speak once (backward compatibility). 
    # If no args, enter persistent loop mode.
    engine = init_engine()
    
    if engine:
        if len(sys.argv) > 1:
            text = " ".join(sys.argv[1:])
            engine.say(text)
            engine.runAndWait()
        else:
            process_input(engine)
