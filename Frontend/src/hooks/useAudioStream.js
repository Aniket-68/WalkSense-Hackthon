/**
 * useAudioStream — Server-side TTS audio playback via /ws/audio (Option B).
 *
 * Connects a WebSocket to the backend's /ws/audio endpoint which streams
 * synthesized WAV or MP3 binary chunks.  Each chunk is decoded and played
 * through the Web Audio API so the user hears server-quality TTS.
 *
 * Active when `tts_remote_mode` is "server", or for non-critical
 * utterances in "hybrid" mode.
 */

import { useEffect, useRef, useCallback } from "react";
import { WS_URL } from "../config";

const AUDIO_WS_URL = WS_URL.replace(/\/ws$/, "/ws/audio");

export function useAudioStream(state, { enabled = true, audioPermitted = true } = {}) {
  const wsRef = useRef(null);
  const ctxRef = useRef(null);
  const queueRef = useRef([]);
  const playingRef = useRef(false);

  // Lazily create or resume AudioContext (browsers require user gesture)
  const getAudioCtx = useCallback(() => {
    if (!ctxRef.current) {
      ctxRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (ctxRef.current.state === "suspended") {
      ctxRef.current.resume();
    }
    return ctxRef.current;
  }, []);

  // Play queued audio buffers one at a time
  const playNext = useCallback(() => {
    if (playingRef.current || queueRef.current.length === 0) return;
    playingRef.current = true;

    const audioData = queueRef.current.shift();
    const ctx = getAudioCtx();

    ctx
      .decodeAudioData(audioData)
      .then((buffer) => {
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.connect(ctx.destination);
        source.onended = () => {
          playingRef.current = false;
          playNext(); // chain next
        };
        source.start(0);
      })
      .catch((err) => {
        console.error("[AudioStream] Decode error:", err);
        playingRef.current = false;
        playNext();
      });
  }, [getAudioCtx]);

  useEffect(() => {
    if (!enabled || !audioPermitted) return;

    const mode = state?.tts_remote_mode;
    // Only connect when server-side audio is expected
    if (mode !== "server" && mode !== "hybrid") return;

    const ws = new WebSocket(AUDIO_WS_URL);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      console.log("[AudioStream] Connected to /ws/audio");
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer && event.data.byteLength > 0) {
        // In hybrid mode, skip server audio for critical/warning (browser TTS handles those)
        // We can't know priority from the binary blob, so always queue —
        // the backend already filters based on mode in emit_tts().
        queueRef.current.push(event.data);
        playNext();
      }
    };

    ws.onclose = () => {
      console.log("[AudioStream] Disconnected");
    };

    ws.onerror = (err) => {
      console.error("[AudioStream] Error:", err);
      ws.close();
    };

    wsRef.current = ws;

    return () => {
      ws.close();
      wsRef.current = null;
      queueRef.current = [];
      playingRef.current = false;
    };
  }, [enabled, audioPermitted, state?.tts_remote_mode, playNext]);

  // Cleanup AudioContext on unmount
  useEffect(() => {
    return () => {
      if (ctxRef.current) {
        ctxRef.current.close().catch(() => {});
        ctxRef.current = null;
      }
    };
  }, []);
}
