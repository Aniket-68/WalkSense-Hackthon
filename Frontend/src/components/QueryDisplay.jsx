import { useState, useRef, useEffect } from "react";
import { API_BASE } from "../config";

export default function QueryDisplay({ state, authFetch, onVoiceStateChange }) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [micError, setMicError] = useState("");
  const [micPermission, setMicPermission] = useState("unknown");
  const listRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);

  const history = state?.dialogue_history || [];

  useEffect(() => {
    if (!onVoiceStateChange) return;
    if (isTranscribing) {
      onVoiceStateChange("transcribing");
      return;
    }
    if (isRecording) {
      onVoiceStateChange("recording");
      return;
    }
    onVoiceStateChange("idle");
  }, [isRecording, isTranscribing, onVoiceStateChange]);

  useEffect(() => {
    return () => {
      if (onVoiceStateChange) onVoiceStateChange("idle");
    };
  }, [onVoiceStateChange]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [history.length]);

  useEffect(() => {
    let cancelled = false;
    let permissionStatus = null;

    async function watchMicPermission() {
      try {
        if (!navigator.permissions?.query) return;
        permissionStatus = await navigator.permissions.query({
          name: "microphone",
        });
        if (cancelled) return;

        setMicPermission(permissionStatus.state || "unknown");
        permissionStatus.onchange = () => {
          setMicPermission(permissionStatus.state || "unknown");
        };
      } catch {
        // Browser doesn't support mic permission query.
      }
    }

    watchMicPermission();

    return () => {
      cancelled = true;
      if (permissionStatus) permissionStatus.onchange = null;
    };
  }, []);

  useEffect(() => {
    if (micPermission === "granted") {
      setMicError("");
    }
    if (micPermission === "denied") {
      setMicError(
        "Microphone is blocked in Chrome. Click the lock icon in the address bar, set Microphone to Allow, then reload this page."
      );
    }
  }, [micPermission]);

  const handleStartRecording = async () => {
    setMicError("");

    if (!window.isSecureContext) {
      setMicError(
        "Microphone access requires a secure context (https or localhost)."
      );
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setMicError("This browser does not support microphone capture.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setMicPermission("granted");
      audioChunksRef.current = [];

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm",
      });

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        // Stop all mic tracks
        stream.getTracks().forEach((track) => track.stop());

        const audioBlob = new Blob(audioChunksRef.current, {
          type: "audio/webm",
        });

        if (audioBlob.size < 1000) {
          console.warn("Audio too short, ignoring");
          return;
        }

        // Send to backend for transcription
        setIsTranscribing(true);
        try {
          const formData = new FormData();
          formData.append("audio", audioBlob, "recording.webm");

          const request = authFetch || fetch;
          const res = await request(`${API_BASE}/api/voice-query`, {
            method: "POST",
            body: formData,
          });

          const data = await res.json();
          if (data.status === "submitted") {
            console.log("Query submitted:", data.text);
          } else if (data.status === "no_speech") {
            console.log("No speech detected");
          } else if (data.error) {
            console.error("Transcription error:", data.error);
          }
        } catch (err) {
          console.error("Failed to send audio:", err);
        } finally {
          setIsTranscribing(false);
        }
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start(250); // collect data every 250ms
      setIsRecording(true);
      // Block stop for 600ms so we always capture the start of speech
      mediaRecorderRef._minRecordingTimer = Date.now();
      console.log("Recording started");
    } catch (err) {
      console.error("Microphone access denied:", err);
      const errName = err?.name || "";
      if (errName === "NotAllowedError" || errName === "PermissionDeniedError") {
        setMicError(
          "Chrome blocked microphone access. Allow microphone for this site, then try again."
        );
      } else if (errName === "NotFoundError" || errName === "DevicesNotFoundError") {
        setMicError("No microphone device was found.");
      } else if (errName === "NotReadableError" || errName === "TrackStartError") {
        setMicError("Microphone is busy in another app. Close that app and retry.");
      } else {
        setMicError(`Microphone error: ${err?.message || "Unknown error"}`);
      }
      setIsRecording(false);
    }
  };

  const handleStopRecording = () => {
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      // Enforce minimum 600ms recording to avoid clipping
      const elapsed = Date.now() - (mediaRecorderRef._minRecordingTimer || 0);
      const MIN_RECORD_MS = 600;
      if (elapsed < MIN_RECORD_MS) {
        setTimeout(() => {
          if (
            mediaRecorderRef.current &&
            mediaRecorderRef.current.state !== "inactive"
          ) {
            mediaRecorderRef.current.stop();
          }
          setIsRecording(false);
        }, MIN_RECORD_MS - elapsed);
        return;
      }
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    console.log("Recording stopped");
  };

  // Handle Escape key to stop recording
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && isRecording) {
        handleStopRecording();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isRecording]);

  return (
    <div className="query-container card">
      <div className="query-header">
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--accent-cyan)"
          strokeWidth="2"
        >
          <path d="M7.5 8.25h9M7.5 12h4.5m-1.5 8.25c-4.97 0-9-3.694-9-8.25s4.03-8.25 9-8.25 9 3.694 9 8.25c0 2.104-.859 4.023-2.273 5.48.432.884.642 1.853.642 2.77v.75c0 .414-.336.75-.75.75-1.605 0-3.108-.622-4.245-1.604A10.92 10.92 0 0110.5 20.25z" />
        </svg>
        <h3>Dialogue</h3>
        {(state?.current_query || isTranscribing) && (
          <span
            className="badge"
            style={{
              background: "var(--accent-cyan-dim)",
              color: "var(--accent-cyan)",
              border: "1px solid rgba(0,229,255,0.2)",
            }}
          >
            {isTranscribing ? "Transcribing…" : "Processing…"}
          </span>
        )}
      </div>

      {/* Display-only conversation window */}
      <div className="dialogue-display" ref={listRef}>
        {history.length === 0 ? (
          <div className="empty-state">
            <svg
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--text-muted)"
              strokeWidth="1.5"
            >
              <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
              <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
            </svg>
            <p>No conversations yet.</p>
            <p style={{ marginTop: 4, fontSize: "0.8rem" }}>
              Press the microphone button below to ask WalkSense.
            </p>
          </div>
        ) : (
          history.map((entry, i) => (
            <div key={i} className={`dialogue-message ${entry.role}`}>
              <div className="message-header">
                {entry.role === "user" ? (
                  <>
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                    >
                      <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                      <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                    </svg>
                    <span>You</span>
                  </>
                ) : (
                  <>
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="currentColor"
                    >
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z" />
                    </svg>
                    <span>WalkSense</span>
                  </>
                )}
              </div>
              <div className="message-bubble">{entry.text}</div>
            </div>
          ))
        )}
      </div>

      {/* Voice input controls */}
      <div className="voice-controls">
        {isTranscribing ? (
          <button className="voice-btn transcribing" disabled>
            <div className="transcribing-indicator">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="spin-icon"
              >
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
            </div>
            <span>Transcribing…</span>
          </button>
        ) : isRecording ? (
          <button
            className="voice-btn recording"
            onClick={handleStopRecording}
            title="Stop recording"
          >
            <div className="recording-indicator">
              <div className="pulse-ring"></div>
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <path d="M6 6h12v12H6z" />
              </svg>
            </div>
            <span>Stop</span>
          </button>
        ) : (
          <button
            className="voice-btn"
            onClick={handleStartRecording}
            title="Ask WalkSense"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
              <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
            </svg>
            <span>Ask WalkSense</span>
          </button>
        )}
      </div>
      {micError && (
        <p
          role="alert"
          style={{
            marginTop: 10,
            fontSize: "0.85rem",
            color: "var(--accent-red, #ff5252)",
          }}
        >
          {micError}
        </p>
      )}
    </div>
  );
}
