import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { LiveMap } from '@/components/live-map';
import { Notice } from '@/components/ui/notice';
import { useDeliveryTracking } from '@/hooks/use-delivery-tracking';
import type { DeliveryStatus } from '@/types/delivery';

const STALE_AFTER_MS = 60_000;

function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

function ago(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds} s ago`;
  return `${Math.round(seconds / 60)} min ago`;
}

/**
 * Live position and ETA while the car is on its way. Calls `onStatusChange` when the
 * delivery status moves on (e.g. delivered), so the screen can reload.
 */
export function LiveTracking({
  deliveryId,
  status,
  onStatusChange,
}: {
  deliveryId: string;
  status: DeliveryStatus;
  onStatusChange: () => void;
}) {
  const { state, connection } = useDeliveryTracking(deliveryId);
  const now = useNow(5_000);
  const changed = state !== null && state.status !== status;

  useEffect(() => {
    if (changed) onStatusChange();
  }, [changed, onStatusChange]);

  const location = state?.tracking_active ? state.location : null;
  const age = location ? now - new Date(location.received_at).getTime() : null;
  return (
    <View className="mt-3">
      {location ? (
        <>
          <LiveMap location={location} />
          {state?.eta ? (
            <Text className="mt-2 text-base font-semibold text-ink">
              Arriving in about {Math.max(1, Math.round(state.eta.seconds / 60))} min
              {state.eta.distance_m ? ` (${(state.eta.distance_m / 1000).toFixed(1)} km)` : ''}
            </Text>
          ) : null}
          <Text className="mt-1 text-sm text-ink-muted">Updated {ago(age ?? 0)}</Text>
          {age !== null && age > STALE_AFTER_MS ? (
            <View className="mt-2">
              <Notice
                tone="info"
                message="No new position for a while. The driver's signal may be weak; the map updates when it returns."
              />
            </View>
          ) : null}
        </>
      ) : status === 'EN_ROUTE' && connection === 'live' ? (
        <Text className="text-sm text-ink-muted">Waiting for the first position from the driver…</Text>
      ) : null}
      {connection === 'reconnecting' ? <Text className="mt-1 text-sm text-ink-muted">Reconnecting…</Text> : null}
    </View>
  );
}
