import { useEffect, useState } from "react";

import Card from "./Card.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

function truncate(id) {
  return id.length > 12 ? `${id.slice(0, 8)}****${id.slice(-4)}` : id;
}

export default function WebhookPanel() {
  const [events, setEvents] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/admin/webhooks/recent`)
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to load webhook history");
        return res.json();
      })
      .then(setEvents)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <Card
      title="Webhook Center"
      note="Every row below already passed HMAC signature verification and the staleness check — a failed webhook never reaches this table at all, it 400s before insertion."
    >
      {error && <p className="font-body text-sm text-rose-700">{error}</p>}
      {!events && !error && <p className="font-body text-sm text-ink-soft">Loading...</p>}
      {events && events.length === 0 && (
        <p className="font-body text-sm text-ink-soft/60">No webhook deliveries recorded yet.</p>
      )}
      {events && events.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] font-body text-sm">
            <thead>
              <tr className="border-b border-putty-dark text-left text-[11px] font-semibold uppercase tracking-wide text-ink-soft/70">
                <th className="py-2 pr-2">Event ID</th>
                <th className="py-2 pr-2">Type</th>
                <th className="py-2 pr-2">Signature</th>
                <th className="py-2 pr-2">Dedup</th>
                <th className="py-2">Received</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-b border-putty-dark/60 last:border-b-0">
                  <td className="py-2 pr-2 font-mono text-xs text-ink-soft">{truncate(e.event_id)}</td>
                  <td className="py-2 pr-2 text-ink">{e.event_type || "—"}</td>
                  <td className="py-2 pr-2 text-moss-dark">✓ Verified</td>
                  <td className="py-2 pr-2 text-moss-dark">✓ Checked</td>
                  <td className="py-2 text-ink-soft/70">{new Date(e.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
