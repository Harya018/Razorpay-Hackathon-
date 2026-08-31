import { BUYER_EVENT_TYPES, translateEvent } from "../../utils/eventTranslation.js";

// One message in a conversation thread. Every string rendered here goes
// through plain JSX text interpolation — never dangerouslySetInnerHTML —
// so React escapes it automatically; an adversarial, SQL-injection- or
// markup-shaped payload (see /red-team-agent's malformed_terms attack)
// renders as inert text in the bubble, never interpreted or executed.
export default function ChatBubble({ event }) {
  const isBuyer = BUYER_EVENT_TYPES.has(event.event_type);
  const { sentence, badge } = translateEvent(event);

  return (
    <div className={`flex ${isBuyer ? "justify-start" : "justify-end"}`}>
      <div
        className={`max-w-[75%] rounded-sm px-3 py-2 font-mono text-sm ${
          isBuyer ? "border border-dashed border-violet-400 bg-violet-50 text-violet-950" : "bg-slate-700 text-white"
        }`}
      >
        <p className={`text-[10px] font-semibold uppercase tracking-wide ${isBuyer ? "text-violet-500" : "text-slate-300"}`}>
          {isBuyer ? "Buyer Agent (LLM)" : "Merchant Gate"}
        </p>
        <span
          className={`mt-1 inline-block rounded-sm px-2 py-0.5 text-[10px] font-medium ${
            isBuyer ? badge.cls : "bg-white/20 text-white"
          }`}
        >
          {badge.text}
        </span>
        <p className="mt-1 whitespace-pre-wrap break-words">{sentence}</p>
        <p className={`mt-1 text-right text-[10px] ${isBuyer ? "text-violet-400" : "text-slate-300"}`}>
          {new Date(event.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </p>
      </div>
    </div>
  );
}
