import { useWebSocket } from "./hooks/useWebSocket";
import CameraFeed from "./components/CameraFeed";
import QueryDisplay from "./components/QueryDisplay";
import SystemControls from "./components/SystemControls";
import PipelineMonitor from "./components/PipelineMonitor";
import KeyboardShortcuts from "./components/KeyboardShortcuts";
import { API_BASE } from "./config";

function App() {
  const { state, connected } = useWebSocket();

  const systemStatus = state?.system_status || "IDLE";
  const isRunning = systemStatus === "RUNNING";
  const isStarting = systemStatus === "STARTING";
  const isStopping = systemStatus === "STOPPING";
  const isTransitioning = isStarting || isStopping;

  const handleStartStop = async () => {
    if (isTransitioning) return;
    try {
      const endpoint = isRunning ? "/api/system/stop" : "/api/system/start";
      await fetch(`${API_BASE}${endpoint}`, { method: "POST" });
    } catch (err) {
      console.error("Start/Stop failed:", err);
    }
  };

  const handleListen = () => {
    // Toggle voice recording by clicking the voice button
    const voiceBtn = document.querySelector(".voice-btn");
    if (voiceBtn) {
      voiceBtn.click();
    }
  };

  return (
    <div className="app-layout">
      {/* ─── Header ─── */}
      <header className="header">
        <div className="header-title">
          <div
            className={`logo-dot ${
              isRunning
                ? "animate-pulse-glow"
                : isTransitioning
                  ? "animate-spin-dot"
                  : ""
            }`}
          />
          <h1>WalkSense</h1>
          <span
            className={`badge ${isTransitioning ? "badge-transitioning" : ""}`}
            style={{
              background: isRunning
                ? "var(--accent-green-dim)"
                : isStarting
                  ? "var(--accent-cyan-dim)"
                  : isStopping
                    ? "var(--accent-amber-dim)"
                    : "var(--bg-card)",
              color: isRunning
                ? "var(--accent-green)"
                : isStarting
                  ? "var(--accent-cyan)"
                  : isStopping
                    ? "var(--accent-amber)"
                    : "var(--text-muted)",
              border: isRunning
                ? "1px solid rgba(0,200,83,0.3)"
                : isStarting
                  ? "1px solid rgba(0,229,255,0.3)"
                  : isStopping
                    ? "1px solid rgba(255,171,0,0.3)"
                    : "1px solid var(--border-subtle)",
            }}
          >
            {isStarting && (
              <svg
                className="spin-icon"
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
              >
                <path d="M12 2a10 10 0 0 1 10 10" />
              </svg>
            )}
            {systemStatus}
          </span>
        </div>

        <div className="header-status">
          <div className="connection-indicator">
            <div
              className={`connection-dot ${connected ? "connected" : "disconnected"}`}
            />
            <span>{connected ? "Connected" : "Disconnected"}</span>
          </div>
          <KeyboardShortcuts
            onStartStop={handleStartStop}
            onListen={handleListen}
          />
        </div>
      </header>

      {/* ─── Main Content ─── */}
      <main className="main-content">
        {/* Left: Camera */}
        <div className="left-panel">
          <CameraFeed state={state} />
        </div>

        {/* Right: Dialogue + Controls */}
        <div className="right-panel">
          <QueryDisplay state={state} />
          <SystemControls state={state} onStartStop={handleStartStop} />
        </div>
      </main>

      {/* ─── Pipeline Monitor ─── */}
      <PipelineMonitor state={state} />
    </div>
  );
}

export default App;
