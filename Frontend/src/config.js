/**
 * Centralized configuration for WalkSense frontend.
 *
 * At build time Vite replaces `import.meta.env.VITE_*` with the literal
 * values from the environment or `.env` file.
 *
 * For local dev    → defaults to localhost:8080
 * For Amplify/prod → set VITE_API_URL in Amplify environment variables
 *                    e.g. https://api.walksense.example.com
 */

// Base URL for REST endpoints (no trailing slash)
export const API_BASE =
  import.meta.env.VITE_API_URL?.replace(/\/+$/, "") || "http://localhost:8080";

// WebSocket URL derived from REST base
function deriveWsUrl(base) {
  try {
    const url = new URL(base);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return `${url.origin}/ws`;
  } catch {
    // fallback
    return base.replace(/^http/, "ws") + "/ws";
  }
}

export const WS_URL =
  import.meta.env.VITE_WS_URL || deriveWsUrl(API_BASE);

// Camera feed URL (MJPEG stream from backend's own camera)
export const CAMERA_FEED_URL = `${API_BASE}/api/camera/feed`;

// Camera source mode: "backend" (server camera/MJPEG) or "browser" (getUserMedia → WS)
export const CAMERA_MODE =
  import.meta.env.VITE_CAMERA_MODE || "backend";
