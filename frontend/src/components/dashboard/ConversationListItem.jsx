import { translateEvent } from "../../utils/eventTranslation.js";

function kindBadge(group) {
  if (group.payment) return { text: "purchased", cls: "bg-emerald-100 text-emerald-800" };
  if (group.token_rejected) return { text: "token rejected", cls: "bg-rose-100 text-rose-800" };
  if (group.purchase_quote) return { text: "402 quoted", cls: "bg-amber-100 text-amber-800" };
  if (group.gate_decision) {
    return group.gate_decision.approved
      ? { text: "gate approved", cls: "bg-emerald-100 text-emerald-800" }
      : { text: "gate rejected", cls: "bg-rose-100 text-rose-800" };
  }
  return { text: group.kind, cls: "bg-violet-100 text-violet-800" };
}

export default function ConversationListItem({ group, selected, unread, onClick }) {
  const lastEvent = group.events[group.events.length - 1];
  const preview = lastEvent ? translateEvent(lastEvent).sentence : group.headline;
  const badge = kindBadge(group);

  return (
    <li>
      <button
        onClick={onClick}
        className={`flex w-full flex-col items-start gap-0.5 border-l-2 px-4 py-3 text-left transition-colors ${
          selected ? "border-violet-600 bg-violet-100" : "border-transparent hover:bg-violet-50"
        }`}
      >
        <div className="flex w-full items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1.5 truncate font-mono text-sm font-semibold text-violet-950">
            {unread && <span className="h-2 w-2 shrink-0 rounded-full bg-blue-500" aria-label="unread" />}
            <span className="truncate">{group.buyer_agent_id}</span>
          </span>
          <span className="shrink-0 font-mono text-[11px] text-violet-400">
            {new Date(group.last_updated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>
        {group.product_name && <p className="truncate font-mono text-xs font-medium text-violet-600">{group.product_name}</p>}
        <p className="w-full truncate font-mono text-xs text-violet-500">{preview}</p>
        <span className={`mt-1 rounded-sm px-2 py-0.5 font-mono text-[10px] font-medium ${badge.cls}`}>{badge.text}</span>
      </button>
    </li>
  );
}
