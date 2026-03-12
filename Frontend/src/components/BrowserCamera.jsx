import { useEffect, useRef, useState, useCallback } from "react";
import { WS_URL } from "../config";

/**
 * BrowserCamera — captures the user's webcam via getUserMedia,
 * displays a local preview, and streams JPEG frames to the backend
 * over a dedicated WebSocket (`/ws/camera`).
 *
 * Used when VITE_CAMERA_MODE=browser (e.g. backend on EC2, no physical cam).
 */

const FRAME_INTERVAL_MS = 200; // ~5 FPS — enough for YOLO + VLM, low bandwidth
const JPEG_QUALITY = 0.7;

export default function BrowserCamera({ isRunning }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const intervalRef = useRef(null);
  const [error, setError] = useState(null);

  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");

  // Enumerate video devices
  useEffect(() => {
    async function getDevices() {
      try {
        let d = await navigator.mediaDevices.enumerateDevices();
        let videoDevices = d.filter((device) => device.kind === "videoinput");

        // Request permission if labels are empty
        if (videoDevices.length > 0 && !videoDevices[0].label) {
          try {
            const tempStream = await navigator.mediaDevices.getUserMedia({ video: true });
            tempStream.getTracks().forEach((t) => t.stop());
            d = await navigator.mediaDevices.enumerateDevices();
            videoDevices = d.filter((device) => device.kind === "videoinput");
          } catch (e) {
            console.warn("Could not get permission to read camera labels", e);
          }
        }

        setDevices(videoDevices);
        if (videoDevices.length > 0 && !selectedDeviceId) {
          // Default to the first back-facing camera if possible, otherwise just the first one
          const backCam = videoDevices.find((d) =>
            d.label.toLowerCase().includes("back")
          );
          setSelectedDeviceId(backCam ? backCam.deviceId : videoDevices[0].deviceId);
        }
      } catch (err) {
        console.error("Error enumerating devices:", err);
      }
    }
    getDevices();
  }, [selectedDeviceId]);

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

  useEffect(() => {
    if (!isRunning) {
      cleanup();
      return;
    }

    let cancelled = false;

    async function start() {
      try {
        const videoConstraints = {
          width: { ideal: 1280 },
          height: { ideal: 720 },
        };

        if (selectedDeviceId) {
          videoConstraints.deviceId = { exact: selectedDeviceId };
        } else {
          videoConstraints.facingMode = "environment";
        }

        // 1. Get user camera
        const stream = await navigator.mediaDevices.getUserMedia({
          video: videoConstraints,
          audio: false,
        });

        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }

        // 2. Connect WebSocket for frame streaming
        const camWsUrl = WS_URL.replace(/\/ws$/, "/ws/camera");
        const ws = new WebSocket(camWsUrl);
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
          console.log("[BrowserCam] WS connected, streaming frames");
          // 3. Start sending frames at interval
          intervalRef.current = setInterval(() => sendFrame(), FRAME_INTERVAL_MS);
        };

        ws.onclose = () => {
          console.log("[BrowserCam] WS closed");
          clearInterval(intervalRef.current);
        };

        ws.onerror = (e) => {
          console.error("[BrowserCam] WS error:", e);
        };

        wsRef.current = ws;
        setError(null);
      } catch (err) {
        console.error("[BrowserCam] Failed to start:", err);
        if (err.name === "NotAllowedError") {
          setError("Camera permission denied. Please allow camera access.");
        } else if (err.name === "NotFoundError") {
          setError("No camera found on this device.");
        } else {
          setError(`Camera error: ${err.message}`);
        }
      }
    }

    start();

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [isRunning, selectedDeviceId, cleanup]);

  function sendFrame() {
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
      JPEG_QUALITY
    );
  }

  if (error) {
    return (
      <div className="camera-placeholder" style={{ color: "var(--accent-red, #ff5252)", position: "relative", width: "100%", height: "100%" }}>
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
      </div>
    );
  }

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", display: "flex", backgroundColor: "#000" }}>
      {devices.length > 0 && (
        <select
          value={selectedDeviceId}
          onChange={(e) => setSelectedDeviceId(e.target.value)}
          style={{
            position: "absolute",
            top: 10,
            right: 10,
            zIndex: 10,
            background: "rgba(0,0,0,0.6)",
            color: "white",
            border: "1px solid rgba(255,255,255,0.3)",
            borderRadius: 4,
            padding: "6px 10px",
            fontSize: "14px",
            outline: "none",
            backdropFilter: "blur(4px)",
          }}
        >
          {devices.map((d, i) => (
            <option key={d.deviceId} value={d.deviceId}>
              {d.label || `Camera ${i + 1}`}
            </option>
          ))}
        </select>
      )}

      {/* Local preview — mirrors user webcam */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="camera-feed"
        style={{ objectFit: "cover", width: "100%", height: "100%" }}
      />
      {/* Hidden canvas for JPEG encoding */}
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </div>
  );
}
