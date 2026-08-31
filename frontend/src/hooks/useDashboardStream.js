import { useEffect, useRef, useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

// Opens the merchant dashboard's shared SSE endpoint and calls onEvent
// for every parsed message — each row is already tagged with its
// channel by the backend (/dashboard/stream). One connection per page
// that uses this hook (the three dashboard pages are mutually exclusive
// routes, so there's never more than one open at a time); each page
// decides for itself which events matter to it and owns its own "Live"
// badge from the returned `connected` flag.
export default function useDashboardStream(onEvent) {
  const [connected, setConnected] = useState(false);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    const source = new EventSource(`${API_BASE_URL}/dashboard/stream`);

    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false); // EventSource auto-reconnects on its own

    source.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      onEventRef.current?.(data);
    };

    return () => source.close();
  }, []);

  return connected;
}
