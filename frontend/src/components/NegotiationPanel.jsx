import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { startCheckout } from "../lib/checkout.js";
import { toastError } from "../lib/toast.js";
import { clearNegotiationAccepted, markNegotiationAccepted, removeFromCart } from "../lib/cart.js";
import LiveBadge from "./LiveBadge.jsx";
import PolicyGateCard from "./PolicyGateCard.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const AUDIT_POLL_MS = 2000;

// resumeSessionId/resumeMessage (Phase 9): when provided, this panel
// skips its own POST /negotiate/start entirely and opens directly into
// an already-running session — used by NegotiationNotification to
// re-open the session useCartAbandonment auto-started earlier, without
// minting a second, redundant negotiation for the same cart. Omit both
// (the original call shape) and this behaves exactly as it always has.
// compact (Phase 9): drops the side-by-side "live audit trail" column —
// used inside NegotiationNotification's narrow floating widget, where
// that second column has no room and would overflow its container.
// autoAccept (Phase 10): fires one fixed "accept" reply automatically as
// soon as a resumed session's opening message is loaded — used by the
// popup's "Accept Offer" quick-action. Reuses this exact same
// send/accept/handoff/checkout code path (real /negotiate/message call,
// real gate-verified handoff) rather than a separate accept mechanism.
export default function NegotiationPanel({
  product,
  onClose,
  onDone,
  onStatus,
  resumeSessionId = null,
  resumeMessage = null,
  compact = false,
  autoAccept = false,
}) {
  const [sessionId, setSessionId] = useState(resumeSessionId);
  const [messages, setMessages] = useState([]);
  const [offerStatus, setOfferStatus] = useState("none");
  const [proposedOffer, setProposedOffer] = useState(null);
  const [closed, setClosed] = useState(false);
  const [handoff, setHandoff] = useState(false);
  const [checkoutAmount, setCheckoutAmount] = useState(null);
  const [approvalToken, setApprovalToken] = useState(null);
  const [auditEntries, setAuditEntries] = useState([]);
  const [input, setInput] = useState("");
  const [starting, setStarting] = useState(!resumeSessionId);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  // Phase 4 (idempotency): one stable key for this panel's own
  // /negotiate/start attempt — lazily generated once and reused for the
  // component's lifetime (React StrictMode's dev-only double-invoke of
  // this effect reuses it, correctly de-duped server-side by
  // Idempotency-Key, instead of minting two live negotiation sessions).
  const startIdempotencyKeyRef = useRef(null);
  function startIdempotencyKey() {
    if (!startIdempotencyKeyRef.current) startIdempotencyKeyRef.current = crypto.randomUUID();
    return startIdempotencyKeyRef.current;
  }

  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);

  const pollRef = useRef(null);
  const auditListRef = useRef(null);
  const messagesEndRef = useRef(null);
  const autoAcceptSentRef = useRef(false);
  const navigate = useNavigate();

  // Derived, not fetched separately — the same real gate_call/gate_decision
  // audit events already polled above (see the AUDIT_POLL_MS effect) are
  // the authoritative record of what policy-gate actually decided. This
  // just picks out the latest one so PolicyGateCard always reflects the
  // real, most recent /evaluate result for this session.
  const gateState = useMemo(() => {
    const lastCall = [...auditEntries].reverse().find((e) => e.event_type === "gate_call");
    const lastDecision = [...auditEntries].reverse().find((e) => e.event_type === "gate_decision");
    if (!lastCall && !lastDecision) return null;
    const requestedValue = lastDecision?.payload?.approved
      ? lastDecision.payload.final_terms?.value
      : (lastCall?.payload?.requested_offer?.value ?? proposedOffer?.value ?? null);
    if (!lastDecision || (lastCall && lastCall.id > lastDecision.id)) {
      return { decision: "pending", requestedValue: lastCall?.payload?.requested_offer?.value ?? requestedValue, reason: null, maxAllowed: null };
    }
    return {
      decision: lastDecision.payload.approved ? "approved" : "rejected",
      requestedValue,
      reason: lastDecision.payload.reason ?? null,
      maxAllowed: lastDecision.payload.max_allowed ?? null,
    };
  }, [auditEntries, proposedOffer]);

  // Phase 20: persist the accepted negotiation to cart state the MOMENT
  // handoff actually happens — not only when/if the shopper clicks a
  // specific button — so Cart.jsx shows the negotiated price for this
  // line even if they just close the popup and go look at their cart
  // themselves, rather than the discount only ever existing inside this
  // one-shot panel.
  useEffect(() => {
    if (handoff && approvalToken) {
      markNegotiationAccepted(product.id, { approvalToken, checkoutAmount, sessionId });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handoff, approvalToken, checkoutAmount, sessionId]);

  useEffect(() => {
    if (resumeSessionId) {
      // Already-running session — just render its opening message,
      // don't call /negotiate/start again.
      setMessages(resumeMessage ? [{ role: "assistant", content: resumeMessage }] : []);
      return undefined;
    }

    let cancelled = false;

    async function start() {
      try {
        const res = await fetch(`${API_BASE_URL}/negotiate/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Idempotency-Key": startIdempotencyKey() },
          body: JSON.stringify({ product_id: product.id, cart_quantity: 1 }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || "Failed to start negotiation");
        }
        const data = await res.json();
        if (cancelled) return;
        setSessionId(data.session_id);
        setMessages(data.message ? [{ role: "assistant", content: data.message }] : []);
        setOfferStatus(data.offer_status);
        setProposedOffer(data.proposed_offer);
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          toastError(err.message);
        }
      } finally {
        if (!cancelled) setStarting(false);
      }
    }

    start();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product.id, resumeSessionId]);

  useEffect(() => {
    if (!sessionId) return undefined;

    async function poll() {
      try {
        const res = await fetch(`${API_BASE_URL}/negotiate/${sessionId}/audit`);
        if (res.ok) setAuditEntries(await res.json());
      } catch {
        // Best-effort — audit trail is a live view, not critical path.
      }
    }

    poll();
    pollRef.current = setInterval(poll, AUDIT_POLL_MS);
    return () => clearInterval(pollRef.current);
  }, [sessionId]);

  useEffect(() => {
    if (autoAccept && resumeSessionId && !autoAcceptSentRef.current && messages.length > 0 && !closed && !handoff) {
      autoAcceptSentRef.current = true;
      handleSend("Yes, I'll take it — let's proceed.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAccept, resumeSessionId, messages.length, closed, handoff]);

  useEffect(() => {
    auditListRef.current?.scrollTo({ top: auditListRef.current.scrollHeight, behavior: "smooth" });
  }, [auditEntries]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(overrideMessage) {
    const userMessage = (overrideMessage ?? input).trim();
    if (!userMessage || sending || closed) return;

    setSending(true);
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    if (overrideMessage === undefined) setInput("");

    try {
      const res = await fetch(`${API_BASE_URL}/negotiate/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, user_message: userMessage }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to send message");
      }
      const data = await res.json();
      setMessages((prev) => (data.message ? [...prev, { role: "assistant", content: data.message }] : prev));
      setOfferStatus(data.offer_status);
      setProposedOffer(data.proposed_offer);
      setClosed(data.closed);
      setHandoff(data.handoff);
      setCheckoutAmount(data.checkout_amount);
      setApprovalToken(data.approval_token);
    } catch (err) {
      setError(err.message);
      toastError(err.message);
    } finally {
      setSending(false);
    }
  }

  async function handleCheckout() {
    setError(null);
    try {
      await startCheckout({
        product,
        approvalToken,
        sessionId,
        onStatus,
        onClose: (paid) => {
          if (!paid) return;
          // The approval_token this line was showing is now redeemed —
          // remove the line and the negotiated-price state so a second
          // visit to the cart doesn't show a price that's no longer
          // honorable (the backend would reject it anyway; this just
          // keeps the UI honest about it too).
          removeFromCart(product.id);
          clearNegotiationAccepted();
          onDone?.(); // nothing left for this popup to do — fully close it
        },
      });
    } catch (err) {
      setError(err.message);
      toastError(err.message);
    }
  }

  // Phase 20: the alternative to checking out immediately from inside
  // this popup — go look at the cart instead, where this same negotiated
  // price (persisted above, the instant handoff happened) is now showing
  // for this product's line, ready to check out from there whenever.
  //
  // Bug fixed Phase 20: this used to call onClose (minimize), which just
  // collapsed the note back to its ORIGINAL pre-negotiation prompt —
  // "Accept Offer" / "Not right now" — even though the deal was already
  // done, since the collapsed view has no idea this panel ever reached
  // handoff. Calling onDone (a full close, not a minimize) instead avoids
  // resurfacing a stale, actively misleading prompt for an already-agreed
  // negotiation.
  function handleGoToCart() {
    onDone?.();
    navigate("/shop/cart");
  }

  return (
    <div className={`mt-4 flex flex-col gap-4 border-t border-putty pt-4 ${compact ? "" : "md:flex-row"}`}>
      <div
        className={`flex flex-1 flex-col rounded-md border border-putty-dark bg-ivory-deep/40 p-3 ${
          compact ? "min-h-[220px]" : "min-h-[280px]"
        }`}
      >
        <div className="mb-1 flex items-center justify-between">
          <p className="font-display text-sm font-semibold text-ink">AI Negotiation — {product.name}</p>
          {!compact && (
            <button onClick={onClose} className="text-sm text-ink-soft/60 hover:text-ink-soft">
              Close
            </button>
          )}
        </div>
        {!compact && (
          <p className="mb-2 font-body text-[11px] text-ink-soft/70">
            The seller AI can negotiate, but it cannot authorize arbitrary discounts — every offer is independently checked by the Policy Gate below.
          </p>
        )}

        <div className="mb-2 flex-1 space-y-2 overflow-y-auto">
          {starting && <p className="font-body text-sm text-ink-soft">Starting negotiation...</p>}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`max-w-[85%] rounded-md px-3 py-2 font-body text-sm ${
                msg.role === "assistant"
                  ? "border border-putty-dark bg-ivory text-ink"
                  : "ml-auto bg-clay text-ivory"
              }`}
            >
              {msg.content}
            </div>
          ))}
          {sending && (
            <div className="max-w-[85%] rounded-md border border-putty-dark bg-ivory px-3 py-2 font-body text-sm text-ink-soft/70">
              Seller agent is analyzing...
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {error && <p className="mb-2 text-sm text-rose-700">{error}</p>}

        {gateState && (
          <div className="mb-3">
            <PolicyGateCard
              catalogPrice={product.price}
              requestedValue={gateState.requestedValue}
              decision={gateState.decision}
              reason={gateState.reason}
              maxAllowed={gateState.maxAllowed}
            />
          </div>
        )}

        {handoff ? (
          <div className="space-y-2 rounded-md border border-moss-light bg-moss-light/15 p-3">
            <p className="font-body text-sm font-semibold text-moss-dark">
              Offer accepted — final price ₹{((checkoutAmount ?? 0) / 100).toFixed(2)}
            </p>
            <p className="font-body text-xs text-moss-dark/80">
              This price is already reflected in your cart — pay now, or check out from there whenever you're ready.
            </p>
            <div className="flex gap-2">
              <button
                onClick={handleCheckout}
                className="flex-1 rounded-sm bg-moss px-4 py-2 text-sm font-semibold text-ivory shadow-sm transition-colors hover:bg-moss-dark"
              >
                Pay now
              </button>
              <button
                onClick={handleGoToCart}
                className="flex-1 rounded-sm border border-moss px-4 py-2 text-sm font-semibold text-moss-dark transition-colors hover:bg-moss-light/30"
              >
                Go to cart
              </button>
            </div>
          </div>
        ) : closed ? (
          <p className="font-body text-sm text-ink-soft">Negotiation ended ({offerStatus}).</p>
        ) : (
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              disabled={starting || sending}
              placeholder="Type your reply..."
              className="flex-1 rounded-sm border border-putty-dark bg-ivory px-3 py-2 font-body text-sm text-ink placeholder:text-ink-soft/50 focus:border-clay focus:outline-none focus:ring-1 focus:ring-clay"
            />
            <button
              onClick={handleSend}
              disabled={starting || sending || !input.trim()}
              className="rounded-sm bg-clay px-4 py-2 text-sm font-semibold text-ivory transition-colors hover:bg-clay-dark disabled:bg-putty disabled:text-ink-soft/50"
            >
              Send
            </button>
          </div>
        )}
      </div>

      {!compact && (
      <div className="w-full md:w-72">
        <button
          type="button"
          onClick={() => setShowTechnicalDetails((s) => !s)}
          className="flex w-full items-center justify-between rounded-md border border-putty-dark bg-ivory px-3 py-2"
        >
          <span className="flex items-center gap-2 font-body text-sm font-semibold text-ink-soft">
            Technical details <LiveBadge color="moss" />
          </span>
          <span className="text-ink-soft/60">{showTechnicalDetails ? "−" : "+"}</span>
        </button>
        {showTechnicalDetails && (
          <div ref={auditListRef} className="mt-2 max-h-[340px] overflow-y-auto rounded-md border border-putty-dark bg-ivory p-3">
            <p className="mb-2 font-body text-[11px] text-ink-soft/60">
              Session <span className="font-mono">{sessionId ? `${sessionId.slice(0, 8)}...` : "—"}</span> — raw audit
              events for this negotiation, as recorded server-side.
            </p>
            {auditEntries.length === 0 && <p className="text-xs text-ink-soft/60">No events yet.</p>}
            <ul className="space-y-2">
              {auditEntries.map((entry) => (
                <li key={entry.id} className="rounded-sm border border-putty bg-ivory-deep/40 p-2 text-xs">
                  <p className="font-mono font-semibold text-ink-soft">{entry.event_type}</p>
                  <p className="text-ink-soft/50">{new Date(entry.created_at).toLocaleTimeString()}</p>
                  <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-ink-soft/70">
                    {JSON.stringify(entry.payload, null, 2)}
                  </pre>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      )}
    </div>
  );
}
