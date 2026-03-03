/**
 * useTTS — Browser-side Text-to-Speech via Web Speech API (Option A).
 *
 * Processes `state.tts_queue` — an array of { text, seq, priority } items
 * returned by each WebSocket state broadcast.  Every item is spoken in order
 * so that RESPONSE utterances are never lost when a WARNING fires right after.
 *
 * Supports priority-based interruption:
 *   - "critical" / "warning" → cancel current speech and speak immediately
 *   - "response" / "info" / "scene" → queue normally via speechSynthesis
 *
 * Active when `tts_remote_mode` is "browser" or for critical/warning
 * alerts in "hybrid" mode.
 *
 * Chrome fixes:
 *   - Waits for voiceschanged before first speak
 *   - 100ms delay after cancel() before speak()
 */

import { useEffect, useRef, useState } from "react";

export function useTTS(state, { enabled = true, audioPermitted = true } = {}) {
  const lastSeq = useRef(0);
  const [voicesReady, setVoicesReady] = useState(
    () => speechSynthesis.getVoices().length > 0
  );

  // Pre-load voices — Chrome fires voiceschanged async
  useEffect(() => {
    if (voicesReady) return;

    const onVoices = () => {
      if (speechSynthesis.getVoices().length > 0) {
        setVoicesReady(true);
        console.log("[TTS] Voices loaded:", speechSynthesis.getVoices().length);
      }
    };

    speechSynthesis.addEventListener("voiceschanged", onVoices);
    onVoices();

    return () => speechSynthesis.removeEventListener("voiceschanged", onVoices);
  }, [voicesReady]);

  // Process the tts_queue array from each state broadcast
  useEffect(() => {
    if (!enabled || !audioPermitted || !voicesReady) return;

    const queue = state?.tts_queue;
    if (!Array.isArray(queue) || queue.length === 0) return;

    const mode = state.tts_remote_mode ?? "browser";

    // Filter items we haven't played yet
    const newItems = queue.filter((item) => item.seq > lastSeq.current);
    if (newItems.length === 0) return;

    // Track the highest seq we'll process
    lastSeq.current = Math.max(...newItems.map((i) => i.seq));

    // Check if any item is high-priority (needs interrupt)
    const hasUrgent = newItems.some(
      (i) => i.priority === "critical" || i.priority === "warning"
    );

    const speakItem = (item) => {
      const shouldSpeak =
        mode === "browser" ||
        (mode === "hybrid" &&
          (item.priority === "critical" || item.priority === "warning"));

      if (!shouldSpeak) return;

      const utterance = new SpeechSynthesisUtterance(item.text);
      utterance.rate = item.priority === "critical" ? 1.2 : 1.05;
      utterance.pitch = 1.0;
      utterance.volume = 1.0;
      utterance.lang = "en-US";

      const voices = speechSynthesis.getVoices();
      const preferred =
        voices.find((v) => v.lang.startsWith("en") && v.default) ||
        voices.find((v) => v.lang.startsWith("en")) ||
        voices[0];
      if (preferred) utterance.voice = preferred;

      utterance.onerror = (e) =>
        console.error("[TTS] SpeechSynthesis error:", e.error, e);
      utterance.onstart = () =>
        console.log(
          `[TTS] Speaking (seq=${item.seq}, pri=${item.priority}):`,
          item.text.slice(0, 60)
        );

      speechSynthesis.speak(utterance);
    };

    if (hasUrgent) {
      speechSynthesis.cancel();
      // Chrome needs a short delay after cancel()
      setTimeout(() => newItems.forEach(speakItem), 100);
    } else {
      newItems.forEach(speakItem);
    }
  }, [state?.tts_queue, enabled, audioPermitted, voicesReady]);

  // Cleanup on unmount
  useEffect(() => {
    return () => speechSynthesis.cancel();
  }, []);
}
