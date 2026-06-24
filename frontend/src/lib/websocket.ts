import type { LiveEvent } from "@/types";

const WS = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost";

export interface WSHandle {
  close: () => void;
}

function makeWS<T>(
  url: string,
  onEvent: (e: T) => void,
  filterPing = true
): WSHandle {
  let current: WebSocket | null = null;
  let closed = false;

  function connect() {
    if (closed) return;
    const ws = new WebSocket(url);
    current = ws;
    ws.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data);
        if (filterPing && parsed.type === "ping") return;
        onEvent(parsed as T);
      } catch { /* ignore malformed */ }
    };
    ws.onclose = () => {
      if (!closed) setTimeout(connect, 3000);
    };
  }

  connect();
  return { close: () => { closed = true; current?.close(); } };
}

export function connectAttendanceWS(
  tenantId: string,
  token: string,
  onEvent: (e: LiveEvent) => void
): WSHandle {
  return makeWS<LiveEvent>(`${WS}/ws/attendance/${tenantId}?token=${token}`, onEvent);
}

export function connectAlertsWS(
  tenantId: string,
  token: string,
  onAlert: (a: Record<string, unknown>) => void
): WSHandle {
  return makeWS<Record<string, unknown>>(`${WS}/ws/alerts/${tenantId}?token=${token}`, onAlert);
}
