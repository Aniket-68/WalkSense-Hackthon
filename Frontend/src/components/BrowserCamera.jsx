import { useCallback, useEffect, useRef, useState } from "react";
import { buildWsUrl } from "../config";

/**
 * BrowserCamera — captures the user's webcam via getUserMedia,
 * displays a local preview, and streams JPEG frames to the backend
 * over a dedicated WebSocket (`/ws/camera`).
 *
 * Used when VITE_CAMERA_MODE=browser (e.g. backend on EC2, no physical cam).
 */

const FRAME_INTERVAL_MS = 200; // ~5 FPS — enough for YOLO + VLM, low bandwidth
const JPEG_QUALITY = 0.7;

export default function BrowserCamera({ isRunning, accessToken }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const intervalRef = useRef(null);
  const [error, setError] = useState(null);
  const [cameraPermission, setCameraPermission] = useState("unknown");
  const [retryTick, setRetryTick] = useState(0);

  const cleanup = useCallback(() => {
    clearInterval(intervalRef.current);
    intervalRef.current = null;

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const sendFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    const ws = wsRef.current;

    if (!video || !canvas || !ws || ws.readyState !== WebSocket.OPEN) return;
    if (video.readyState < 2) return; // HAVE_CURRENT_DATA

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);

    // Convert to JPEG blob and send as binary
    canvas.toBlob(
      (blob) => {
        if (blob && ws.readyState === WebSocket.OPEN) {
          blob.arrayBuffer().then((buf) => ws.send(buf));
        }
      },
      "image/jpeg",
      JPEG_QUALITY,
    );
  }, []);

  useEffect(() => {
    let cancelled = false;
    let permissionStatus = null;

    async function watchCameraPermission() {
      try {
        if (!navigator.permissions?.query) return;
        permissionStatus = await navigator.permissions.query({ name: "camera" });
        if (cancelled) return;

        setCameraPermission(permissionStatus.state || "unknown");
        permissionStatus.onchange = () => {
          setCameraPermission(permissionStatus.state || "unknown");
        };
      } catch {
        // Browser doesn't support camera permission query.
      }
    }

    watchCameraPermission();
    return () => {
      cancelled = true;
      if (permissionStatus) permissionStatus.onchange = null;
    };
  }, []);

  useEffect(() => {
    if (!isRunning || !accessToken) {
      cleanup();
      return;
    }

    let cancelled = false;

    async function start() {
      setError(null);

      if (!window.isSecureContext) {
        setError("Camera access requires a secure context (https or localhost).");
        return;
      }

      if (!navigator.mediaDevices?.getUserMedia) {
        setError("This browser does not support camera capture.");
        return;
      }

      if (cameraPermission === "denied") {
        setError(
          "Camera is blocked in Chrome. Click the lock icon in the address bar, set Camera to Allow, then reload this page."
        );
        return;
      }

      try {
        // 1. Get user camera
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 1280 },
            height: { ideal: 720 },
            facingMode: "environment",
          },
          audio: false,
        });

        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;
        setCameraPermission("granted");
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }

        // 2. Connect WebSocket for frame streaming
        const ws = new WebSocket(buildWsUrl("/ws/camera", accessToken));
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
          console.log("[BrowserCam] WS connected, streaming frames");
          // 3. Start sending frames at interval
          intervalRef.current = setInterval(sendFrame, FRAME_INTERVAL_MS);
        };

        ws.onclose = () => {
          console.log("[BrowserCam] WS closed");
          clearInterval(intervalRef.current);
        };

        ws.onerror = (e) => {
          console.error("[BrowserCam] WS error:", e);
          setError("Camera WebSocket connection failed");
        };

        wsRef.current = ws;
        setError(null);
      } catch (err) {
        console.error("[BrowserCam] Failed to start:", err);
        const errName = err?.name || "";
        if (errName === "NotAllowedError" || errName === "PermissionDeniedError") {
          setCameraPermission("denied");
          setError(
            "Chrome blocked camera access. Allow camera for this site, then retry."
          );
        } else if (errName === "NotFoundError" || errName === "DevicesNotFoundError") {
          setError("No camera found on this device.");
        } else if (errName === "NotReadableError" || errName === "TrackStartError") {
          setError("Camera is busy in another app. Close that app and retry.");
        } else {
          setError(`Camera error: ${err?.message || "Unknown error"}`);
        }
      }
    }

    start();

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [isRunning, accessToken, retryTick, cameraPermission, cleanup, sendFrame]);

  if (error) {
    return (
      <div
        className="camera-placeholder"
        style={{ color: "var(--accent-red, #ff5252)" }}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          style={{ width: 48, height: 48 }}
        >
          <path d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9A2.25 2.25 0 0013.5 5.25h-9A2.25 2.25 0 002.25 7.5v9A2.25 2.25 0 004.5 18.75z" />
        </svg>
        <p>{error}</p>
        <button
          type="button"
          className="camera-retry-btn"
          onClick={() => setRetryTick((v) => v + 1)}
        >
          Retry Camera Access
        </button>
      </div>
    );
  }

  return (
    <>
      {/* Local preview — mirrors user webcam */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="camera-feed"
        style={{ objectFit: "cover" }}
      />
      {/* Hidden canvas for JPEG encoding */}
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </>
  );
}
