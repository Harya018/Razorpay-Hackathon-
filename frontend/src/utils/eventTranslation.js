// Human-readable translation layer for raw audit_log rows.
//
// Every event_type and reason code handled here was confirmed by grepping
// the actual backend/policy-gate source (not guessed):
//   - event_type="..." across backend/app/agent/nodes.py,
//     backend/app/routes/agent_commerce.py, backend/app/routes/payments.py
//   - reason="..." across policy-gate/app/routes/evaluate.py (/evaluate,
//     /verify) and the dynamic "gate_unreachable: {e}" from
//     backend/app/gate_client.py
//
// All money fields on these payloads (offer "value", "final_terms.value",
// "max_allowed", "amount", "unit_price", "quoted_amount",
// "charged_original_price") are paise, and where an offer is involved they
// represent the FINAL TOTAL price, not a discount delta — confirmed by
// evaluate.py's `final_amount=offer.value` and nodes.py's `_offer_summary`.

export function rupees(paise) {
  return paise == null ? "—" : `₹${(paise / 100).toFixed(2)}`;
}

const REASON_TRANSLATIONS = {
  attempt_cap_exceeded: "the negotiation had already used up its allowed number of offer attempts",
  no_offer_to_evaluate: "no discount or bundle was actually proposed",
  missing_discount_value: "the proposed discount didn't include a price",
  discount_value_exceeds_original_price: "the proposed price was higher than the original listed price",
  below_floor_or_exceeds_max_discount: "the requested discount was below what we can profitably offer",
  bundle_has_no_priced_terms_to_evaluate: "the proposed bundle didn't include a final price",
  bundle_effective_price_below_floor: "the bundle's effective price was below what we can profitably offer",
  unknown_offer_type: "the offer type wasn't one the gate recognizes",
  unknown_token: "the approval token isn't recognized",
  token_not_approved: "the approval token was for an offer that was never approved",
  token_already_used: "the approval token was already used on a previous checkout",
  terms_mismatch: "the checkout details didn't match what was approved",
};

// gate_unreachable is dynamic ("gate_unreachable: <exception message>"), not
// a fixed code — matched by prefix rather than exact lookup.
export function translateReason(reason) {
  if (!reason) return null;
  if (reason in REASON_TRANSLATIONS) return REASON_TRANSLATIONS[reason];
  if (reason.startsWith("gate_unreachable")) return "the policy gate couldn't be reached";
  return reason; // unknown code — show the raw string rather than invent a sentence
}

const OFFER_SHAPE_LABEL = { discount: "a discount", bundle: "a bundle", none: "no offer" };
const INTENT_LABEL = { accept: "accepted", reject: "declined", counter: "countered", off_topic: "went off-topic" };
const CLOSED_REASON_LABEL = {
  accepted: "the shopper accepted",
  rejected: "the shopper declined",
  attempt_cap_reached: "the attempt limit was reached",
  no_offer_made: "no offer was ever made",
};

const badge = (text, cls) => ({ text, cls });
const B = {
  neutral: (text) => badge(text, "bg-slate-100 text-slate-600"),
  info: (text) => badge(text, "bg-blue-100 text-blue-800"),
  pending: (text) => badge(text, "bg-amber-100 text-amber-800"),
  good: (text) => badge(text, "bg-emerald-100 text-emerald-800"),
  bad: (text) => badge(text, "bg-rose-100 text-rose-800"),
  agent: (text) => badge(text, "bg-violet-100 text-violet-800"),
};

