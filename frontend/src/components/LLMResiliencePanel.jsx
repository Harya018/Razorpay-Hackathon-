import { useEffect, useState } from "react";

import Card from "./Card.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

function Tier({ label, ok, sub }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-putty-dark bg-ivory px-3 py-2">
      <div>
        <p className="font-body text-sm font-medium text-ink">{label}</p>
        {sub && <p className="font-body text-[11px] text-ink-soft/60">{sub}</p>}
      </div>
      <span className={`flex items-center gap-1.5 font-body text-xs font-semibold ${ok ? "text-moss-dark" : "text-ink-soft/50"}`}>
        <span className={`h-2 w-2 rounded-full ${ok ? "bg-moss" : "bg-putty-dark"}`} />
        {ok ? "Configured" : "Not configured"}
      </span>
    </div>
  );
}

export default function LLMResiliencePanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/dashboard/llm-provider-status`)
      .then(async (res) => {
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to load LLM provider status");
        return res.json();
      })
      .then(setData)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <Card title="LLM Resilience"><p className="font-body text-sm text-rose-700">{error}</p></Card>;
  if (!data) return <Card title="LLM Resilience"><p className="font-body text-sm text-ink-soft">Loading...</p></Card>;

  const c = data.providers_configured;

  return (
    <Card title="LLM Resilience" note="Configuration and real fallback usage — never a simulated outage.">
      <div className="space-y-2">
        <Tier label="Primary — Groq" ok={c.groq_primary} />
        <Tier label="Fallback — Groq (secondary key)" ok={c.groq_secondary} sub="A second key on the same account shares its quota — helps only with non-quota errors" />
        <Tier label="Fallback — Gemini" ok={c.gemini} sub="A genuinely separate provider/quota pool" />
        <Tier label="Deterministic safe fallback" ok={data.demo_fallback_mode || data.demo_mode} sub={data.demo_fallback_mode || data.demo_mode ? "Ready — used only if every real provider fails" : "Off — a total provider failure would surface as an error, not a silent guess"} />
      </div>
      <p className="mt-3 font-body text-xs text-ink-soft/70">
        Deterministic fallback actually used, recent history: <span className="font-semibold text-ink">{data.deterministic_fallback_used_recent_count}</span> time(s)
        {data.deterministic_fallback_last_used_at && ` — last at ${new Date(data.deterministic_fallback_last_used_at).toLocaleString()}`}.
      </p>
      <p className="mt-1 font-body text-[11px] text-ink-soft/50">{data.note}</p>
    </Card>
  );
}
