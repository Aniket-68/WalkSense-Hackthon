export default function MobileControlDock({
  systemStatus = "IDLE",
  connected = false,
  isMuted = false,
  voiceState = "idle",
  onListen,
  onStartStop,
  onToggleMute,
}) {
  const isRunning = systemStatus === "RUNNING";
  const isStarting = systemStatus === "STARTING";
  const isStopping = systemStatus === "STOPPING";
  const isTransitioning = isStarting || isStopping;

  const startLabel = isStarting
    ? "Starting"
    : isStopping
      ? "Stopping"
      : isRunning
        ? "Stop System"
        : "Start System";

  const micTitle =
    voiceState === "recording"
      ? "Stop recording"
      : voiceState === "transcribing"
        ? "Transcribing"
        : "Ask WalkSense";

  return (
    <div className="mobile-dock" aria-label="Mobile Controls">
      <button
        type="button"
        className={`mobile-dock-btn mobile-dock-side ${isMuted ? "active" : ""}`}
        onClick={onToggleMute}
        disabled={!connected}
        title={!connected ? "Backend disconnected" : (isMuted ? "Unmute Audio" : "Mute Audio")}
      >
        {isMuted ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M16.5 12A4.5 4.5 0 0014 7.97v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51A8.796 8.796 0 0021 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06a8.99 8.99 0 003.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z" />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0014 7.97v8.05c1.48-.73 2.5-2.25 2.5-3.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
          </svg>
        )}
        <span>{isMuted ? "Muted" : "Audio"}</span>
      </button>

      <button
        type="button"
        className={`mobile-mic-btn ${voiceState}`}
        onClick={onListen}
        title={!connected ? "Backend disconnected" : micTitle}
        disabled={!connected || voiceState === "transcribing"}
      >
        {voiceState === "recording" ? (
          <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor">
            <path d="M6 6h12v12H6z" />
          </svg>
        ) : voiceState === "transcribing" ? (
          <svg
            className="spin-icon"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
          >
            <path d="M12 2a10 10 0 0 1 10 10" />
          </svg>
        ) : (
          <svg width="26" height="26" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
            <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
          </svg>
        )}
      </button>

      <button
        type="button"
        className={`mobile-dock-btn mobile-dock-start ${isRunning ? "stop" : "start"} ${isTransitioning ? "waiting" : ""}`}
        onClick={onStartStop}
        disabled={!connected || isTransitioning}
        title={!connected ? "Backend disconnected" : startLabel}
      >
        {isRunning ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="5" width="4" height="14" rx="1" />
            <rect x="14" y="5" width="4" height="14" rx="1" />
          </svg>
        ) : (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5.14v14l11-7-11-7z" />
          </svg>
        )}
        <span>{startLabel}</span>
      </button>
    </div>
  );
}
