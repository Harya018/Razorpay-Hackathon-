import { useCallback, useEffect, useState } from "react";

import { readError } from "../components/ui.jsx";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Loads one order's detail from either the customer route (/orders/:id,
// ownership-checked server-side) or the merchant route
// (/dashboard/orders/:id, admin-gated). Same response shape; the merchant
// version additionally carries raw event payloads and customer contact.
export default function useOrderDetail(orderId, { merchant = false } = {}) {
  const [state, setState] = useState({ loading: true, data: null, error: null });

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true }));
    fetch(`${API_BASE_URL}${merchant ? "/dashboard" : ""}/orders/${orderId}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await readError(res, "Couldn't load this order"));
        return res.json();
      })
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((err) => setState({ loading: false, data: null, error: err.message }));
  }, [orderId, merchant]);

  useEffect(load, [load]);
  return { ...state, reload: load };
}
