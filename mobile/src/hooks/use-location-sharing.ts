import * as Location from 'expo-location';
import { useEffect, useState } from 'react';

import { ApiError } from '@/lib/api';
import { sendLocation } from '@/services/owner-deliveries';
import type { LocationFix } from '@/types/tracking';

const MIN_SEND_INTERVAL_MS = 10_000; // the server accepts one update every 5 s

function toFix(position: Location.LocationObject): LocationFix {
  const { coords } = position;
  return {
    latitude: coords.latitude,
    longitude: coords.longitude,
    accuracy_m: coords.accuracy ?? null,
    heading: coords.heading !== null && coords.heading >= 0 ? coords.heading % 360 : null,
    speed_mps: coords.speed !== null && coords.speed >= 0 ? coords.speed : null,
    recorded_at: new Date(position.timestamp).toISOString(),
  };
}

/**
 * Shares the phone's position for a delivery while `sharing` is on and this screen is open
 * (foreground only; background sharing needs a development build). Stops by itself when the
 * server says the delivery is no longer on its way.
 */
export function useLocationSharing(deliveryId: string) {
  const [sharing, setSharing] = useState(false);
  const [lastSentAt, setLastSentAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ended, setEnded] = useState(false);

  useEffect(() => {
    if (!sharing) return;
    let subscription: Location.LocationSubscription | null = null;
    let cancelled = false;
    let lastSent = 0;

    (async () => {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (cancelled) return;
      if (permission.status !== 'granted') {
        setError('Allow location access so the renter can see the car arrive.');
        setSharing(false);
        return;
      }
      subscription = await Location.watchPositionAsync(
        { accuracy: Location.Accuracy.High, timeInterval: 15_000, distanceInterval: 20 },
        async (position) => {
          if (Date.now() - lastSent < MIN_SEND_INTERVAL_MS) return;
          lastSent = Date.now();
          try {
            await sendLocation(deliveryId, toFix(position));
            setLastSentAt(Date.now());
            setError(null);
          } catch (e) {
            if (e instanceof ApiError && e.status === 409) {
              setEnded(true);
              setSharing(false);
            } else if (!(e instanceof ApiError && e.status === 429)) {
              setError(e instanceof ApiError ? e.message : 'Could not send your position.');
            }
          }
        },
      );
      if (cancelled) subscription.remove();
    })();

    return () => {
      cancelled = true;
      subscription?.remove();
    };
  }, [sharing, deliveryId]);

  return {
    sharing,
    lastSentAt,
    error,
    ended,
    start: () => {
      setError(null);
      setSharing(true);
    },
    stop: () => setSharing(false),
  };
}
