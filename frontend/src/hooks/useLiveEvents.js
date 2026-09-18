import { useCallback, useState } from "react";

import useDashboardStream from "./useDashboardStream.js";

const MAX_EVENTS = 30;

// Thin layer over useDashboardStream that also keeps a bounded buffer of
// the most recent events — so a page can own its ONE SSE connection (per
// useDashboardStream's own one-connection-per-page rule) and hand the
// buffer to a purely presentational LiveEventTicker, while still reacting
// to individual events itself via onEvent (e.g. bumping a refreshKey).
export default function useLiveEvents(onEvent) {
  const [events, setEvents] = useState([]);

  const handle = useCallback(
    (data) => {
      setEvents((prev) => [data, ...prev].slice(0, MAX_EVENTS));
      onEvent?.(data);
    },
    [onEvent]
  );

  const connected = useDashboardStream(handle);
  return { events, connected };
}
