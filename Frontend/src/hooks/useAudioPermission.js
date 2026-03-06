/**
 * useAudioPermission — Manages user consent for browser audio playback.
 *
 * Browsers enforce an autoplay policy: audio cannot start without a prior
 * user gesture (click / tap / keypress).  This hook surfaces a "request"
 * function that, when called from a click handler, unlocks both the
 * Web Speech API (`speechSynthesis`) and the Web Audio API (`AudioContext`).
 *
 * It also persists the permission in `sessionStorage` so the banner
 * doesn't reappear after a soft page refresh within the same tab.
 *
 * Usage:
 *   const { granted, request } = useAudioPermission(needsAudio);
 *   // `needsAudio` — true when tts_remote_mode !== "local"
 *   // Show a banner when `needsAudio && !granted`
 *   // Call `request()` from a button's onClick
 */

import { useState, useCallback, useRef, useEffect } from "react";

const STORAGE_KEY = "walksense_audio_permitted";

export function useAudioPermission(needsAudio = false) {
  const [granted, setGranted] = useState(
    () => sessionStorage.getItem(STORAGE_KEY) === "1"
  );
  const ctxRef = useRef(null);

  const request = useCallback(() => {
    // Unlock Web Speech API with a silent utterance
    try {
      const silentUtterance = new SpeechSynthesisUtterance("");
      silentUtterance.volume = 0;
      speechSynthesis.speak(silentUtterance);
    } catch (e) {
      console.warn("[AudioPermission] speechSynthesis unlock failed:", e);
    }

    // Unlock Web Audio API by creating + resuming an AudioContext
    try {
      if (!ctxRef.current) {
        ctxRef.current = new (window.AudioContext ||
          window.webkitAudioContext)();
      }
      if (ctxRef.current.state === "suspended") {
        ctxRef.current.resume();
      }
    } catch (e) {
      console.warn("[AudioPermission] AudioContext unlock failed:", e);
    }

    setGranted(true);
    sessionStorage.setItem(STORAGE_KEY, "1");
    console.log("[AudioPermission] Audio playback permitted by user gesture");
  }, []);

  // Cleanup AudioContext on unmount
  useEffect(() => {
    return () => {
      if (ctxRef.current) {
        ctxRef.current.close().catch(() => {});
        ctxRef.current = null;
      }
    };
  }, []);

  return { granted, request, needsPrompt: needsAudio && !granted };
}
