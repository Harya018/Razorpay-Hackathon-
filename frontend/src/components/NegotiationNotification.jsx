import { useEffect, useRef, useState } from "react";

import { dismissNegotiation, markNegotiationOpened } from "../lib/cart.js";
import NegotiationPanel from "./NegotiationPanel.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// A slight, fixed per-mount tilt — irregular, hand-placed, never
// perfectly square. Randomized once per notification (keyed by
// sessionId) rather than per render, so it doesn't jitter on re-renders.
function tiltFor(sessionId) {
  if (!sessionId) return -1.2;
  let hash = 0;
  for (let i = 0; i < sessionId.length; i += 1) hash = (hash * 31 + sessionId.charCodeAt(i)) % 1000;
  return -0.6 - (hash % 130) / 100; // range roughly -0.6deg to -1.9deg
}

function speak(text) {
  try {
    if (!("speechSynthesis" in window) || !text) return;
    window.speechSynthesis.cancel(); // never overlap with a previous utterance
    const utterance = new SpeechSynthesisUtterance(text);
    window.speechSynthesis.speak(utterance);
  } catch {
    // Best-effort narration only — never break the popup if TTS is
    // unavailable/blocked in this browser.
  }
}

function stopSpeaking() {
  try {
    window.speechSynthesis?.cancel();
  } catch {
    // ignore
  }
}

