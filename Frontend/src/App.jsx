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

  const handleStartStop = async () => {
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
            className={`logo-dot ${systemStatus === "RUNNING" ? "animate-pulse-glow" : ""}`}
          />
          <h1>WalkSense</h1>
          <span
            className="badge"
            style={{
              background:
                systemStatus === "RUNNING"
                  ? "var(--accent-green-dim)"
                  : "var(--bg-card)",
              color:
                systemStatus === "RUNNING"
                  ? "var(--accent-green)"
                  : "var(--text-muted)",
              border:
                systemStatus === "RUNNING"
                  ? "1px solid rgba(0,200,83,0.3)"
                  : "1px solid var(--border-subtle)",
            }}
          >
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
