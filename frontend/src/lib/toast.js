// Minimal toast bus — no new dependency, same "dispatch a window event,
// components listen" pattern cart.js already uses for "cart:updated".
// ToastHost.jsx is the one listener that actually renders these; any
// component can call toast(...) without importing React state plumbing.

let counter = 0;

// kind: "info" (default) | "success" | "error"
export function toast(message, kind = "info") {
  if (!message) return;
  const detail = { id: `t${Date.now()}_${counter++}`, message, kind };
  window.dispatchEvent(new CustomEvent("app:toast", { detail }));
}

export const toastSuccess = (message) => toast(message, "success");
export const toastError = (message) => toast(message, "error");
