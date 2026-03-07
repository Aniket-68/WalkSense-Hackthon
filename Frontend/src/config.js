/**
 * Centralized configuration for WalkSense frontend.
 *
 * At build time Vite replaces `import.meta.env.VITE_*` with the literal
 * values from the environment or `.env` file.
 *
 * If VITE_API_URL is not set, the backend URL is auto-derived from the
 * browser's current hostname (same host, port 8080). This means:
 *   - localhost:5173  → backend at localhost:8080
 *   - 192.168.x.x:5173 → backend at 192.168.x.x:8080
 *   - myserver.com    → backend at myserver.com:8080
 *
 * For Amplify/prod → set VITE_API_URL in environment variables
 *                    e.g. https://api.walksense.example.com
 */

// Base URL for REST endpoints (no trailing slash)
function deriveApiBase() {
  // Explicit env var takes priority
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL.replace(/\/+$/, "");
  }
  // In dev mode, Vite proxies /api → backend, so use same origin (empty string).
  // In production (built static files served elsewhere), derive from hostname.
  if (import.meta.env.DEV) {
    return ""; // same-origin — Vite proxy handles /api and /ws
  }
  const host = window.location.hostname;
  const port = import.meta.env.VITE_API_PORT || "8080";
  return `${window.location.protocol}//${host}:${port}`;
}

export const API_BASE = deriveApiBase();

// WebSocket URL derived from current page origin
function deriveWsUrl() {
  if (import.meta.env.VITE_WS_URL) {
    return import.meta.env.VITE_WS_URL;
  }
  // Use same protocol/host/port as the page — Vite proxy handles /ws → backend
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host; // includes port
  return `${proto}//${host}/ws`;
}

export const WS_URL = deriveWsUrl();

// Camera feed URL (MJPEG stream from backend's own camera)
export const CAMERA_FEED_URL = `${API_BASE}/api/camera/feed`;

// Optional helper used by mobile UI variants. Access token is ignored when not used.
export function buildCameraFeedUrl(_accessToken) {
  return CAMERA_FEED_URL;
}

// Camera source mode: "backend" (server camera/MJPEG) or "browser" (getUserMedia → WS)
export const CAMERA_MODE =
  import.meta.env.VITE_CAMERA_MODE || "backend";
