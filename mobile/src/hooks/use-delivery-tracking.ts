import { useEffect, useState } from 'react';

import { getAccessToken, websocketUrl } from '@/lib/api';
import type { TrackingState } from '@/types/tracking';

export type Connection = 'connecting' | 'live' | 'reconnecting' | 'ended' | 'unavailable';

// Close codes sent by the server (backend app/api/routes/live.py).
const ENDED = 4000;
const UNAUTHENTICATED = 4401;
const FORBIDDEN = 4403;
const MAX_BACKOFF_MS = 30_000;

/**
 * Follows a delivery over the live WebSocket: authenticates with the access token in the
 * first message, refreshes the session once when the server says the token expired, and
 * reconnects with backoff after network drops. Stops for good when tracking ends.
 */
export function useDeliveryTracking(deliveryId: string, enabled = true) {
  const [state, setState] = useState<TrackingState | null>(null);
  const [connection, setConnection] = useState<Connection>('connecting');

  useEffect(() => {
    if (!enabled) return;
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let stopped = false;
    let attempt = 0;
    let renewed = false;

    const connect = async (renew: boolean) => {
      const token = await getAccessToken({ renew });
      if (stopped) return;
      if (!token) {
        setConnection('unavailable');
        return;
      }
      socket = new WebSocket(websocketUrl(`/api/v1/deliveries/${encodeURIComponent(deliveryId)}/live`));
      socket.onopen = () => socket?.send(JSON.stringify({ type: 'auth', token }));
      socket.onmessage = (event) => {
        let message: { type?: string } & Partial<TrackingState>;
        try {
          message = JSON.parse(String(event.data));
        } catch {
          return;
        }
        if (message.type === 'snapshot' || message.type === 'status' || message.type === 'location') {
          attempt = 0;
          renewed = false;
          setConnection('live');
          setState(message as TrackingState);
        }
      };
      socket.onclose = (event) => {
        socket = null;
        if (stopped) return;
        if (event.code === ENDED) return setConnection('ended');
        if (event.code === FORBIDDEN) return setConnection('unavailable');
        if (event.code === UNAUTHENTICATED) {
          if (renewed) return setConnection('unavailable'); // refreshing did not help
          renewed = true;
          setConnection('reconnecting');
          void connect(true);
          return;
        }
        setConnection('reconnecting');
        const delay = Math.min(1000 * 2 ** attempt, MAX_BACKOFF_MS);
        attempt += 1;
        timer = setTimeout(() => void connect(false), delay);
      };
    };

    void connect(false);
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }, [deliveryId, enabled]);

  return { state, connection };
}
