import { useState } from "react";
import { API_BASE } from "../config";

export default function SystemControls({ state, onStartStop }) {
  const [loading, setLoading] = useState(false);
  const systemStatus = state?.system_status || "IDLE";
  const isRunning = systemStatus === "RUNNING";
  const isStarting = systemStatus === "STARTING";
  const isStopping = systemStatus === "STOPPING";
  const isTransitioning = isStarting || isStopping;
  const isMuted = state?.muted || false;

  const handleToggle = async () => {
    if (isTransitioning) return;
    setLoading(true);
    try {
      const endpoint = isRunning ? "/api/system/stop" : "/api/system/start";
      await fetch(`${API_BASE}${endpoint}`, { method: "POST" });
    } catch (err) {
      console.error("Toggle failed:", err);
    } finally {
      setLoading(false);
    }
    if (onStartStop) onStartStop();
  };

  const handleMute = async () => {
    try {
      await fetch(`${API_BASE}/api/system/mute`, { method: "POST" });
    } catch (err) {
      console.error("Mute failed:", err);
    }
  };

  // Button label & style logic
  let btnClass = "start";
  let btnLabel = "Start System";
  let btnIcon = (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
      <path d="M8 5.14v14l11-7-11-7z" />
    </svg>
  );

  if (isStarting) {
    btnClass = "starting";
    btnLabel = "Initializing…";
    btnIcon = (
      <svg
        className="spin-icon"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      >
        <path d="M12 2a10 10 0 0 1 10 10" />
      </svg>
    );
  } else if (isStopping) {
    btnClass = "stopping";
    btnLabel = "Stopping…";
    btnIcon = (
      <svg
        className="spin-icon"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      >
        <path d="M12 2a10 10 0 0 1 10 10" />
      </svg>
    );
  } else if (isRunning) {
    btnClass = "stop";
    btnLabel = "Stop System";
    btnIcon = (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <rect x="6" y="5" width="4" height="14" rx="1" />
        <rect x="14" y="5" width="4" height="14" rx="1" />
      </svg>
    );
  }

  return (
    <div className="controls-container card">
      <button
        className={`control-btn ${btnClass}`}
        onClick={handleToggle}
        disabled={isTransitioning || loading}
      >
        {btnIcon}
        {btnLabel}
        {isStarting && <span className="init-progress-bar" />}
      </button>

      <button
        className={`control-btn ${isMuted ? "mute-active" : ""}`}
        onClick={handleMute}
        title={isMuted ? "Unmute Audio" : "Mute Audio"}
      >
        {isMuted ? (
          <>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M16.5 12A4.5 4.5 0 0014 7.97v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51A8.796 8.796 0 0021 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06a8.99 8.99 0 003.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" />
            </svg>
            Muted
          </>
        ) : (
          <>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0014 7.97v8.05c1.48-.73 2.5-2.25 2.5-3.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
            </svg>
            Audio
          </>
        )}
      </button>
    </div>
  );
}
