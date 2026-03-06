import { useState } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { useAuth } from "./hooks/useAuth";
import { useTTS } from "./hooks/useTTS";
import { useAudioStream } from "./hooks/useAudioStream";
import { useAudioPermission } from "./hooks/useAudioPermission";
import CameraFeed from "./components/CameraFeed";
import QueryDisplay from "./components/QueryDisplay";
import SystemControls from "./components/SystemControls";
import PipelineMonitor from "./components/PipelineMonitor";
import KeyboardShortcuts from "./components/KeyboardShortcuts";
import LoginPanel from "./components/LoginPanel";
import SignupPanel from "./components/SignupPanel";
import MobileControlDock from "./components/MobileControlDock";
import { API_BASE } from "./config";

function App() {
  const auth = useAuth();
  const [showSignup, setShowSignup] = useState(false);
  const [voiceState, setVoiceState] = useState("idle");
  const { state, connected } = useWebSocket(auth.accessToken, auth.refreshSession);

  // Audio permission — required before any browser audio can play
  const needsAudio =
    state?.tts_remote_mode && state.tts_remote_mode !== "local";
  const {
    granted: audioPermitted,
    request: requestAudio,
    needsPrompt,
  } = useAudioPermission(needsAudio);

  // Remote TTS — hooks auto-activate based on state.tts_remote_mode
  useTTS(state, { audioPermitted }); // Option A: browser Web Speech API
  useAudioStream(state, {
    audioPermitted,
    accessToken: auth.accessToken,
  }); // Option B: server-synthesized audio stream

  const systemStatus = state?.system_status || "IDLE";
  const isRunning = systemStatus === "RUNNING";
  const isStarting = systemStatus === "STARTING";
  const isStopping = systemStatus === "STOPPING";
  const isTransitioning = isStarting || isStopping;

  const handleStartStop = async () => {
    if (isTransitioning) return;
    // Any click is a user gesture — unlock audio if not already permitted
    if (!audioPermitted) requestAudio();
    try {
      const endpoint = isRunning ? "/api/system/stop" : "/api/system/start";
      await auth.authFetch(`${API_BASE}${endpoint}`, { method: "POST" });
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

  const handleToggleMute = async () => {
    try {
      await auth.authFetch(`${API_BASE}/api/system/mute`, { method: "POST" });
    } catch (err) {
      console.error("Mute failed:", err);
    }
  };

  if (auth.isInitializing) {
    return (
      <div className="login-screen">
        <div className="login-card card">
          <h2>WalkSense</h2>
          <p>Initializing session...</p>
        </div>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    if (showSignup) {
      return (
        <SignupPanel
          onSignup={(bundle) => {
            auth.loginWithBundle(bundle);
            setShowSignup(false);
          }}
          onSwitchToLogin={() => setShowSignup(false)}
        />
      );
    }
    return (
      <LoginPanel
        onLogin={auth.login}
        error={auth.authError}
        onSwitchToSignup={() => setShowSignup(true)}
      />
    );
  }

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
          <span className="auth-user mono">{auth.user?.username}</span>
          <button className="logout-btn" onClick={auth.logout}>
            Logout
          </button>
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

      {/* ─── Audio Permission Banner ─── */}
      {needsPrompt && (
        <div className="audio-permission-banner">
          <div className="audio-permission-content">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
              <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
            </svg>
            <span>WalkSense needs your permission to play audio alerts</span>
            <button className="audio-permission-btn" onClick={requestAudio}>
              Enable Audio
            </button>
          </div>
        </div>
      )}

      {/* ─── Main Content ─── */}
      <main className="main-content">
        {/* Left: Camera */}
        <div className="left-panel">
          <div className="camera-stack">
            <CameraFeed state={state} accessToken={auth.accessToken} />
            <div className="mobile-pipeline-overlay">
              <PipelineMonitor state={state} variant="compact" />
            </div>
          </div>
        </div>

        {/* Right: Dialogue + Controls */}
        <div className="right-panel">
          <QueryDisplay
            state={state}
            authFetch={auth.authFetch}
            onVoiceStateChange={setVoiceState}
          />
          <SystemControls
            state={state}
            onStartStop={handleStartStop}
            authFetch={auth.authFetch}
            onToggleMute={handleToggleMute}
          />
        </div>
      </main>

      {/* ─── Pipeline Monitor ─── */}
      <div className="desktop-pipeline-wrap">
        <PipelineMonitor state={state} />
      </div>

      <MobileControlDock
        systemStatus={systemStatus}
        isMuted={Boolean(state?.muted)}
        voiceState={voiceState}
        onListen={handleListen}
        onStartStop={handleStartStop}
        onToggleMute={handleToggleMute}
      />
    </div>
  );
}

export default App;
