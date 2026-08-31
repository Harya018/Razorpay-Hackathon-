import { useEffect, useRef, useState } from "react";

import { agentGroupSummary } from "../../utils/eventTranslation.js";
import ChatBubble from "./ChatBubble.jsx";

export default function ChatThread({ group }) {
  const bottomRef = useRef(null);
  const [showDetails, setShowDetails] = useState(false);
  const [showRaw, setShowRaw] = useState(false);
  const prevCountRef = useRef({ key: null, count: 0 });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [group?.events?.length, group?.group_key]);

  // Ledger "new entry" tick: only bubbles appended since we last rendered
  // THIS conversation flash — switching threads never re-ticks history.
  const sameThread = prevCountRef.current.key === group?.group_key;
  const tickFrom = sameThread ? prevCountRef.current.count : Infinity;
  useEffect(() => {
    prevCountRef.current = { key: group?.group_key ?? null, count: group?.events?.length ?? 0 };
  }, [group?.group_key, group?.events?.length]);

  // Collapse the details panel when switching conversations, so it
  // doesn't stay open showing the PREVIOUS thread's data underneath.
  useEffect(() => {
    setShowDetails(false);
    setShowRaw(false);
  }, [group?.group_key]);

  if (!group) {
    return (
      <div className="flex h-full items-center justify-center p-6 font-mono text-sm text-violet-400">
        Select a conversation to view it.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-violet-200 px-4 py-3">
        <p className="font-mono text-sm font-semibold text-violet-950">{group.buyer_agent_id}</p>
        <p className="font-mono text-xs text-violet-500">
          {group.product_name || "Unknown product"} - session {group.group_key.slice(0, 8)}
        </p>
        <button
          className="mt-1 font-mono text-xs font-medium text-violet-600 hover:text-violet-800"
          onClick={() => setShowDetails((v) => !v)}
        >
          {showDetails ? "Hide details" : "Details"}
        </button>
        {showDetails && (
          <div className="mt-2 space-y-2 border border-dashed border-violet-300 bg-violet-50 p-2.5">
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-xs">
              {agentGroupSummary(group).map((row) => (
                <div key={row.label} className="contents">
                  <dt className="font-medium text-violet-500">{row.label}</dt>
                  <dd className="text-violet-800">{row.value}</dd>
                </div>
              ))}
            </dl>
            <button
              className="font-mono text-xs font-medium text-violet-400 hover:text-violet-600"
              onClick={() => setShowRaw((v) => !v)}
            >
              {showRaw ? "Hide raw event data" : "Raw event data"}
            </button>
            {showRaw && (
              <pre className="overflow-x-auto whitespace-pre-wrap border border-violet-200 bg-content p-2 font-mono text-xs text-violet-700">
                {JSON.stringify(group.events, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {group.events.map((e, i) => (
          <div key={i} className={i >= tickFrom ? "ledger-row-tick" : ""}>
            <ChatBubble event={e} />
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
