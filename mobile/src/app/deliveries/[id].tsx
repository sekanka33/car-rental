import { Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { SignInPrompt } from '@/components/sign-in-prompt';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { useLocationSharing } from '@/hooks/use-location-sharing';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/dates';
import { type AssignedDelivery, getMyDelivery, startDelivery } from '@/services/owner-deliveries';

function useSecondsSince(time: number | null): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(timer);
  }, []);
  return time === null ? null : Math.max(0, Math.round((now - time) / 1000));
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View className="flex-row justify-between py-1.5">
      <Text className="text-base text-ink-muted">{label}</Text>
      <Text className="ml-4 flex-1 text-right text-base text-ink">{value}</Text>
    </View>
  );
}

function Sharing({ deliveryId, onEnded }: { deliveryId: string; onEnded: () => void }) {
  const { sharing, lastSentAt, error, ended, start, stop } = useLocationSharing(deliveryId);
  const seconds = useSecondsSince(lastSentAt);
  useEffect(() => {
    if (ended) onEnded();
  }, [ended, onEnded]);
  return (
    <View className="mt-6">
      <Text className="mb-2 text-sm text-ink-muted">
        Keep this screen open while you drive. The renter sees your position only while the car is on its way.
      </Text>
      {error ? <Notice tone="danger" message={error} /> : null}
      {sharing ? (
        <>
          <Notice tone="success" message={seconds === null ? 'Sharing your location…' : `Location shared ${seconds} s ago`} />
          <Button label="Stop sharing" variant="secondary" onPress={stop} />
        </>
      ) : (
        <Button label="Share my location" onPress={start} />
      )}
    </View>
  );
}

function DeliveryDetails({ delivery, onChanged }: { delivery: AssignedDelivery; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const setOff = async () => {
    setBusy(true);
    setError(null);
    try {
      await startDelivery(delivery.id);
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not update the delivery.');
      setBusy(false);
    }
  };
  return (
    <Screen scroll>
      <Stack.Screen options={{ title: `Delivery ${delivery.booking_reference}` }} />
      <Text className="text-2xl font-bold text-ink">
        {delivery.vehicle.make} {delivery.vehicle.model}
      </Text>
      <Text className="text-base text-ink-muted">{delivery.registration_number}</Text>
      <View className="mt-4">
        <Row label="Renter" value={delivery.renter.full_name} />
        {delivery.renter.phone_number ? <Row label="Phone" value={delivery.renter.phone_number} /> : null}
        <Row label="Deliver to" value={delivery.dropoff_address} />
        <Row label="When" value={delivery.scheduled_for ? formatDateTime(delivery.scheduled_for) : 'Not confirmed yet'} />
      </View>
      {error ? (
        <View className="mt-4">
          <Notice tone="danger" message={error} />
        </View>
      ) : null}
      {delivery.status === 'SCHEDULED' ? <Button label="Set off now" loading={busy} onPress={setOff} className="mt-6" /> : null}
      {delivery.status === 'EN_ROUTE' ? <Sharing deliveryId={delivery.id} onEnded={onChanged} /> : null}
      {delivery.status === 'PENDING_SCHEDULE' ? (
        <Text className="mt-6 text-sm text-ink-muted">Confirm the delivery time first (owner screens arrive in a later release).</Text>
      ) : null}
    </Screen>
  );
}

export default function OwnerDeliveryScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { state } = useAuth();
  const load = useCallback(() => getMyDelivery(id), [id]);
  const delivery = useAsync(load);
  if (state.status === 'signedOut') return <SignInPrompt message="Log in to see this delivery." />;
  if (delivery.status === 'loading' || state.status === 'loading') return <LoadingState />;
  if (delivery.status === 'error') {
    if (delivery.error instanceof ApiError && delivery.error.isNotFound) {
      return <EmptyState title="Delivery not found" message="It may be assigned to someone else." />;
    }
    return <ErrorState message={delivery.error.message} onAction={delivery.reload} />;
  }
  return <DeliveryDetails delivery={delivery.data} onChanged={delivery.reload} />;
}
