import ConversationListItem from "./ConversationListItem.jsx";

// Fed the SAME groups array the page already fetched from
// GET /dashboard/agent-activity (already sorted most-recent-first by the
// backend) — no separate request. Clicking a row selects that
// conversation; the page owns which one is selected and clears its
// unread flag.
export default function ConversationList({ groups, selectedKey, unreadKeys, onSelect }) {
  if (groups.length === 0) {
    return <p className="p-4 font-mono text-xs text-violet-400">No agent-to-agent activity yet.</p>;
  }

  return (
    <ul className="divide-y divide-violet-100">
      {groups.map((g) => (
        <ConversationListItem
          key={g.group_key}
          group={g}
          selected={g.group_key === selectedKey}
          unread={unreadKeys.has(g.group_key)}
          onClick={() => onSelect(g.group_key)}
        />
      ))}
    </ul>
  );
}
