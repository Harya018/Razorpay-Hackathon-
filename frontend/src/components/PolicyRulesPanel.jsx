import { useEffect, useState } from "react";

import Card from "./Card.jsx";
import { toastError, toastSuccess } from "../lib/toast.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Lets a merchant adjust the Policy Gate's actual discount limits from
// the dashboard — not a mock settings screen. Every value shown/edited
// here round-trips through the real backend -> policy-gate chain
// (backend/app/routes/admin_rules.py -> policy-gate/app/routes/rules.py
// -> app/rules/merchant_rules.py, which is what evaluate.py reads on
// every real negotiation). The LLM never sees or touches these numbers —
// this panel changes the deterministic floor the Policy Gate enforces,
// nothing about how the seller/buyer agents negotiate.
export default function PolicyRulesPanel() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [defaultDraft, setDefaultDraft] = useState({ max_discount_pct: "", max_attempts: "" });
  const [savingDefault, setSavingDefault] = useState(false);
  const [productDrafts, setProductDrafts] = useState({}); // product_id -> { max_discount_pct, floor_price }
  const [savingProductId, setSavingProductId] = useState(null);

  function load() {
    fetch(`${API_BASE_URL}/admin/policy-rules`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || "Failed to load policy rules");
        }
        return res.json();
      })
      .then((d) => {
        setData(d);
        setDefaultDraft({ max_discount_pct: String(d.default.max_discount_pct), max_attempts: String(d.default.max_attempts) });
        setError(null);
      })
      .catch((err) => setError(err.message));
  }

  useEffect(load, []);

  function draftFor(product) {
    const override = data.products.find((p) => p.product_id === product.product_id);
    return productDrafts[product.product_id] ?? {
      max_discount_pct: override ? String(override.max_discount_pct) : "",
      floor_price: override?.floor_price != null ? String(override.floor_price / 100) : "",
    };
  }

  function setDraft(productId, patch) {
    setProductDrafts((prev) => ({ ...prev, [productId]: { ...draftForId(productId), ...patch } }));
  }
  function draftForId(productId) {
    const product = data.catalog.find((p) => p.product_id === productId);
    return draftFor(product);
  }

  async function saveDefault() {
    setSavingDefault(true);
    try {
      const res = await fetch(`${API_BASE_URL}/admin/policy-rules/default`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          max_discount_pct: Number(defaultDraft.max_discount_pct),
          max_attempts: Number(defaultDraft.max_attempts),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to update default rule");
      }
      toastSuccess("Default policy updated.");
      load();
    } catch (err) {
      toastError(err.message);
    } finally {
      setSavingDefault(false);
    }
  }

  async function saveProductRule(productId) {
    const draft = draftForId(productId);
    setSavingProductId(productId);
    try {
      const res = await fetch(`${API_BASE_URL}/admin/policy-rules/product/${productId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          max_discount_pct: Number(draft.max_discount_pct),
          floor_price: draft.floor_price === "" ? null : Math.round(Number(draft.floor_price) * 100),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to update product rule");
      }
      toastSuccess("Product rule updated.");
      load();
    } catch (err) {
      toastError(err.message);
    } finally {
      setSavingProductId(null);
    }
  }

  async function revertProductRule(productId) {
    setSavingProductId(productId);
    try {
      const res = await fetch(`${API_BASE_URL}/admin/policy-rules/product/${productId}`, { method: "DELETE" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to revert product rule");
      }
      toastSuccess("Reverted to the default policy.");
      setProductDrafts((prev) => {
        const next = { ...prev };
        delete next[productId];
        return next;
      });
      load();
    } catch (err) {
      toastError(err.message);
    } finally {
      setSavingProductId(null);
    }
  }

  if (error) {
    return (
      <Card title="Policy Gate Rules">
        <p className="font-body text-sm text-rose-700">{error}</p>
        <p className="mt-1 font-body text-xs text-ink-soft/60">
          This needs GATE_SECRET configured identically in both backend/.env and policy-gate/.env.
        </p>
      </Card>
    );
  }
  if (!data) return <Card title="Policy Gate Rules"><p className="font-body text-sm text-ink-soft">Loading...</p></Card>;

  return (
    <Card
      title="Policy Gate Rules"
      note="Adjusts the deterministic limits evaluate.py enforces on every negotiation — never the LLM's behavior."
    >
      <div className="rounded-lg border border-putty-dark bg-ivory-deep/40 p-3">
        <p className="font-body text-xs font-semibold uppercase tracking-wide text-ink-soft">Default policy</p>
        <p className="mt-0.5 font-body text-[11px] text-ink-soft/60">Applies to every product without its own override below.</p>
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="font-body text-[11px] text-ink-soft">Max discount %</span>
            <input
              type="number"
              min="0"
              max="100"
              step="0.5"
              value={defaultDraft.max_discount_pct}
              onChange={(e) => setDefaultDraft((d) => ({ ...d, max_discount_pct: e.target.value }))}
              className="w-24 rounded-sm border border-putty-dark bg-ivory px-2 py-1 font-body text-sm text-ink focus:border-clay focus:outline-none"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-body text-[11px] text-ink-soft">Max negotiation attempts</span>
            <input
              type="number"
              min="1"
              max="20"
              value={defaultDraft.max_attempts}
              onChange={(e) => setDefaultDraft((d) => ({ ...d, max_attempts: e.target.value }))}
              className="w-24 rounded-sm border border-putty-dark bg-ivory px-2 py-1 font-body text-sm text-ink focus:border-clay focus:outline-none"
            />
          </label>
          <button
            onClick={saveDefault}
            disabled={savingDefault}
            className="rounded-sm bg-clay px-4 py-1.5 font-body text-sm font-semibold text-ivory shadow-sm transition-colors hover:bg-clay-dark disabled:bg-putty"
          >
            {savingDefault ? "Saving..." : "Save default"}
          </button>
        </div>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] font-body text-sm">
          <thead>
            <tr className="border-b border-putty-dark text-left text-[11px] font-semibold uppercase tracking-wide text-ink-soft/70">
              <th className="py-2 pr-2">Product</th>
              <th className="py-2 pr-2">Catalog price</th>
              <th className="py-2 pr-2">Max discount %</th>
              <th className="py-2 pr-2">Floor price (₹, optional)</th>
              <th className="py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.catalog.map((product) => {
              const draft = draftFor(product);
              const saving = savingProductId === product.product_id;
              return (
                <tr key={product.product_id} className="border-b border-putty-dark/60 last:border-b-0">
                  <td className="max-w-[220px] truncate py-2 pr-2 text-ink">
                    {product.name} <span className="text-ink-soft/50">#{product.product_id}</span>
                  </td>
                  <td className="py-2 pr-2 text-ink-soft">₹{(product.price / 100).toFixed(2)}</td>
                  <td className="py-2 pr-2">
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="0.5"
                      placeholder={String(data.default.max_discount_pct)}
                      value={draft.max_discount_pct}
                      onChange={(e) => setDraft(product.product_id, { max_discount_pct: e.target.value })}
                      className="w-20 rounded-sm border border-putty-dark bg-ivory px-2 py-1 font-body text-sm text-ink focus:border-clay focus:outline-none"
                    />
                  </td>
                  <td className="py-2 pr-2">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="none"
                      value={draft.floor_price}
                      onChange={(e) => setDraft(product.product_id, { floor_price: e.target.value })}
                      className="w-24 rounded-sm border border-putty-dark bg-ivory px-2 py-1 font-body text-sm text-ink focus:border-clay focus:outline-none"
                    />
                  </td>
                  <td className="py-2">
                    <div className="flex gap-2">
                      <button
                        onClick={() => saveProductRule(product.product_id)}
                        disabled={saving || !draft.max_discount_pct}
                        className="rounded-sm bg-clay px-3 py-1 font-body text-xs font-semibold text-ivory shadow-sm hover:bg-clay-dark disabled:bg-putty"
                      >
                        {saving ? "..." : "Save"}
                      </button>
                      {product.has_override && (
                        <button
                          onClick={() => revertProductRule(product.product_id)}
                          disabled={saving}
                          className="rounded-sm border border-putty-dark px-3 py-1 font-body text-xs font-medium text-ink-soft hover:bg-putty-light"
                        >
                          Revert
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
