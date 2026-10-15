import { Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Linking, Text, View } from 'react-native';

import { SectionTitle } from '@/components/dashboard';
import { PickImageButtons } from '@/components/pick-image-buttons';
import { PrivateImage } from '@/components/private-image';
import { SignInPrompt } from '@/components/sign-in-prompt';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { TextField } from '@/components/ui/text-field';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { useLocationSharing } from '@/hooks/use-location-sharing';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/dates';
import { DELIVERY_STATUS, FUEL_LEVEL, PROBLEM_KIND } from '@/lib/labels';
import { scheduleChoices } from '@/lib/owner';
import {
  type AssignedDelivery,
  getMyDelivery,
  recordHandover,
  recordReturn,
  reportProblem,
  scheduleDelivery,
  startDelivery,
  uploadRecordPhoto,
} from '@/services/owner-deliveries';
import type { DeliveryException, FuelLevel, HandoverRecord } from '@/types/delivery';

const FUEL_LEVELS: FuelLevel[] = ['EMPTY', 'QUARTER', 'HALF', 'THREE_QUARTERS', 'FULL'];
const PROBLEMS: DeliveryException['kind'][] = ['DELAY', 'RENTER_UNAVAILABLE', 'ADDRESS_PROBLEM', 'VEHICLE_PROBLEM', 'OTHER'];
const MAX_PHOTOS = 10;
const RETURN_PHOTO_WINDOW_MS = 2 * 60 * 60 * 1000;

const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

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
    <View className="mt-4">
      <Text className="mb-2 text-sm text-ink-muted">
        Keep this screen open while you drive. The renter sees your position only while the car is on its way.
      </Text>
      {error ? <Notice tone="danger" message={error} /> : null}
      {sharing ? (
        <>
          <Notice tone="success" message={seconds === null ? 'Sharing your location…' : `Location shared ${seconds} s ago`} />
          <Button label="Stop sharing" variant="secondary" onPress={stop} className="mt-2" />
        </>
      ) : (
        <Button label="Share my location" onPress={start} />
      )}
    </View>
  );
}

function Schedule({ delivery, onChanged }: { delivery: AssignedDelivery; onChanged: () => void }) {
  const [choices] = useState(() => scheduleChoices(delivery.rental_start_at));
  const [choice, setChoice] = useState(choices[0]?.value ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await scheduleDelivery(delivery.id, choice ?? undefined);
      onChanged();
    } catch (e) {
      setError(message(e, 'Could not confirm the time.'));
      setBusy(false);
    }
  };
  return (
    <>
      <SectionTitle title="When will you deliver?" />
      <Text className="mb-2 text-sm text-ink-muted">Any time from 24 hours before the rental starts up to the start.</Text>
      <View className="mb-3 flex-row flex-wrap gap-y-2">
        {choices.map((c) => (
          <Chip key={c.value} label={c.label} selected={choice === c.value} onPress={() => setChoice(c.value)} />
        ))}
      </View>
      {choices.length === 0 ? <Notice tone="info" message="The rental has started. Contact support to arrange a time." /> : null}
      {error ? <Notice tone="danger" message={error} /> : null}
      <Button label="Confirm delivery time" disabled={choices.length === 0} loading={busy} onPress={save} className="mt-2" />
    </>
  );
}

function ConditionForm({
  title,
  intro,
  submitLabel,
  minOdometer,
  onSubmit,
}: {
  title: string;
  intro: string;
  submitLabel: string;
  minOdometer?: number;
  onSubmit: (record: { odometer_km: number; fuel_level: FuelLevel; condition_notes: string | null }) => Promise<void>;
}) {
  const [odometer, setOdometer] = useState('');
  const [fuel, setFuel] = useState<FuelLevel | null>(null);
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    const km = Number(odometer);
    if (!/^\d{1,7}$/.test(odometer)) return setError('Enter the odometer reading in km.');
    if (minOdometer !== undefined && km < minOdometer) {
      return setError(`The odometer cannot be lower than at handover (${minOdometer} km).`);
    }
    if (!fuel) return setError('Choose the fuel level.');
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ odometer_km: km, fuel_level: fuel, condition_notes: notes.trim() || null });
    } catch (e) {
      setError(message(e, 'Could not save the record.'));
      setBusy(false);
    }
  };
  return (
    <>
      <SectionTitle title={title} />
      <Text className="mb-3 text-sm text-ink-muted">{intro}</Text>
      <TextField label="Odometer (km)" value={odometer} onChangeText={setOdometer} keyboardType="number-pad" maxLength={7} />
      <Text className="mb-1.5 text-sm font-medium text-ink">Fuel level</Text>
      <View className="mb-4 flex-row flex-wrap gap-y-2">
        {FUEL_LEVELS.map((level) => (
          <Chip key={level} label={FUEL_LEVEL[level]} selected={fuel === level} onPress={() => setFuel(level)} />
        ))}
      </View>
      <TextField
        label="Condition notes (scratches, dents, cleanliness)"
        value={notes}
        onChangeText={setNotes}
        multiline
        maxLength={2000}
        style={{ height: 96, paddingTop: 12, textAlignVertical: 'top' }}
      />
      {error ? (
        <View className="mb-3">
          <Notice tone="danger" message={error} />
        </View>
      ) : null}
      <Button label={submitLabel} loading={busy} onPress={save} />
    </>
  );
}

