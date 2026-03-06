"""
FastAPI server for WalkSense.
Provides REST endpoints, WebSocket state streaming, and MJPEG camera feed.

Run with:
    cd backend && python -m api.server
"""

import asyncio
import time
import sys
import os
from contextlib import asynccontextmanager

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    File,
    UploadFile,
    Depends,
    Request,
    HTTPException,
    status,
)
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
from loguru import logger

# Ensure backend root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from API.manager import SystemManager
from API.auth import (
    AUTH_CLEANUP_INTERVAL_SECONDS,
    AUTH_HOUSEKEEPING_ENABLED,
    AuthError,
    RateLimitExceeded,
    TokenReuseDetected,
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    enforce_rate_limit,
    issue_login_tokens,
    maybe_emit_lockout_alert,
    provision_managed_user,
    record_audit_event,
    register_rate_limit_failure,
    render_prometheus_metrics,
    reset_rate_limit,
    require_user,
    revoke_family,
    revoke_family_from_refresh,
    run_auth_maintenance_cycle,
    rotate_refresh_token,
    set_refresh_cookie,
    validate_access_token,
)

# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

_auth_housekeeping_task: Optional[asyncio.Task] = None

def _cors_origins_from_env() -> list[str]:
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,https://localhost:5173")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["http://localhost:5173", "https://localhost:5173"]

manager = SystemManager()
VOICE_QUERY_MAX_CONCURRENCY = max(1, int(os.getenv("VOICE_QUERY_MAX_CONCURRENCY", "4")))
_voice_query_semaphore = asyncio.Semaphore(VOICE_QUERY_MAX_CONCURRENCY)


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


# ──────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────

class QueryRequest(BaseModel):
    text: str

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    confirm_password: Optional[str] = None


async def _auth_housekeeping_loop() -> None:
    """Periodic auth cleanup + alert scan."""
    interval = max(60, int(AUTH_CLEANUP_INTERVAL_SECONDS))
    while True:
        await asyncio.sleep(interval)
        try:
            result = run_auth_maintenance_cycle()
            if result["deleted_audit_events"] or result["deleted_rate_limits"]:
                logger.info(
                    "[AUTH_MAINTENANCE] cleanup deleted "
                    f"audit={result['deleted_audit_events']} rate_limits={result['deleted_rate_limits']}"
                )
        except Exception as exc:
            logger.error(f"[AUTH_MAINTENANCE] cleanup loop error: {exc}")


@asynccontextmanager
async def _lifespan(_: FastAPI):
    global _auth_housekeeping_task
    if not AUTH_HOUSEKEEPING_ENABLED:
        logger.info("[AUTH_MAINTENANCE] housekeeping disabled by config")
    else:
        if _auth_housekeeping_task is None or _auth_housekeeping_task.done():
            _auth_housekeeping_task = asyncio.create_task(_auth_housekeeping_loop())
            logger.info("[AUTH_MAINTENANCE] housekeeping loop started")
    try:
        yield
    finally:
        if _auth_housekeeping_task:
            _auth_housekeeping_task.cancel()
            try:
                await _auth_housekeeping_task
            except asyncio.CancelledError:
                pass
            _auth_housekeeping_task = None


