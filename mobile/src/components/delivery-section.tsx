import { useState } from 'react';
import { Text, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { TextField } from '@/components/ui/text-field';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/dates';
import { acknowledgeHandover, requestReturn } from '@/services/deliveries';
import type { Delivery, FuelLevel, HandoverRecord } from '@/types/delivery';

const FUEL: Record<FuelLevel, string> = {
  EMPTY: 'Empty',
  QUARTER: '¼ tank',
  HALF: '½ tank',
  THREE_QUARTERS: '¾ tank',
  FULL: 'Full tank',
};

function statusLine(delivery: Delivery): string {
  const who = delivery.delivery_person_first_name ?? 'The owner';
  switch (delivery.status) {
    case 'PENDING_SCHEDULE':
      return `${who} will confirm the delivery time soon.`;
    case 'SCHEDULED':
      return `${who} delivers on ${formatDateTime(delivery.scheduled_for!)}.`;
    case 'EN_ROUTE':
      return `${who} is on the way with your car.`;
    case 'DELIVERED':
      return `Delivered on ${formatDateTime(delivery.delivered_at!)}.`;
    case 'FAILED':
      return 'The delivery could not be completed. Our team will contact you to arrange a new time.';
    case 'CANCELLED':
      return 'The delivery was cancelled.';
  }
}

function Record({ title, record }: { title: string; record: HandoverRecord }) {
  return (
    <View className="mt-3 rounded-xl border border-surface-border p-3">
      <Text className="text-base font-semibold text-ink">{title}</Text>
      <Text className="mt-1 text-sm text-ink-muted">
        {formatDateTime(record.recorded_at)} · {record.odometer_km.toLocaleString('en-ZA')} km · {FUEL[record.fuel_level]}
      </Text>
      {record.condition_notes ? <Text className="mt-1 text-sm text-ink">{record.condition_notes}</Text> : null}
      {record.photos.length > 0 ? (
        <Text className="mt-1 text-sm text-ink-muted">
          {record.photos.length} {record.photos.length === 1 ? 'photo' : 'photos'} recorded
        </Text>
      ) : null}
      {record.renter_notes ? <Text className="mt-1 text-sm text-ink">Your note: {record.renter_notes}</Text> : null}
    </View>
  );
}

/** Delivery progress for the renter, plus the two renter actions: confirm handover, ready to return. */
export function DeliverySection({ delivery, onChanged }: { delivery: Delivery; onChanged: () => void }) {
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const openIssues = delivery.exceptions.filter((e) => e.resolved_at === null);

  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Something went wrong. Please try again.');
      setBusy(false);
    }
  };

  return (
    <>
      <Text className="mb-1 mt-6 text-lg font-semibold text-ink">Delivery</Text>
      <Text className="text-base text-ink">{statusLine(delivery)}</Text>
      {openIssues.map((issue) => (
        <View key={issue.id} className="mt-3">
          <Notice tone="info" message={`Update from the owner: ${issue.notes}`} />
        </View>
      ))}
      {delivery.handover ? <Record title="Handover" record={delivery.handover} /> : null}
      {delivery.return_record ? <Record title="Return" record={delivery.return_record} /> : null}

      {error ? (
        <View className="mt-4">
          <Notice tone="danger" message={error} />
        </View>
      ) : null}
      {delivery.booking_status === 'DELIVERED' ? (
        <View className="mt-4">
          <Text className="mb-3 text-sm text-ink-muted">
            Check the car against the handover record above. Note anything that does not match before you confirm.
          </Text>
          <TextField label="Anything that does not match? (optional)" value={notes} onChangeText={setNotes} maxLength={1000} />
          <Button
            label="I have the car"
            loading={busy}
            onPress={() => act(() => acknowledgeHandover(delivery.booking_id, notes.trim() || undefined))}
          />
        </View>
      ) : null}
      {delivery.booking_status === 'ACTIVE_RENTAL' ? (
        <Button
          label="I'm ready to return the car"
          variant="secondary"
          loading={busy}
          onPress={() => act(() => requestReturn(delivery.booking_id))}
          className="mt-4"
        />
      ) : null}
      {delivery.booking_status === 'RETURN_PENDING' ? (
        <Text className="mt-3 text-sm text-ink-muted">The owner has been told you are ready to return the car.</Text>
      ) : null}
    </>
  );
}
