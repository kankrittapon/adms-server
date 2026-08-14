import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken } from "../api/client";

/** Shape of the MQTT payload the Collector publishes on attendance/events. */
export interface AttendanceEvent {
  user_id: string;
  device_ip: string;
  scan_time: string;
  punch_type?: string;
  status?: string;
  event_type: string;
}

export type StreamStatus = "connecting" | "connected" | "disconnected";

const RECONNECT_DELAY_MS = 3000;

/**
 * Subscribes to GET /api/v1/stream/attendance (Server-Sent Events).
 *
 * Uses fetch + ReadableStream so the Bearer token stays in the Authorization
 * header (EventSource cannot set headers, and tokens in query strings are
 * avoided for security hygiene). Auto-reconnects with a fixed delay; exposes
 * connection status + the most recent event.
 */
export function useAttendanceStream(): {
  status: StreamStatus;
  lastEvent: AttendanceEvent | null;
} {
  const [status, setStatus] = useState<StreamStatus>("disconnected");
  const [lastEvent, setLastEvent] = useState<AttendanceEvent | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const connect = useCallback(() => {
    const token = getToken();
    if (!token) {
      setStatus("disconnected");
      return;
    }
    const controller = new AbortController();
    abortRef.current = controller;
    let closed = false;

    const run = async () => {
      try {
        const res = await fetch(`${api.baseUrl}/api/v1/stream/attendance`, {
          headers: { Accept: "text/event-stream", Authorization: `Bearer ${token}` },
          signal: controller.signal,
        });
        if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
        setStatus("connected");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let idx: number;
          while ((idx = buffer.indexOf("\n\n")) !== -1) {
            const block = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            const dataLine = block
              .split("\n")
              .find((l) => l.startsWith("data: "));
            if (dataLine) {
              try {
                setLastEvent(JSON.parse(dataLine.slice(6)) as AttendanceEvent);
              } catch {
                // malformed event — ignore, keep the stream alive
              }
            }
          }
        }
      } catch {
        // aborted or network error — fall through to reconnect
      } finally {
        if (!closed && !controller.signal.aborted) {
          setStatus("disconnected");
          // reconnect after a delay (unless the component unmounted meanwhile)
          setTimeout(() => {
            if (!closed) connect();
          }, RECONNECT_DELAY_MS);
        }
      }
    };

    // eslint-disable-next-line @typescript-eslint/no-floating-promises
    run();

    return () => {
      closed = true;
      controller.abort();
    };
  }, []);

  useEffect(() => {
    const cleanup = connect();
    return () => {
      cleanup?.();
      abortRef.current?.abort();
    };
  }, [connect]);

  return { status, lastEvent };
}