app = FastAPI(title="WalkSense API", version="1.0.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_from_env(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# REST Endpoints
# ──────────────────────────────────────────────

@app.post("/api/auth/login")
async def auth_login(req: LoginRequest, request: Request):
    """Authenticate user and issue access + refresh tokens."""
    client_ip = _client_ip(request)
    username = (req.username or "").strip().lower()
    rate_id = f"{client_ip}:{username}"

    try:
        enforce_rate_limit("login", rate_id)
    except RateLimitExceeded as e:
        record_audit_event(
            "login_rate_limited",
            False,
            username=username or None,
            ip=client_ip,
            detail=f"retry_after={e.retry_after}",
        )
        maybe_emit_lockout_alert(trigger="login_rate_limited", ip=client_ip)
        return JSONResponse(
            {"detail": e.message},
            status_code=e.status_code,
            headers={"Retry-After": str(e.retry_after)},
        )

    try:
        token_bundle = issue_login_tokens(req.username, req.password, client_ip=client_ip)
        reset_rate_limit("login", rate_id)
    except AuthError as e:
        register_rate_limit_failure("login", rate_id, ip=client_ip, reason=e.message)
        return JSONResponse({"detail": e.message}, status_code=e.status_code)

    response = JSONResponse(
        {
            "status": "ok",
            "token_type": "bearer",
            "access_token": token_bundle["access_token"],
            "expires_in": token_bundle["expires_in"],
            "user": token_bundle["user"],
        }
    )
    set_refresh_cookie(response, token_bundle["refresh_token"])
    return response


@app.post("/api/auth/register")
async def auth_register(req: RegisterRequest, request: Request):
    """Self-service user registration."""
    client_ip = _client_ip(request)
    username = (req.username or "").strip().lower()

    # Basic validation
    if not username or len(username) < 3:
        raise HTTPException(status_code=422, detail="Username must be at least 3 characters")
    if not req.password or len(req.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    if req.confirm_password is not None and req.password != req.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match")

    # Apply same rate limiting as login
    rate_id = f"{client_ip}:register"
    try:
        enforce_rate_limit("login", rate_id)
    except RateLimitExceeded as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers={"Retry-After": str(e.retry_after)},
        ) from e

    # Create the user
    try:
        provision_managed_user(username, req.password)
    except ValueError as e:
        msg = str(e)
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail="Username already taken")
        raise HTTPException(status_code=422, detail=msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Registration failed")

    # Auto-login — issue tokens immediately
    try:
        token_bundle = issue_login_tokens(username, req.password, client_ip=client_ip)
    except AuthError as e:
        # Account created but token issue failed — shouldn't happen
        raise HTTPException(status_code=e.status_code, detail=e.message) from e

    record_audit_event("register_success", True, username=username, ip=client_ip)
    reset_rate_limit("login", rate_id)

    response = JSONResponse(
        {
            "status": "created",
            "token_type": "bearer",
            "access_token": token_bundle["access_token"],
            "expires_in": token_bundle["expires_in"],
            "user": token_bundle["user"],
        },
        status_code=201,
    )
    set_refresh_cookie(response, token_bundle["refresh_token"])
    return response


@app.post("/api/auth/refresh")
async def auth_refresh(request: Request):
    """Rotate refresh token and issue a new access token."""
    client_ip = _client_ip(request)
    rate_id = f"{client_ip}:refresh"
    try:
        enforce_rate_limit("refresh", rate_id)
    except RateLimitExceeded as e:
        record_audit_event(
            "refresh_rate_limited",
            False,
            ip=client_ip,
            detail=f"retry_after={e.retry_after}",
        )
        maybe_emit_lockout_alert(trigger="refresh_rate_limited", ip=client_ip)
        return JSONResponse(
            {"detail": e.message},
            status_code=e.status_code,
            headers={"Retry-After": str(e.retry_after)},
        )

    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        register_rate_limit_failure("refresh", rate_id, ip=client_ip, reason="missing_refresh_cookie")
        record_audit_event("refresh_failed", False, ip=client_ip, detail="missing_refresh_cookie")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    try:
        token_bundle = rotate_refresh_token(refresh_token, client_ip=client_ip)
        reset_rate_limit("refresh", rate_id)
    except TokenReuseDetected as e:
        register_rate_limit_failure("refresh", rate_id, ip=client_ip, reason="refresh_reuse_detected")
        maybe_emit_lockout_alert(trigger="refresh_reuse_detected", ip=client_ip)
        response = JSONResponse(
            {"status": "compromised", "detail": e.message},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
        clear_refresh_cookie(response)
        return response
    except AuthError as e:
        register_rate_limit_failure("refresh", rate_id, ip=client_ip, reason=e.message)
        response = JSONResponse({"detail": e.message}, status_code=e.status_code)
        clear_refresh_cookie(response)
        return response

    response = JSONResponse(
        {
            "status": "ok",
            "token_type": "bearer",
            "access_token": token_bundle["access_token"],
            "expires_in": token_bundle["expires_in"],
            "user": token_bundle["user"],
        }
    )
    set_refresh_cookie(response, token_bundle["refresh_token"])
    return response


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    """Revoke the token family represented by the current refresh token."""
    client_ip = _client_ip(request)
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if refresh_token:
        try:
            revoke_family_from_refresh(refresh_token, reason="logout", client_ip=client_ip)
            record_audit_event("logout_success", True, ip=client_ip)
        except AuthError:
            # Invalid/expired refresh token: still clear cookie and return success.
            record_audit_event("logout_with_invalid_refresh", False, ip=client_ip)
            pass
    else:
        record_audit_event("logout_without_refresh", True, ip=client_ip)

    response = JSONResponse({"status": "logged_out"})
    clear_refresh_cookie(response)
    return response


@app.post("/api/auth/revoke-family")
async def auth_revoke_family(request: Request, current_user: Dict[str, Any] = Depends(require_user)):
    """Immediately revoke current JWT family (compromised session response)."""
    client_ip = _client_ip(request)
    revoke_family(
        current_user["family_id"],
        reason="manual_compromise_report",
        actor_user_id=current_user["id"],
        client_ip=client_ip,
    )
    maybe_emit_lockout_alert(trigger="manual_family_revoke", ip=client_ip)
    response = JSONResponse({"status": "revoked"})
    clear_refresh_cookie(response)
    return response


@app.get("/api/auth/me")
async def auth_me(current_user: Dict[str, Any] = Depends(require_user)):
    """Return authenticated user profile from access token."""
    return {"user": {"id": current_user["id"], "username": current_user["username"]}}


@app.post("/api/system/start")
async def system_start(current_user: Dict[str, Any] = Depends(require_user)):
    """Start the processing pipeline."""
    manager.start()
    return {"status": "started"}


@app.post("/api/system/stop")
async def system_stop(current_user: Dict[str, Any] = Depends(require_user)):
    """Stop the processing pipeline."""
    manager.stop()
    return {"status": "stopped"}


@app.get("/api/system/status")
async def system_status(current_user: Dict[str, Any] = Depends(require_user)):
    """Get current system state."""
    return manager.get_state()


@app.get("/api/config")
async def get_config(current_user: Dict[str, Any] = Depends(require_user)):
    """Return runtime configuration the frontend needs (camera mode, TTS mode, etc.)."""
    from Infrastructure.config import Config
    return {
        "camera_mode": Config.get("camera.mode", "hardware"),
        "tts_remote_mode": Config.get("tts.remote_mode", "browser"),
    }


@app.post("/api/query")
async def submit_query(req: QueryRequest, current_user: Dict[str, Any] = Depends(require_user)):
    """Submit a text query to the system."""
    manager.submit_query(req.text)
    return {"status": "submitted", "query": req.text}


@app.post("/api/voice-query")
async def voice_query(audio: UploadFile = File(...), current_user: Dict[str, Any] = Depends(require_user)):
    """Accept audio from browser mic, transcribe, and submit as query."""

    try:
        audio_bytes = await audio.read()
        logger.info(f"[VoiceQuery] Received audio: {len(audio_bytes)} bytes, type={audio.content_type}")

        # Limit concurrent transcode/transcribe jobs to avoid threadpool starvation.
        async with _voice_query_semaphore:
            # Run blocking work (ffmpeg + whisper/deepgram) in thread pool
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
async def toggle_mute(current_user: Dict[str, Any] = Depends(require_user)):
    """Toggle audio mute."""
    muted = manager.toggle_mute()
    return {"muted": muted}


@app.get("/metrics/auth")
async def auth_metrics() -> PlainTextResponse:
    """Prometheus-formatted security metrics for auth lockouts/compromise events."""
    return PlainTextResponse(render_prometheus_metrics(), media_type="text/plain; version=0.0.4")


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
async def camera_feed(access_token: Optional[str] = None):
    """MJPEG stream of the annotated camera feed."""
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")
    try:
        validate_access_token(access_token)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message) from e

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
    token = ws.query_params.get("access_token")
    if not token:
        await ws.close(code=4401)
        return
    try:
        validate_access_token(token)
    except AuthError:
        await ws.close(code=4401)
        return

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
# WebSocket — Server-side TTS audio streaming
# ──────────────────────────────────────────────

@app.websocket("/ws/audio")
async def audio_ws(ws: WebSocket):
    """Stream synthesized audio bytes to the browser.

    Used when tts.remote_mode is 'server' or 'hybrid'.
    The backend synthesizes WAV/MP3 via TTSEngine.synthesize_to_bytes()
    and pushes binary chunks here.  The frontend decodes and plays them
    via the Web Audio API.
    """
    token = ws.query_params.get("access_token")
    if not token:
        await ws.close(code=4401)
        return
    try:
        validate_access_token(token)
    except AuthError:
        await ws.close(code=4401)
        return

    await ws.accept()
    logger.info("[WS/Audio] Client connected for TTS audio stream")

    try:
        while True:
            audio_data = manager.get_audio_chunk()
            if audio_data:
                await ws.send_bytes(audio_data)
            else:
                await asyncio.sleep(0.1)   # poll interval
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[WS/Audio] Error: {e}")
    finally:
        logger.info("[WS/Audio] Client disconnected")


# ──────────────────────────────────────────────
# WebSocket — Real-time state push
# ──────────────────────────────────────────────

connected_clients: set[WebSocket] = set()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Push system state to the frontend every ~200ms."""
    token = ws.query_params.get("access_token")
    if not token:
        await ws.close(code=4401)
        return
    try:
        validate_access_token(token)
    except AuthError:
        await ws.close(code=4401)
        return

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