function RecordView({
  delivery,
  record,
  canAddPhotos,
  onChanged,
}: {
  delivery: AssignedDelivery;
  record: HandoverRecord;
  canAddPhotos: boolean;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const title = record.kind === 'HANDOVER' ? 'Handover' : 'Return';
  return (
    <>
      <SectionTitle title={title} />
      <Row label="Recorded" value={formatDateTime(record.recorded_at)} />
      <Row label="Odometer" value={`${record.odometer_km} km`} />
      <Row label="Fuel" value={FUEL_LEVEL[record.fuel_level]} />
      {record.condition_notes ? <Row label="Notes" value={record.condition_notes} /> : null}
      {record.kind === 'HANDOVER' ? (
        <Row
          label="Renter"
          value={record.renter_acknowledged_at ? `Confirmed ${formatDateTime(record.renter_acknowledged_at)}` : 'Not confirmed yet'}
        />
      ) : null}
      {record.renter_notes ? (
        <View className="mt-2">
          <Notice tone="info" message={`Renter noted: ${record.renter_notes}`} />
        </View>
      ) : null}
      <View className="mt-2 flex-row flex-wrap gap-2">
        {record.photos.map((photo, i) => (
          <PrivateImage key={photo.id} path={photo.url} className="h-20 w-20" label={`${title} photo ${i + 1}`} />
        ))}
      </View>
      {error ? (
        <View className="mt-2">
          <Notice tone="danger" message={error} />
        </View>
      ) : null}
      {canAddPhotos && record.photos.length < MAX_PHOTOS ? (
        <>
          <Text className="mt-2 text-sm text-ink-muted">
            {record.kind === 'HANDOVER'
              ? 'Add photos of every side and the dashboard before the renter confirms.'
              : 'Add photos of the car as it came back (within 2 hours).'}
          </Text>
          <PickImageButtons
            onError={setError}
            onPicked={async (file) => {
              setError(null);
              await uploadRecordPhoto(delivery.id, record.kind, file);
              onChanged();
            }}
          />
        </>
      ) : null}
    </>
  );
}

function ReportProblem({ delivery, onChanged }: { delivery: AssignedDelivery; onChanged: () => void }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<DeliveryException['kind']>('DELAY');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!open) return <Button label="Report a problem" variant="ghost" className="mt-4" onPress={() => setOpen(true)} />;
  const send = async () => {
    if (notes.trim().length < 3) return setError('Describe what happened.');
    setBusy(true);
    setError(null);
    try {
      await reportProblem(delivery.id, kind, notes.trim());
      setOpen(false);
      setNotes('');
      onChanged();
    } catch (e) {
      setError(message(e, 'Could not send the report.'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <SectionTitle title="Report a problem" />
      <View className="mb-3 flex-row flex-wrap gap-y-2">
        {PROBLEMS.map((p) => (
          <Chip key={p} label={PROBLEM_KIND[p]} selected={kind === p} onPress={() => setKind(p)} />
        ))}
      </View>
      <Text className="mb-2 text-sm text-ink-muted">
        {kind === 'DELAY'
          ? 'The renter sees your note; the delivery continues.'
          : 'This stops the delivery. CarHire SA support will reschedule it or cancel the booking (the renter is refunded).'}
      </Text>
      <TextField label="What happened?" value={notes} onChangeText={setNotes} multiline maxLength={1000} style={{ height: 80, paddingTop: 12, textAlignVertical: 'top' }} />
      {error ? (
        <View className="mb-3">
          <Notice tone="danger" message={error} />
        </View>
      ) : null}
      <View className="flex-row gap-3">
        <Button label="Cancel" variant="secondary" className="flex-1" onPress={() => setOpen(false)} />
        <Button label="Send" className="flex-1" loading={busy} onPress={send} />
      </View>
    </>
  );
}

function DeliveryDetails({ delivery, onChanged }: { delivery: AssignedDelivery; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openedAt] = useState(() => Date.now());
  const { status, handover, return_record: returned } = delivery;
  const active = status === 'PENDING_SCHEDULE' || status === 'SCHEDULED' || status === 'EN_ROUTE';
  const awaitingReturn =
    status === 'DELIVERED' && !returned && ['DELIVERED', 'ACTIVE_RENTAL', 'RETURN_PENDING'].includes(delivery.booking_status);
  const returnPhotosOpen = returned !== null && openedAt - Date.parse(returned.recorded_at) < RETURN_PHOTO_WINDOW_MS;

  const setOff = async () => {
    setBusy(true);
    setError(null);
    try {
      await startDelivery(delivery.id);
      onChanged();
    } catch (e) {
      setError(message(e, 'Could not update the delivery.'));
      setBusy(false);
    }
  };

  return (
    <Screen scroll>
      <Stack.Screen options={{ title: `Delivery ${delivery.booking_reference}` }} />
      <Text className="text-2xl font-bold text-ink">
        {delivery.vehicle.make} {delivery.vehicle.model}
      </Text>
      <Text className="text-base text-ink-muted">
        {delivery.registration_number} · {DELIVERY_STATUS[status]}
      </Text>
      <View className="mt-4">
        <Row label="Renter" value={delivery.renter.full_name} />
        <Row label="Deliver to" value={delivery.dropoff_address} />
        <Row label="Rental" value={`${formatDateTime(delivery.rental_start_at)} → ${formatDateTime(delivery.rental_end_at)}`} />
        <Row label="Delivery time" value={delivery.scheduled_for ? formatDateTime(delivery.scheduled_for) : 'Not confirmed yet'} />
      </View>
      {delivery.renter.phone_number && (active || awaitingReturn) ? (
        <Button
          label={`Call ${delivery.renter.full_name.split(' ')[0]}`}
          variant="secondary"
          className="mt-3"
          onPress={() => Linking.openURL(`tel:${delivery.renter.phone_number}`)}
        />
      ) : null}

      {delivery.exceptions
        .filter((x) => !x.resolved_at)
        .map((x) => (
          <View key={x.id} className="mt-3">
            <Notice tone={x.kind === 'DELAY' ? 'info' : 'danger'} message={`${PROBLEM_KIND[x.kind]}: ${x.notes}`} />
          </View>
        ))}
      {status === 'FAILED' ? (
        <View className="mt-3">
          <Notice tone="danger" message="This delivery is stopped. CarHire SA support will reschedule it or cancel the booking." />
        </View>
      ) : null}
      {error ? (
        <View className="mt-4">
          <Notice tone="danger" message={error} />
        </View>
      ) : null}

      {status === 'PENDING_SCHEDULE' ? <Schedule delivery={delivery} onChanged={onChanged} /> : null}
      {status === 'SCHEDULED' ? <Button label="Set off now" loading={busy} onPress={setOff} className="mt-6" /> : null}
      {status === 'EN_ROUTE' ? (
        <>
          <Sharing deliveryId={delivery.id} onEnded={onChanged} />
          <ConditionForm
            title="Hand over the car"
            intro="Record the car's condition with the renter present. You can add photos next."
            submitLabel="Record handover"
            onSubmit={async (record) => {
              await recordHandover(delivery.id, record);
              onChanged();
            }}
          />
        </>
      ) : null}

      {handover ? (
        <RecordView delivery={delivery} record={handover} canAddPhotos={!handover.renter_acknowledged_at} onChanged={onChanged} />
      ) : null}
      {awaitingReturn ? (
        <ConditionForm
          title="Record the return"
          intro={
            delivery.booking_status === 'RETURN_PENDING'
              ? 'The renter is ready to return the car. Record its condition when you collect it.'
              : 'Record the car’s condition when you collect it. This completes the booking.'
          }
          submitLabel="Record return"
          minOdometer={handover?.odometer_km}
          onSubmit={async (record) => {
            await recordReturn(delivery.id, record);
            onChanged();
          }}
        />
      ) : null}
      {returned ? <RecordView delivery={delivery} record={returned} canAddPhotos={returnPhotosOpen} onChanged={onChanged} /> : null}

      {active ? <ReportProblem delivery={delivery} onChanged={onChanged} /> : null}
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
