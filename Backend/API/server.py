"""
FastAPI server for WalkSense.
Provides REST endpoints, WebSocket state streaming, and MJPEG camera feed.

Run with:
    cd backend && python -m api.server
"""

import asyncio
import json
import time
import sys
import os

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, UploadFile
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from loguru import logger

# Ensure backend root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from API.manager import SystemManager

# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

app = FastAPI(title="WalkSense API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Vite dev server + any origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = SystemManager()


# ──────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────

class QueryRequest(BaseModel):
    text: str


# ──────────────────────────────────────────────
# REST Endpoints
# ──────────────────────────────────────────────

@app.post("/api/system/start")
async def system_start():
    """Start the processing pipeline."""
    manager.start()
    return {"status": "started"}


@app.post("/api/system/stop")
async def system_stop():
    """Stop the processing pipeline."""
    manager.stop()
    return {"status": "stopped"}


@app.get("/api/system/status")
async def system_status():
    """Get current system state."""
    return manager.get_state()


@app.post("/api/query")
async def submit_query(req: QueryRequest):
    """Submit a text query to the system."""
    manager.submit_query(req.text)
    return {"status": "submitted", "query": req.text}


@app.post("/api/voice-query")
async def voice_query(audio: UploadFile = File(...)):
    """Accept audio from browser mic, transcribe, and submit as query."""

    try:
        audio_bytes = await audio.read()
        logger.info(f"[VoiceQuery] Received audio: {len(audio_bytes)} bytes, type={audio.content_type}")

        # Run blocking work (ffmpeg + whisper) in thread pool
        text = await asyncio.to_thread(_process_voice_audio, audio_bytes, audio.content_type)

        if not text:
            return JSONResponse(
                status_code=200,
                content={"status": "no_speech", "text": ""}
            )

        # Submit as query
        manager.submit_query(text)
        return {"status": "submitted", "text": text}

    except Exception as e:
        logger.error(f"[VoiceQuery] Error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


def _find_ffmpeg():
    """Find ffmpeg executable, refreshing PATH from system environment if needed."""
    import shutil
    import os
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    # Refresh PATH from system environment (winget installs update registry but not current process)
    system_path = os.environ.get("Path", "")
    fresh_path = os.pathsep.join([
        os.environ.get("SystemRoot", r"C:\Windows") + r"\system32",
        os.environ.get("SystemRoot", r"C:\Windows"),
    ])
    try:
        import winreg
        for root, sub in [(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, r"Environment")]:
            try:
                with winreg.OpenKey(root, sub) as key:
                    val, _ = winreg.QueryValueEx(key, "Path")
                    fresh_path = fresh_path + os.pathsep + val
            except OSError:
                pass
        os.environ["Path"] = fresh_path
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
    except ImportError:
        pass
    return None


def _process_voice_audio(audio_bytes: bytes, content_type: str) -> Optional[str]:
    """Convert audio to WAV and transcribe. Runs in thread pool."""
    import tempfile
    import subprocess

    # Convert to WAV if needed (browser sends WebM/OGG)
    content_type = content_type or ""
    if "wav" not in content_type:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as src_f:
            src_f.write(audio_bytes)
            src_path = src_f.name

        wav_path = src_path.replace(".webm", ".wav")
        try:
            ffmpeg_path = _find_ffmpeg()
            if not ffmpeg_path:
                logger.error("[VoiceQuery] FFmpeg not found. Please install FFmpeg:")
                logger.error("  1. Download from: https://ffmpeg.org/download.html")
                logger.error("  2. Add to system PATH")
                logger.error("  3. Or install via: winget install FFmpeg")
                raise FileNotFoundError("FFmpeg is required but not installed. Please install FFmpeg and add it to your system PATH.")
                
            # -af "adelay=500|500" pads 500ms silence at the start so
            # Whisper doesn't clip the first word (browser MediaRecorder
            # often loses the first ~200-400ms of audio)
            subprocess.run(
                [ffmpeg_path, "-y", "-i", src_path,
                 "-af", "adelay=500|500,apad=pad_dur=0.3",
                 "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
                capture_output=True, timeout=10
            )
            with open(wav_path, "rb") as wav_f:
                audio_bytes = wav_f.read()
            logger.info(f"[VoiceQuery] Converted to WAV: {len(audio_bytes)} bytes")
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"[VoiceQuery] Audio conversion failed: {e}")
            raise
        finally:
            import os
            for p in [src_path, wav_path]:
                if os.path.exists(p):
                    os.unlink(p)

    # Transcribe
    return manager.transcribe_audio(audio_bytes)


@app.post("/api/system/mute")
async def toggle_mute():
    """Toggle audio mute."""
    muted = manager.toggle_mute()
    return {"muted": muted}


# ──────────────────────────────────────────────
# MJPEG Camera Stream
# ──────────────────────────────────────────────

def _mjpeg_generator():
    """Yield JPEG frames as an MJPEG stream."""
    while True:
        frame = manager.get_annotated_frame()
        if frame is not None:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        else:
            # No frame yet — send a tiny delay
            time.sleep(0.05)


@app.get("/api/camera/feed")
async def camera_feed():
    """MJPEG stream of the annotated camera feed."""
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ──────────────────────────────────────────────
# WebSocket — Browser Camera Frame Ingestion
# ──────────────────────────────────────────────

@app.websocket("/ws/camera")
async def camera_ws(ws: WebSocket):
    """Receive JPEG frames from the browser's getUserMedia camera.

    Used when camera.mode = 'browser' (backend on EC2, no physical camera).
    The frontend sends binary JPEG blobs at ~5 FPS.
    """
    await ws.accept()
    logger.info("[WS/Camera] Browser camera client connected")

    try:
        while True:
            data = await ws.receive_bytes()
            if data:
                manager.push_browser_frame(data)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[WS/Camera] Error: {e}")
    finally:
        logger.info("[WS/Camera] Browser camera client disconnected")


# ──────────────────────────────────────────────
# WebSocket — Real-time state push
# ──────────────────────────────────────────────

connected_clients: set[WebSocket] = set()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Push system state to the frontend every ~200ms."""
    await ws.accept()
    connected_clients.add(ws)
    logger.info(f"[WS] Client connected ({len(connected_clients)} total)")

    try:
        while True:
            state = manager.get_state()
            await ws.send_json(state)
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[WS] Connection error: {e}")
    finally:
        connected_clients.discard(ws)
        logger.info(f"[WS] Client disconnected ({len(connected_clients)} total)")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting WalkSense API server...")
    uvicorn.run(
        "API.server:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info",
    )