// The seller-initiated negotiation popup (Phase 10), restyled as a
// handwritten note from Priya rather than a coupon-style modal (Phase 16
// design pass) — irregular corners, a washi-tape pin, a settle-into-place
// entrance instead of a slide-in. Everything shown here — the message,
// the offered price — comes from a REAL /negotiate/start call the
// abandonment hook already made against the real seller agent and real
// policy gate; nothing here is a client-side hardcoded discount. "Accept
// Offer" replies into that SAME real session via NegotiationPanel's
// autoAccept path; "Not right now" leaves the cart at its original,
// un-negotiated price.
export default function NegotiationNotification({ notification }) {
  const [expanded, setExpanded] = useState(false);
  const [autoAccept, setAutoAccept] = useState(false);
  const [product, setProduct] = useState(null);
  const [statusMessage, setStatusMessage] = useState(null);
  const [voiceOn, setVoiceOn] = useState(true);
  const spokenSessionRef = useRef(null);

  useEffect(() => {
    if (!notification?.productId) return;
    fetch(`${API_BASE_URL}/product/${notification.productId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then(setProduct)
      .catch(() => {});
  }, [notification?.productId]);

  useEffect(() => {
    if (!notification || !voiceOn) return;
    if (spokenSessionRef.current === notification.sessionId) return; // speak once per session
    spokenSessionRef.current = notification.sessionId;
    speak(notification.message);
  }, [notification, voiceOn]);

  useEffect(() => stopSpeaking, []); // stop any speech if the component unmounts (route change, etc.)

  if (!notification) return null;

  function toggleVoice() {
    setVoiceOn((v) => {
      if (v) stopSpeaking();
      return !v;
    });
  }

  function handleOpenChat() {
    markNegotiationOpened();
    setAutoAccept(false);
    setExpanded(true);
  }

  function handleAccept() {
    markNegotiationOpened();
    stopSpeaking();
    setAutoAccept(true);
    setExpanded(true);
  }

  function handleDismiss() {
    stopSpeaking();
    dismissNegotiation();
  }

  const originalTotal = product ? product.price : null;
  const offeredTotal = notification.proposedValue;
  const rotation = tiltFor(notification.sessionId);

  return (
    <div
      key={notification.sessionId}
      className={`note-settle-in fixed bottom-4 right-4 z-50 w-[calc(100vw-2rem)] sm:w-full ${
        expanded ? "sm:max-w-md" : "sm:max-w-sm"
      }`}
      style={{ "--note-rest-rotation": `${expanded ? rotation * 0.3 : rotation}deg` }}
    >
      {!expanded ? (
        <div
          className="relative rounded-[3px_18px_4px_16px] border border-putty-dark bg-ivory p-4 pt-5 shadow-[0_10px_30px_-8px_rgba(43,40,35,0.35)]"
          style={{ transform: `rotate(${rotation}deg)` }}
        >
          {/* Washi-tape pin, top-left — the "someone placed this here" cue */}
          <div
            className="absolute -top-2.5 left-6 h-5 w-14 rounded-[1px] bg-clay-light/70 shadow-sm"
            style={{ transform: "rotate(-5deg)" }}
            aria-hidden="true"
          />

          <div className="mb-2 flex items-center justify-between">
            <span className="font-display text-sm italic text-ink-soft">A note from Priya</span>
            <button
              onClick={toggleVoice}
              title={voiceOn ? "Mute voice" : "Unmute voice"}
              className="text-ink-soft/60 hover:text-ink-soft"
            >
              {voiceOn ? "🔊" : "🔇"}
            </button>
          </div>

          <button onClick={handleOpenChat} className="block w-full text-left">
            {product && (
              <div className="mb-2 flex items-center gap-3">
                <img
                  src={product.image_urls?.[0]}
                  alt={product.name}
                  className="h-12 w-12 shrink-0 rounded-md border border-putty-dark object-cover"
                />
                <div className="min-w-0">
                  <p className="truncate font-display text-sm font-semibold text-ink">{product.name}</p>
                  {offeredTotal != null && originalTotal != null && (
                    <p className="text-sm">
                      <span className="mr-1.5 text-ink-soft/60 line-through">₹{(originalTotal / 100).toFixed(2)}</span>
                      <span className="font-semibold text-moss-dark">₹{(offeredTotal / 100).toFixed(2)}</span>
                    </p>
                  )}
                </div>
              </div>
            )}
            <p className="font-body text-sm leading-relaxed text-ink">{notification.message}</p>
          </button>

          <p className="mt-2 text-right font-display text-xs italic text-ink-soft/70">— Priya, owner</p>

          <div className="mt-3 flex gap-2">
            <button
              onClick={handleAccept}
              className="flex-1 rounded-sm bg-clay px-3 py-2 text-xs font-semibold text-ivory shadow-sm transition-colors hover:bg-clay-dark"
            >
              Accept Offer
            </button>
            <button
              onClick={handleDismiss}
              className="flex-1 rounded-sm border border-putty-dark px-3 py-2 text-xs font-medium text-ink-soft transition-colors hover:bg-putty-light"
            >
              Not right now
            </button>
          </div>
        </div>
      ) : (
        <div
          className="rounded-[4px_14px_4px_14px] border border-putty-dark bg-ivory shadow-[0_14px_36px_-10px_rgba(43,40,35,0.4)]"
          style={{ transform: `rotate(${rotation * 0.3}deg)` }}
        >
          <div className="flex items-center justify-between border-b border-putty px-4 py-2.5">
            <p className="font-display text-sm italic text-ink-soft">A note from Priya</p>
            <div className="flex items-center gap-3">
              <button onClick={toggleVoice} title={voiceOn ? "Mute voice" : "Unmute voice"} className="text-ink-soft/60 hover:text-ink-soft">
                {voiceOn ? "🔊" : "🔇"}
              </button>
              <button onClick={() => setExpanded(false)} className="text-sm text-ink-soft/60 hover:text-ink-soft">
                Minimize
              </button>
            </div>
          </div>
          <div className="max-h-[70vh] overflow-y-auto p-3">
            {statusMessage && (
              <p className="mb-2 rounded-sm border border-moss-light bg-moss-light/20 px-3 py-2 text-xs font-medium text-moss-dark">
                {statusMessage}
              </p>
            )}
            {product ? (
              <NegotiationPanel
                product={product}
                resumeSessionId={notification.sessionId}
                resumeMessage={notification.message}
                onClose={() => setExpanded(false)}
                onStatus={setStatusMessage}
                autoAccept={autoAccept}
                compact
              />
            ) : (
              <p className="p-2 text-sm text-ink-soft">Loading...</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
