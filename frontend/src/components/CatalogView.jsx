import { useEffect, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

export default function CatalogView() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusMessage, setStatusMessage] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/catalog`)
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load catalog");
        return res.json();
      })
      .then(setProducts)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleBuy(product) {
    setError(null);
    setStatusMessage(null);

    try {
      const res = await fetch(`${API_BASE_URL}/order/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_id: product.id, quantity: 1 }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Failed to create order");
      }

      const { razorpay_order_id, amount, key_id } = await res.json();

      const razorpay = new window.Razorpay({
        key: key_id,
        amount,
        currency: "INR",
        order_id: razorpay_order_id,
        name: product.name,
        description: product.description || "",
        handler: () => setStatusMessage("Payment initiated"),
        modal: {
          ondismiss: () => setStatusMessage("Payment cancelled"),
        },
      });

      razorpay.open();
    } catch (err) {
      setError(err.message);
    }
  }

  if (loading) return <p>Loading catalog...</p>;
  if (error) return <p className="text-red-600">{error}</p>;

  return (
    <div>
      {statusMessage && <p className="mb-4 font-medium">{statusMessage}</p>}
      <ul className="space-y-3">
        {products.map((product) => (
          <li
            key={product.id}
            className="flex items-center justify-between border rounded p-4 bg-white"
          >
            <div>
              <p className="font-medium">{product.name}</p>
              <p className="text-sm text-gray-600">
                ₹{(product.price / 100).toFixed(2)} · stock: {product.stock}
              </p>
              {product.description && (
                <p className="text-sm text-gray-500">{product.description}</p>
              )}
            </div>
            <button
              onClick={() => handleBuy(product)}
              disabled={product.stock < 1}
              className="px-4 py-2 bg-blue-600 text-white rounded disabled:bg-gray-300"
            >
              Buy
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
