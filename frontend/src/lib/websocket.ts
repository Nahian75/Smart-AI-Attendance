import type { LiveEvent } from "@/types";

const WS = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost";

export interface WSHandle {
  close: () => void;
}

export function connectAttendanceWS(
  tenantId: string,
  token: string,
  onEvent: (e: LiveEvent) => void
): WSHandle {
  let current: WebSocket | null = null;
  let closed = false;

  function connect() {
    if (closed) return;
    const ws = new WebSocket(`${WS}/ws/attendance/${tenantId}?token=${token}`);
    current = ws;
    ws.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data);
        if (parsed.type === "ping") return;
        onEvent(parsed as LiveEvent);
      } catch { /* ignore malformed */ }
    };
    ws.onclose = () => {
      if (!closed) setTimeout(connect, 3000);
    };
  }

  connect();
  return { close: () => { closed = true; current?.close(); } };
}
