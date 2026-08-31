import { useEffect, useRef, useState } from "react";

import ChatThread from "../../components/dashboard/ChatThread.jsx";
import ConversationList from "../../components/dashboard/ConversationList.jsx";
import LiveBadge from "../../components/LiveBadge.jsx";
import useDashboardStream from "../../hooks/useDashboardStream.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export default function AgentConversationsPage() {
  const [groups, setGroups] = useState([]);
  const [selectedKey, setSelectedKey] = useState(null);
  const [unreadKeys, setUnreadKeys] = useState(new Set());
  const [version, setVersion] = useState(0);
  const selectedKeyRef = useRef(null);
  selectedKeyRef.current = selectedKey;

  const connected = useDashboardStream((data) => {
    if (data.channel === "agent") setVersion((v) => v + 1);
  });

  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/agent-activity?limit=30`)
      .then((res) => res.json())
      .then((data) => {
        setGroups((prevGroups) => {
          // A conversation whose last_updated moved forward since the
          // previous fetch got a new message — flag it unread unless
          // it's the one currently open (already-open threads never
          // need an unread dot; ChatThread's own auto-scroll handles
          // "new message while I'm looking at it").
          const prevByKey = Object.fromEntries(prevGroups.map((g) => [g.group_key, g.last_updated]));
          setUnreadKeys((prevUnread) => {
            const next = new Set(prevUnread);
            for (const g of data) {
              const isNew = prevByKey[g.group_key] !== undefined && g.last_updated !== prevByKey[g.group_key];
              if (isNew && g.group_key !== selectedKeyRef.current) next.add(g.group_key);
            }
            return next;
          });
          return data;
        });
        setSelectedKey((prev) => (prev && data.some((g) => g.group_key === prev) ? prev : data[0]?.group_key ?? null));
      })
      .catch(() => {});
  }, [version]);

  function handleSelect(key) {
    setSelectedKey(key);
    setUnreadKeys((prev) => {
      if (!prev.has(key)) return prev;
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
  }

  const selectedGroup = groups.find((g) => g.group_key === selectedKey) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="font-mono text-xl font-bold tracking-tight text-slate-100">AI Buyer Agents</h1>
        {connected ? (
          <LiveBadge color="violet" label="Live" />
        ) : (
          <span className="rounded-sm bg-white/10 px-2 py-0.5 font-mono text-xs font-medium text-slate-400">connecting...</span>
        )}
      </div>

      <div className="flex h-[calc(100vh-220px)] overflow-hidden rounded-sm border border-violet-400/40 bg-content">
        <div className="w-72 shrink-0 overflow-y-auto border-r border-violet-200 sm:w-80">
          <ConversationList groups={groups} selectedKey={selectedKey} unreadKeys={unreadKeys} onSelect={handleSelect} />
        </div>
        <div className="min-w-0 flex-1 bg-content">
          <ChatThread group={selectedGroup} />
        </div>
      </div>
    </div>
  );
}
