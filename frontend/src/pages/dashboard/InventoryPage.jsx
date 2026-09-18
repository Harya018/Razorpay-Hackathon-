import { useEffect, useState } from "react";

import Card from "../../components/Card.jsx";
import StockBadge from "../../components/StockBadge.jsx";
import { Badge, ConfirmModal, ErrorBox, SkeletonRows, fmtDate, readError, rupees } from "../../components/ui.jsx";
import { toastError, toastSuccess } from "../../lib/toast.js";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Every action here is a real PATCH/DELETE /product/{id} — admin-gated
// server-side (require_merchant_admin), validated by the backend's
// ProductUpdate schema, and written to the audit chain as
// product_updated / product_deleted. Delete is a soft delete (is_active)
// so existing orders keep resolving; the row stays visible here, flagged.
function EditModal({ product, onClose, onSaved }) {
  const [draft, setDraft] = useState({
    name: product.name,
    price: (product.price / 100).toFixed(2),
    stock: String(product.stock),
    category: product.category || "",
    description: product.description || "",
    negotiable: product.negotiable,
  });
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    try {
      const body = {
        name: draft.name.trim(),
        price: Math.round(Number(draft.price) * 100),
        stock: Number(draft.stock),
        category: draft.category.trim() || null,
        description: draft.description.trim() || null,
        negotiable: draft.negotiable,
      };
      const res = await fetch(`${API_BASE_URL}/product/${product.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) throw new Error(await readError(res, "Couldn't update product"));
      toastSuccess(`Updated ${body.name}.`);
      onSaved();
    } catch (err) {
      toastError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const input = "mt-0.5 w-full rounded-sm border border-putty-dark bg-ivory px-2 py-1.5 font-body text-sm text-ink focus:border-clay focus:outline-none";
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-ink/40 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl border border-putty-dark bg-white p-5 shadow-lg" onClick={(e) => e.stopPropagation()}>
        <p className="font-display text-lg font-semibold text-ink">Edit product #{product.id}</p>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="sm:col-span-2"><span className="font-body text-[11px] text-ink-soft">Name</span><input className={input} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></label>
          <label><span className="font-body text-[11px] text-ink-soft">Price (₹)</span><input className={input} type="number" min="0.01" step="0.01" value={draft.price} onChange={(e) => setDraft({ ...draft, price: e.target.value })} /></label>
          <label><span className="font-body text-[11px] text-ink-soft">Stock</span><input className={input} type="number" min="0" step="1" value={draft.stock} onChange={(e) => setDraft({ ...draft, stock: e.target.value })} /></label>
          <label><span className="font-body text-[11px] text-ink-soft">Category</span><input className={input} value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} /></label>
          <label className="flex items-center gap-2 pt-4 font-body text-sm text-ink"><input type="checkbox" checked={draft.negotiable} onChange={(e) => setDraft({ ...draft, negotiable: e.target.checked })} /> Negotiable</label>
          <label className="sm:col-span-2"><span className="font-body text-[11px] text-ink-soft">Description</span><textarea className={input} rows={2} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></label>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} disabled={busy} className="rounded-lg border border-putty-dark px-4 py-2 font-body text-sm text-ink-soft hover:bg-putty-light">Cancel</button>
          <button onClick={save} disabled={busy} className="rounded-lg bg-clay px-4 py-2 font-body text-sm font-semibold text-ivory hover:bg-clay-dark disabled:opacity-60">{busy ? "Saving…" : "Save changes"}</button>
        </div>
      </div>
    </div>
  );
}

function StockModal({ product, onClose, onSaved }) {
  const [value, setValue] = useState(String(product.stock));
  const [busy, setBusy] = useState(false);
  async function save() {
    const stock = Number(value);
    if (!Number.isInteger(stock) || stock < 0) return toastError("Stock must be a whole number ≥ 0.");
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE_URL}/product/${product.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stock }) });
      if (!res.ok) throw new Error(await readError(res, "Couldn't update stock"));
      toastSuccess(`${product.name}: stock set to ${stock}.`);
      onSaved();
    } catch (err) {
      toastError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <ConfirmModal
      open
      title="Update stock"
      confirmLabel="Save stock"
      busy={busy}
      onCancel={onClose}
      onConfirm={save}
      body={
        <label className="block">
          <span className="font-body text-xs text-ink-soft">{product.name} — current stock {product.stock}</span>
          <input type="number" min="0" step="1" value={value} onChange={(e) => setValue(e.target.value)} className="mt-1 w-32 rounded-sm border border-putty-dark bg-ivory px-2 py-1.5 font-body text-sm text-ink focus:border-clay focus:outline-none" />
        </label>
      }
    />
  );
}

export default function InventoryPage() {
  const [products, setProducts] = useState(null);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null);
  const [stocking, setStocking] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [busy, setBusy] = useState(false);

  function load() {
    fetch(`${API_BASE_URL}/catalog?include_inactive=1`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await readError(res, "Couldn't load inventory"));
        return res.json();
      })
      .then(setProducts)
      .catch((err) => setError(err.message));
  }
  useEffect(load, []);

  async function confirmDelete() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE_URL}/product/${deleting.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await readError(res, "Couldn't delete product"));
      toastSuccess(`Deleted ${deleting.name} (hidden from the storefront; existing orders keep their record).`);
      setDeleting(null);
      load();
    } catch (err) {
      toastError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function restore(p) {
    const res = await fetch(`${API_BASE_URL}/product/${p.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_active: true }) });
    if (!res.ok) return toastError(await readError(res, "Couldn't restore product"));
    toastSuccess(`Restored ${p.name}.`);
    load();
  }

  return (
    <div>
      <h1 className="font-display text-2xl font-semibold text-ink">Inventory</h1>
      <p className="mb-5 mt-1 font-body text-sm text-ink-soft">
        Stock is the backend's source of truth — it is deducted atomically when a payment is verified, never by the frontend.
        Low stock = 5 or fewer (StockBadge.jsx).
      </p>
      {error && <ErrorBox message={error} />}
      <Card>
        {!products && !error && <SkeletonRows rows={6} />}
        {products && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] font-body text-sm">
              <thead>
                <tr className="border-b border-putty-dark text-left text-[11px] font-semibold uppercase tracking-wide text-ink-soft/70">
                  <th className="py-2 pr-2">ID</th><th className="py-2 pr-2">Product</th><th className="py-2 pr-2">Category</th><th className="py-2 pr-2">Price</th>
                  <th className="py-2 pr-2">Stock</th><th className="py-2 pr-2">Status</th><th className="py-2 pr-2">Updated</th><th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr key={p.id} className={`border-b border-putty-dark/60 last:border-b-0 ${p.is_active ? "" : "opacity-60"}`}>
                    <td className="py-2 pr-2 font-mono text-xs text-ink-soft">#{p.id}</td>
                    <td className="max-w-[240px] truncate py-2 pr-2 font-medium text-ink">{p.name}</td>
                    <td className="py-2 pr-2 capitalize text-ink-soft">{p.category || "—"}</td>
                    <td className="py-2 pr-2 text-ink">{rupees(p.price)}</td>
                    <td className="py-2 pr-2 text-ink">{p.stock}</td>
                    <td className="py-2 pr-2">
                      <div className="flex flex-col gap-1">
                        <StockBadge stock={p.stock} showCount={false} />
                        {!p.is_active && <Badge tone="error">Deleted</Badge>}
                        {p.is_active && !p.negotiable && <Badge tone="neutral">Fixed price</Badge>}
                      </div>
                    </td>
                    <td className="py-2 pr-2 text-xs text-ink-soft/70">{fmtDate(p.updated_at || p.created_at)}</td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-1.5">
                        {p.is_active ? (
                          <>
                            <button onClick={() => setStocking(p)} className="rounded-sm bg-clay px-2.5 py-1 font-body text-xs font-semibold text-ivory hover:bg-clay-dark">Update Stock</button>
                            <button onClick={() => setEditing(p)} className="rounded-sm border border-putty-dark px-2.5 py-1 font-body text-xs text-ink-soft hover:bg-putty-light">Edit</button>
                            <button onClick={() => setDeleting(p)} className="rounded-sm border border-rose-300 px-2.5 py-1 font-body text-xs text-rose-700 hover:bg-rose-50">Delete</button>
                          </>
                        ) : (
                          <button onClick={() => restore(p)} className="rounded-sm border border-putty-dark px-2.5 py-1 font-body text-xs text-ink-soft hover:bg-putty-light">Restore</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {editing && <EditModal product={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />}
      {stocking && <StockModal product={stocking} onClose={() => setStocking(null)} onSaved={() => { setStocking(null); load(); }} />}
      <ConfirmModal
        open={Boolean(deleting)}
        title="Delete Product?"
        danger
        confirmLabel="Delete Product"
        busy={busy}
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
        body={
          deleting && (
            <>
              <p className="font-medium text-ink">{deleting.name} <span className="font-mono text-xs text-ink-soft/60">#{deleting.id}</span></p>
              <p className="mt-1">It will be removed from the storefront immediately. Existing orders and audit records that reference it are preserved, and you can restore it from this page.</p>
            </>
          )
        }
      />
    </div>
  );
}
