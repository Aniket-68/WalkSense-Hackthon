import { CAMERA_MODE, buildCameraFeedUrl } from "../config";
import BrowserCamera from "./BrowserCamera";

export default function CameraFeed({ state, accessToken }) {
  const isRunning = state?.system_status === "RUNNING";
  const detectionCount = state?.pipeline?.yolo?.detections_count ?? 0;
  const spatialSummary = state?.spatial_summary || "";
  const description = state?.latest_description || "";

  // Prefer backend-reported camera_mode (runtime), fall back to env var (build-time)
  const useBrowserCam = (state?.camera_mode ?? CAMERA_MODE) === "browser";

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
          {(description || spatialSummary) && (
            <div className="scene-description">
              {spatialSummary && <div className="label">Spatial Sense</div>}
              {spatialSummary && (
                <div
                  style={{
                    marginBottom: 4,
                    fontSize: "0.75rem",
                    color: "var(--text-secondary)",
                  }}
                >
                  {spatialSummary}
                </div>
              )}
              {description && <div>{description}</div>}
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