const TRANSLATORS = {
  cart_assessed(p) {
    return {
      sentence: `Shopper added ${p.quantity} × ${p.product_name} (${rupees(p.unit_price)} each) to the cart.`,
      badge: B.neutral("cart"),
    };
  },

  offer_decision(p) {
    const reasoning = p.reasoning ? ` — "${p.reasoning}"` : "";
    if (p.should_offer) {
      return {
        sentence: `Decided to offer ${OFFER_SHAPE_LABEL[p.offer_shape] || p.offer_shape} (attempt ${p.attempt_number})${reasoning}`,
        badge: B.info("planning offer"),
      };
    }
    return {
      sentence: `Decided not to make an offer (attempt ${p.attempt_number})${reasoning}`,
      badge: B.neutral("no offer"),
    };
  },

  gate_call(p) {
    const offer = p.requested_offer || {};
    const fallbackNote = p.is_fallback ? " — this is the merchant's fallback ceiling" : "";
    return {
      sentence: `Sent a ${offer.type} proposal (${rupees(offer.value)}) to the policy gate for review${fallbackNote} (attempt ${p.attempt_number}).`,
      badge: B.pending("→ gate"),
    };
  },

  gate_decision(p) {
    if (p.approved) {
      return {
        sentence: `Policy gate approved the offer at ${rupees(p.final_terms?.value)}.`,
        badge: B.good("gate approved"),
      };
    }
    const ceiling = p.max_allowed != null ? ` (most it would allow: ${rupees(p.max_allowed)})` : "";
    return {
      sentence: `Policy gate rejected the offer — ${translateReason(p.reason)}${ceiling}.`,
      badge: B.bad("gate rejected"),
    };
  },

  offer_generation_failed(p) {
    return {
      sentence: `Agent failed to generate a usable offer on attempt ${p.attempt_number} (${p.error}).`,
      badge: B.bad("generation failed"),
    };
  },

  offer_proposed(p) {
    return {
      sentence: `Proposed to the shopper: ${p.type} at ${rupees(p.value)} — "${p.message}"`,
      badge: B.info("offer sent"),
    };
  },

  response_interpreted(p) {
    const label = INTENT_LABEL[p.intent] || p.intent;
    const badgeByIntent = { accept: B.good, reject: B.bad, counter: B.pending, off_topic: B.neutral }[p.intent] || B.neutral;
    return {
      sentence: `Shopper said: "${p.user_message}" — interpreted as ${label}.`,
      badge: badgeByIntent(label),
    };
  },

  negotiation_closed(p) {
    const reasonLabel = CLOSED_REASON_LABEL[p.closed_reason] || p.closed_reason;
    const badgeByStatus = { accepted: B.good, rejected: B.bad }[p.final_status] || B.neutral;
    return {
      sentence: `Negotiation closed after ${p.turns} turn(s) — ${reasonLabel} (final status: ${p.final_status}).`,
      badge: badgeByStatus(p.final_status || "closed"),
    };
  },

  agent_negotiate_requested(p) {
    const terms = p.proposed_terms || {};
    return {
      sentence: `Buyer agent ${p.buyer_agent_id} proposed ${terms.type} at ${rupees(terms.value)}.`,
      badge: B.agent("agent proposal"),
    };
  },

  agent_negotiate_decided(p) {
    if (p.approved) {
      return {
        sentence: `Policy gate approved buyer agent ${p.buyer_agent_id}'s offer at ${rupees(p.final_terms?.value)}.`,
        badge: B.good("gate approved"),
      };
    }
    const ceiling = p.max_allowed != null ? ` (most it would allow: ${rupees(p.max_allowed)})` : "";
    return {
      sentence: `Policy gate rejected buyer agent ${p.buyer_agent_id}'s offer — ${translateReason(p.reason)}${ceiling}.`,
      badge: B.bad("gate rejected"),
    };
  },

  agent_purchase_402(p) {
    return {
      sentence: `Buyer agent ${p.buyer_agent_id} requested purchase — quoted ${rupees(p.quoted_amount)}, awaiting payment.`,
      badge: B.pending("402 quoted"),
    };
  },

  agent_payment_completed(p) {
    return {
      sentence: `Buyer agent ${p.buyer_agent_id} completed payment of ${rupees(p.amount)}.`,
      badge: B.good("purchased"),
    };
  },

  checkout_token_rejected(p) {
    const who = p.buyer_agent_id ? `Buyer agent ${p.buyer_agent_id}` : "Shopper";
    return {
      sentence: `${who} presented a checkout token that was rejected — ${translateReason(p.reason)}. Charged full price ${rupees(p.charged_original_price)}.`,
      badge: B.bad("token rejected"),
    };
  },

  customer_mindset_summary(p) {
    return {
      sentence: `AI-generated insight (not a verified customer profile): ${p.summary}`,
      badge: B.agent("AI insight"),
    };
  },

  order_created(p) {
    const priceNote = p.discount_applied ? "negotiated discount applied" : "full price";
    return {
      sentence: `Order created for ${p.quantity} unit(s) at ${rupees(p.amount)} (${priceNote}).`,
      badge: B.good("order created"),
    };
  },
};

// Falls back to a literal, non-fabricated label for any event_type not in
// the map above — should not happen given the grep above, but this is a
// safety net, not a source of invented text.
export function translateEvent(event) {
  const translator = TRANSLATORS[event.event_type];
  if (!translator) {
    return { sentence: `${event.event_type} event.`, badge: B.neutral(event.event_type) };
  }
  return translator(event.payload || {});
}

// Structured Buyer / Product / Requested / Gate said / Final price summary
// for the human-negotiation "Details" panel, built from the already
// server-aggregated session object returned by GET /dashboard/negotiations.
export function humanSessionSummary(session) {
  return [
    { label: "Shopper", value: `session ${session.session_id.slice(0, 8)}` },
    { label: "Product", value: session.product_name || "—" },
    {
      label: "Requested",
      value: session.proposed_offer ? `${session.proposed_offer.type} at ${rupees(session.proposed_offer.value)}` : "no offer yet",
    },
    {
      label: "Gate said",
      value: !session.gate_decision
        ? "not evaluated yet"
        : session.gate_decision.approved
        ? "approved"
        : `rejected — ${translateReason(session.gate_decision.reason)}`,
    },
    {
      label: "Final price",
      value: !session.closed
        ? "negotiation still in progress"
        : session.final_status === "accepted" && session.proposed_offer
        ? rupees(session.proposed_offer.value)
        : `not completed (${session.final_status || "no offer"})`,
    },
  ];
}

// Same shape for the agent-to-agent "Details" panel, built from the
// server-aggregated group object returned by GET /dashboard/agent-activity.
export function agentGroupSummary(group) {
  return [
    { label: "Buyer agent", value: group.buyer_agent_id || "—" },
    {
      label: "Product",
      value: group.purchase_quote?.product_id != null ? `product #${group.purchase_quote.product_id}` : "—",
    },
    {
      label: "Requested",
      value: group.proposed_terms ? `${group.proposed_terms.type} at ${rupees(group.proposed_terms.value)}` : "—",
    },
    {
      label: "Gate said",
      value: group.gate_decision
        ? group.gate_decision.approved
          ? "approved"
          : `rejected — ${translateReason(group.gate_decision.reason)}`
        : group.token_rejected
        ? `token rejected — ${translateReason(group.token_rejected.reason)}`
        : "not evaluated yet",
    },
    {
      label: "Final price",
      value: group.payment
        ? rupees(group.payment.amount)
        : group.purchase_quote
        ? `quoted ${rupees(group.purchase_quote.quoted_amount)}, not yet paid`
        : "—",
    },
  ];
}

// Event types the buyer agent itself emits/initiates, vs. ones that are the
// merchant/gate's response — used by ChatBubble to pick bubble side.
export const BUYER_EVENT_TYPES = new Set(["agent_negotiate_requested", "agent_purchase_402", "agent_payment_completed"]);
