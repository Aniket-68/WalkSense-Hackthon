import { useState } from "react";
import { CAMERA_MODE, buildCameraFeedUrl } from "../config";
import BrowserCamera from "./BrowserCamera";

export default function CameraFeed({ state, connected, accessToken }) {
  const isRunning = state?.system_status === "RUNNING";
  const detectionCount = state?.pipeline?.yolo?.detections_count ?? 0;
  const spatialSummary = state?.spatial_summary || "";
  const description = state?.latest_description || "";

  // Prefer backend-reported camera_mode (runtime), fall back to env var (build-time)
  const useBrowserCam = (state?.camera_mode ?? CAMERA_MODE) === "browser";
  
  const [serverStatus, setServerStatus] = useState("unknown");
  const [showTooltip, setShowTooltip] = useState(false);

  const startInstance = async () => {
    setServerStatus("starting");
    try {
      const apiUrl = import.meta.env.VITE_API_GATEWAY_URL || "YOUR_API_GATEWAY_URL/start-ai";
      
      if (apiUrl.includes("YOUR_API_GATEWAY_URL")) {
        console.warn("Please replace 'YOUR_API_GATEWAY_URL' with your actual AWS API Gateway endpoint in .env");
      } else {
        await fetch(apiUrl);
      }
      
      // Will automatically reconnect once websocket comes online
      setTimeout(() => {
         if (!connected) setServerStatus("unknown");
      }, 120000); // Give up visual spin after 2 mins
    } catch (err) {
      console.error("Failed to trigger API Gateway:", err);
      setServerStatus("offline");
      alert("Failed to start EC2 instance");
    }
  };

  // ─── Disconnected Overlay ───
  if (connected === false) {
    return (
      <div className="camera-container" style={{ position: "relative" }}>
        <div style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", background: "rgba(0,0,0,0.85)", zIndex: 20 }}>
          {serverStatus === "starting" ? (
             <>
                <style>{"@keyframes spin { 100% { transform: rotate(360deg); } }"}</style>
                <div style={{ width: "40px", height: "40px", border: "4px solid rgba(255,255,255,0.2)", borderTopColor: "#fff", borderRadius: "50%", animation: "spin 1s linear infinite", marginBottom: 20 }} />
                <p style={{ color: "white", fontSize: "18px", fontWeight: "500" }}>Starting AI Instance...</p>
                <p style={{ color: "rgba(255,255,255,0.7)", marginTop: 8, fontSize: "14px" }}>This typically takes 1-2 minutes.</p>
             </>
          ) : (
             <>
                <svg style={{ width: 48, height: 48, color: "#ff5252", marginBottom: 10 }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <p style={{ color: "white", marginBottom: 20, fontSize: "18px", fontWeight: "500" }}>Server is currently offline to save costs.</p>
                
                <div style={{ position: "relative" }} 
                      onMouseEnter={() => setShowTooltip(true)} 
                      onMouseLeave={() => setShowTooltip(false)}>
                  <button 
                    onClick={startInstance}
                    style={{ padding: "12px 24px", fontSize: "16px", borderRadius: "8px", background: "#4caf50", color: "white", border: "none", cursor: "pointer", fontWeight: "bold", boxShadow: "0 4px 6px rgba(0,0,0,0.3)", transition: "background 0.2s" }}
                    onMouseOver={(e) => e.target.style.background = "#45a049"}
                    onMouseOut={(e) => e.target.style.background = "#4caf50"}
                  >
                    Start AI Server
                  </button>
                  
                  {showTooltip && (
                    <div style={{ position: "absolute", bottom: "115%", left: "50%", transform: "translateX(-50%)", background: "#333", color: "#fff", padding: "10px 14px", borderRadius: "6px", fontSize: "14px", whiteSpace: "nowrap", pointerEvents: "none", boxShadow: "0 4px 12px rgba(0,0,0,0.5)", width: "300px", textAlign: "center" }}>
                      Start the backend EC2 instance. It will automatically stop after 15 minutes of inactivity.
                      <div style={{ position: "absolute", bottom: "-6px", left: "50%", transform: "translateX(-50%)", borderLeft: "6px solid transparent", borderRight: "6px solid transparent", borderTop: "6px solid #333" }} />
                    </div>
                  )}
                </div>
             </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="camera-container">
      {isRunning ? (
        <>
          {useBrowserCam ? (
            <BrowserCamera isRunning={isRunning} accessToken={accessToken} />
          ) : (
            <img
              className="camera-feed"
              src={buildCameraFeedUrl(accessToken)}
              alt="WalkSense Camera Feed"
            />
          )}

          {/* Overlay badges */}
          <div className="camera-overlay">
            <span className="badge">
              <span style={{ color: "var(--accent-green)" }}>●</span>
              LIVE
            </span>
            {detectionCount > 0 && (
              <span className="badge">
                {detectionCount} object{detectionCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>

          {/* Bottom description */}
          {description && (
            <div className="scene-description">
              <div className="label">WalkSense Vision</div>
              <div>{description}</div>
            </div>
          )}
        </>
      ) : (
        <div className="camera-placeholder">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9A2.25 2.25 0 0013.5 5.25h-9A2.25 2.25 0 002.25 7.5v9A2.25 2.25 0 004.5 18.75z" />
          </svg>
          <p>
            Camera feed offline — press <strong>Start</strong> to begin
          </p>
        </div>
      )}
    </div>
  );
}
