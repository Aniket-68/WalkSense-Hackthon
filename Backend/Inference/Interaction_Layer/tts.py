# audio/tts.py

import subprocess
import sys
import os
import threading
import queue
import platform

class TTSEngine:
    def __init__(self):
        """Initialize TTS with threaded engine"""
        self.text_queue = queue.Queue()
        self.running = True
        self.engine = None
        self.use_win32com = False
        
        # Start TTS thread
        self.thread = threading.Thread(target=self._tts_worker, daemon=True)
        self.thread.start()

    def _tts_worker(self):
        """Background thread that processes TTS requests"""
        try:
            from Infrastructure.config import Config
            from loguru import logger
            
            # On Windows, use win32com.client for better threading support
            if platform.system() == 'Windows':
                try:
                    import win32com.client
                    self.engine = win32com.client.Dispatch("SAPI.SpVoice")
                    self.use_win32com = True
                    
                    # Configure from config
                    provider = Config.get("tts.active_provider", "pyttsx3")
                    config_path = f"tts.providers.{provider}"
                    
                    rate = Config.get(f"{config_path}.rate", 150)
                    volume = Config.get(f"{config_path}.volume", 1.0)
                    
                    # Win32com uses different scale: Rate is -10 to 10, Volume is 0 to 100
                    # Convert from pyttsx3 scale
                    win32_rate = int((rate - 150) / 25)  # 150 wpm is 0, each 25 wpm is 1 step
                    win32_rate = max(-10, min(10, win32_rate))
                    win32_volume = int(volume * 100)
                    
                    self.engine.Rate = win32_rate
                    self.engine.Volume = win32_volume
                    
                    # List available voices
                    voices = self.engine.GetVoices()
                    logger.info(f"[TTS] Found {voices.Count} voices using win32com")
                    
                    # Try to find and set Zira voice
                    voice_name = Config.get(f"{config_path}.voice", "default")
                    if voice_name == "default":
                        for i in range(voices.Count):
                            voice = voices.Item(i)
                            desc = voice.GetDescription()
                            if "zira" in desc.lower():
                                self.engine.Voice = voice
                                logger.info(f"[TTS] Using voice: {desc}")
                                break
                        else:
                            logger.info(f"[TTS] Using default voice")
                    
                    logger.info(f"[TTS] ✓ Worker thread started with win32com (Rate: {win32_rate}, Volume: {win32_volume})")
                    
                except ImportError:
                    logger.warning("[TTS] win32com not available, falling back to pyttsx3")
                    self.use_win32com = False
                    self._init_pyttsx3(Config)
            else:
                # Non-Windows: use pyttsx3
                self._init_pyttsx3(Config)
            
            # Process queue
            while self.running:
                try:
                    text = self.text_queue.get(timeout=0.5)
                    if text:
                        logger.info(f"[TTS] 🔊 Speaking: {text}")
                        try:
                            if self.use_win32com:
                                # Win32com method - more reliable on Windows
                                self.engine.Speak(text)
                            else:
                                # pyttsx3 method
                                self.engine.say(text)
                                self.engine.runAndWait()
                            logger.info("[TTS] ✓ Finished speaking")
                        except Exception as speak_error:
                            logger.error(f"[TTS] ❌ Speech failed: {speak_error}")
                            import traceback
                            traceback.print_exc()
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"[TTS] Worker loop error: {e}")
                    import traceback
                    traceback.print_exc()
                    
        except Exception as e:
            from loguru import logger
            logger.error(f"[TTS] Worker thread failed: {e}")
            import traceback
            traceback.print_exc()
    
    def _init_pyttsx3(self, Config):
        """Initialize pyttsx3 engine (fallback for non-Windows or if win32com fails)"""
        from loguru import logger
        import pyttsx3
        
        try:
            if platform.system() == 'Windows':
                logger.info("[TTS] Initializing with pyttsx3 sapi5 driver")
                self.engine = pyttsx3.init('sapi5', debug=False)
            else:
                self.engine = pyttsx3.init()
            
            provider = Config.get("tts.active_provider", "pyttsx3")
            config_path = f"tts.providers.{provider}"
            
            rate = Config.get(f"{config_path}.rate", 150)
            volume = Config.get(f"{config_path}.volume", 1.0)
            voice_name = Config.get(f"{config_path}.voice", "default")
            
            self.engine.setProperty('rate', rate)
            self.engine.setProperty('volume', volume)
            
            voices = self.engine.getProperty('voices')
            logger.info(f"[TTS] Found {len(voices)} voices using pyttsx3")
            
            if voice_name == "default":
                for v in voices:
                    if "zira" in v.name.lower():
                        self.engine.setProperty('voice', v.id)
                        logger.info(f"[TTS] Using voice: {v.name}")
                        break
                else:
                    if voices:
                        self.engine.setProperty('voice', voices[0].id)
                        logger.info(f"[TTS] Using default voice: {voices[0].name}")
            
            logger.info("[TTS] ✓ Worker thread started with pyttsx3")
            
        except Exception as e:
            logger.error(f"[TTS] Failed to initialize pyttsx3: {e}")
            raise

    def speak(self, text):
        """Queue text for speaking"""
        if text:
            from loguru import logger
            logger.info(f"AI: {text}")
            print(f"[TTS] SPEAKING: {text}")
            
            try:
                # Clear queue and add new text (interruption behavior)
                while not self.text_queue.empty():
                    try:
                        self.text_queue.get_nowait()
                    except queue.Empty:
                        break
                
                self.text_queue.put(text)
            except Exception as e:
                logger.error(f"TTS ERROR: {e}")
            
    def stop(self):
        """Stop current speech"""
        # Clear queue
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
            except queue.Empty:
                break
        
        # Stop engine if possible
        if self.engine:
            try:
                if self.use_win32com:
                    # Win32com doesn't have a stop method, but clearing queue is enough
                    pass
                else:
                    self.engine.stop()
            except:
                pass

    # -----------------------------------------------------------------
    # Server-side synthesis (Option B: stream audio bytes to client)
    # -----------------------------------------------------------------

    def synthesize_to_bytes(self, text: str) -> bytes:
        """Synthesize text to WAV bytes (for remote streaming via /ws/audio).

        Returns raw WAV bytes that can be sent to the browser and decoded
        with ``AudioContext.decodeAudioData()``.

        Strategy:
        1. win32com  → SpFileStream to capture SAPI output to WAV file
        2. pyttsx3   → save_to_file()
        3. fallback  → gTTS (Google Translate TTS) as a last resort
        """
        import tempfile
        import io

        wav_path = os.path.join(tempfile.gettempdir(), f"walksense_tts_{id(self)}.wav")

        try:
            if self.use_win32com and self.engine:
                return self._synth_win32com(text, wav_path)

            if self.engine and not self.use_win32com:
                return self._synth_pyttsx3(text, wav_path)

        except Exception as e:
            from loguru import logger
            logger.warning(f"[TTS] Primary synthesis failed: {e}, trying gTTS fallback")

        # Fallback: gTTS (requires internet, but always works)
        try:
            return self._synth_gtts(text)
        except Exception as e:
            from loguru import logger
            logger.error(f"[TTS] All synthesis methods failed: {e}")
            return b""

    def _synth_win32com(self, text: str, wav_path: str) -> bytes:
        """Synthesize via win32com SAPI → WAV file → bytes."""
        import win32com.client

        # Create a fresh SAPI voice in THIS thread (COM apartment)
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")

        # Open file stream for writing (create flag = 3)
        stream.Open(wav_path, 3)
        voice.AudioOutputStream = stream
        voice.Rate = self.engine.Rate
        voice.Volume = self.engine.Volume
        voice.Speak(text)
        stream.Close()

        with open(wav_path, "rb") as f:
            data = f.read()

        try:
            os.unlink(wav_path)
        except OSError:
            pass

        return data

    def _synth_pyttsx3(self, text: str, wav_path: str) -> bytes:
        """Synthesize via pyttsx3 save_to_file → bytes."""
        import pyttsx3

        # pyttsx3 is not thread-safe — create a temporary engine
        eng = pyttsx3.init()
        eng.setProperty("rate", self.engine.getProperty("rate"))
        eng.setProperty("volume", self.engine.getProperty("volume"))
        eng.save_to_file(text, wav_path)
        eng.runAndWait()
        eng.stop()

        with open(wav_path, "rb") as f:
            data = f.read()

        try:
            os.unlink(wav_path)
        except OSError:
            pass

        return data

    @staticmethod
    def _synth_gtts(text: str) -> bytes:
        """Synthesize via Google Translate TTS (MP3 bytes)."""
        import io
        from gtts import gTTS

        mp3_buf = io.BytesIO()
        tts = gTTS(text=text, lang="en", slow=False)
        tts.write_to_fp(mp3_buf)
        return mp3_buf.getvalue()

