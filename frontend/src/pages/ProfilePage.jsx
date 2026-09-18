import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import Card from "../components/Card.jsx";
import { Badge, ErrorBox, Field, SkeletonRows, readError } from "../components/ui.jsx";
import { signOut } from "../lib/auth.js";
import { toastError, toastSuccess } from "../lib/toast.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const EDITABLE = [
  ["display_name", "Display name", "text"],
  ["phone", "Phone", "tel"],
  ["address_line", "Address", "text"],
  ["city", "City", "text"],
  ["pincode", "Pincode", "text"],
];

// One component, two contexts (customer /profile, merchant
// /dashboard/profile). Identity fields (email, avatar, provider, session
// times) come straight from the verified token via GET /profile and are
// read-only — the backend has no way to change them (that's Supabase's
// job). The only editable fields are the ones the backend actually
// stores (CustomerProfile): display name + contact/shipping details.
export default function ProfilePage({ merchant = false }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({});
  const [saving, setSaving] = useState(false);

  function load() {
    fetch(`${API_BASE_URL}/profile`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await readError(res, "Couldn't load profile"));
        return res.json();
      })
      .then((d) => {
        setData(d);
        setDraft(Object.fromEntries(EDITABLE.map(([k]) => [k, d.profile[k] || ""])));
      })
      .catch((err) => setError(err.message));
  }
  useEffect(load, []);

  async function save() {
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE_URL}/profile`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft) });
      if (!res.ok) throw new Error(await readError(res, "Couldn't save profile"));
      toastSuccess("Profile updated.");
      setEditing(false);
      load();
    } catch (err) {
      toastError(err.message);
    } finally {
      setSaving(false);
    }
  }

  const ts = (s) => (s ? new Date(s * 1000).toLocaleString() : "not in token");

  return (
    <div className={merchant ? "" : "p-4 sm:p-6"}>
      <h1 className="font-display text-2xl font-semibold text-ink">{merchant ? "Merchant Profile" : "Your Profile"}</h1>
      <p className="mb-5 mt-1 font-body text-sm text-ink-soft">
        {merchant ? "The merchant account behind this dashboard." : "Your account and the contact details used on your orders and invoices."}
      </p>

      {error && <ErrorBox message={error} />}
      {!data && !error && <SkeletonRows rows={5} />}

      {data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card title="Account">
            <div className="mb-3 flex items-center gap-3">
              {data.avatar_url ? (
                <img src={data.avatar_url} alt="" className="h-14 w-14 rounded-full border border-putty-dark object-cover" />
              ) : (
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-putty-light font-display text-xl text-ink-soft">
                  {(data.name || data.email || "?")[0].toUpperCase()}
                </div>
              )}
              <div>
                <p className="font-display text-base font-semibold text-ink">{data.name || "—"}</p>
                <p className="font-body text-sm text-ink-soft">{data.email}</p>
              </div>
            </div>
            <div className="divide-y divide-putty">
              <Field label="Account type"><Badge tone={data.role === "MERCHANT_ADMIN" ? "info" : "neutral"}>{data.role}</Badge></Field>
              <Field label="Authentication provider">{data.provider || "not in token"}</Field>
              <Field label="Session issued">{ts(data.session_issued_at)}</Field>
              <Field label="Session expires">{ts(data.session_expires_at)}</Field>
              {merchant && <Field label="Store">Priya's Shop <span className="text-ink-soft/50">(single-store deployment)</span></Field>}
            </div>
            <p className="mt-2 font-body text-[11px] text-ink-soft/50">
              Identity fields are read from the verified sign-in token; account creation date isn't carried in the token, so it isn't shown.
            </p>
            <div className="mt-4 flex gap-2">
              {!merchant && <Link to="/orders" className="rounded-sm border border-clay px-3 py-1.5 font-body text-xs font-medium text-clay hover:bg-putty-light">Your orders</Link>}
              <button onClick={signOut} className="rounded-sm border border-putty-dark px-3 py-1.5 font-body text-xs font-medium text-ink-soft hover:bg-putty-light">
                Logout
              </button>
            </div>
          </Card>

          <Card
            title={merchant ? "Contact details" : "Contact & shipping"}
            action={
              !editing && (
                <button onClick={() => setEditing(true)} className="font-body text-xs text-clay hover:underline">Edit Profile</button>
              )
            }
          >
            {editing ? (
              <div className="space-y-2">
                {EDITABLE.map(([k, label, type]) => (
                  <label key={k} className="block">
                    <span className="font-body text-[11px] text-ink-soft">{label}</span>
                    <input
                      type={type}
                      value={draft[k]}
                      onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))}
                      className="mt-0.5 w-full rounded-sm border border-putty-dark bg-ivory px-2 py-1.5 font-body text-sm text-ink focus:border-clay focus:outline-none"
                    />
                  </label>
                ))}
                <div className="flex justify-end gap-2 pt-1">
                  <button onClick={() => setEditing(false)} disabled={saving} className="rounded-sm border border-putty-dark px-3 py-1.5 font-body text-xs text-ink-soft hover:bg-putty-light">Cancel</button>
                  <button onClick={save} disabled={saving} className="rounded-sm bg-clay px-3 py-1.5 font-body text-xs font-semibold text-ivory hover:bg-clay-dark disabled:opacity-60">{saving ? "Saving…" : "Save"}</button>
                </div>
              </div>
            ) : (
              <div className="divide-y divide-putty">
                {EDITABLE.map(([k, label]) => (
                  <Field key={k} label={label}>{data.profile[k] || <span className="text-ink-soft/40">not set</span>}</Field>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
