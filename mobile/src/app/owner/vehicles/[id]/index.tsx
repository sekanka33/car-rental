import Ionicons from '@expo/vector-icons/Ionicons';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert, Platform, Pressable, Text, View } from 'react-native';

import { SectionTitle } from '@/components/dashboard';
import { PickImageButtons } from '@/components/pick-image-buttons';
import { PrivateImage } from '@/components/private-image';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { ErrorState, LoadingState } from '@/components/ui/state-views';
import { TextField } from '@/components/ui/text-field';
import { COLORS } from '@/constants/brand';
import { useAsync } from '@/hooks/use-async';
import { useReloadOnFocus } from '@/hooks/use-reload-on-focus';
import { ApiError } from '@/lib/api';
import { formatDateTime, saToday } from '@/lib/dates';
import { formatZar } from '@/lib/format';
import { DOCUMENT_TYPE, EXPIRING_DOCUMENTS, isIsoDate, VEHICLE_STATUS } from '@/lib/labels';
import { pickDocument, type PickedFile, pickImage } from '@/lib/upload';
import {
  deleteVehicle,
  deleteVehiclePhoto,
  getMyVehicle,
  setListed,
  submitVehicle,
  uploadVehicleDocument,
  uploadVehiclePhoto,
  vehiclePhotoPath,
  withdrawVehicle,
} from '@/services/owner';
import type { OwnerVehicle, VehicleDocumentType } from '@/types/owner';

const MIN_PHOTOS = 3;
const MAX_PHOTOS = 12;
const DOCUMENT_TYPES: VehicleDocumentType[] = ['REGISTRATION_CERTIFICATE', 'LICENCE_DISC', 'INSURANCE', 'ROADWORTHY_CERTIFICATE'];
const REQUIRED: VehicleDocumentType[] = ['REGISTRATION_CERTIFICATE', 'LICENCE_DISC', 'INSURANCE'];

/** The API's message (it lists anything missing before a submission), else `fallback`. */
function errorText(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

/** Asks before something that cannot be undone (window.confirm on web). */
function confirm(title: string, message: string, action: string): Promise<boolean> {
  if (Platform.OS === 'web') return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  return new Promise((resolve) =>
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
      { text: action, style: 'destructive', onPress: () => resolve(true) },
    ]),
  );
}

function Photos({ vehicle, onChanged, onError }: { vehicle: OwnerVehicle; onChanged: () => void; onError: (m: string) => void }) {
  const locked = vehicle.status === 'PENDING_APPROVAL' || vehicle.status === 'SUSPENDED';
  const remove = async (photoId: string) => {
    if (!(await confirm('Remove photo?', 'The photo is deleted.', 'Remove'))) return;
    try {
      await deleteVehiclePhoto(vehicle.id, photoId);
      onChanged();
    } catch (e) {
      onError(errorText(e, 'Could not remove the photo.'));
    }
  };
  return (
    <>
      <SectionTitle title={`Photos (${vehicle.photos.length}/${MAX_PHOTOS})`} />
      <View className="flex-row flex-wrap gap-2">
        {vehicle.photos.map((photo, index) => (
          <View key={photo.id}>
            <PrivateImage path={vehiclePhotoPath(vehicle.id, photo.id)} label={`Photo ${index + 1}`} />
            {!locked ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Remove photo ${index + 1}`}
                onPress={() => remove(photo.id)}
                className="absolute right-1 top-1 rounded-full bg-white/90 p-1">
                <Ionicons name="close" size={16} color={COLORS.ink} />
              </Pressable>
            ) : null}
          </View>
        ))}
      </View>
      {vehicle.photos.length < MIN_PHOTOS ? (
        <Text className="mt-2 text-sm text-ink-muted">Add at least {MIN_PHOTOS} clear photos: front, back, side and inside.</Text>
      ) : null}
      {!locked && vehicle.photos.length < MAX_PHOTOS ? (
        <PickImageButtons
          onError={onError}
          onPicked={async (file) => {
            await uploadVehiclePhoto(vehicle.id, file);
            onChanged();
          }}
        />
      ) : null}
    </>
  );
}

function DocumentRow({
  vehicle,
  type,
  onChanged,
  onError,
}: {
  vehicle: OwnerVehicle;
  type: VehicleDocumentType;
  onChanged: () => void;
  onError: (m: string) => void;
}) {
  const current = vehicle.documents.find((d) => d.document_type === type && d.is_current);
  const needsExpiry = EXPIRING_DOCUMENTS.includes(type);
  const expired = vehicle.compliance.expired.includes(type);
  const [open, setOpen] = useState(false);
  const [expiry, setExpiry] = useState('');
  const [expiryError, setExpiryError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (pick: () => Promise<PickedFile | null>) => {
    if (needsExpiry && (!isIsoDate(expiry) || expiry <= saToday())) {
      setExpiryError('Enter the expiry date as YYYY-MM-DD (in the future).');
      return;
    }
    setExpiryError(null);
    setBusy(true);
    try {
      const file = await pick();
      if (file) {
        await uploadVehicleDocument(vehicle.id, type, file, needsExpiry ? expiry : null);
        setOpen(false);
        setExpiry('');
        onChanged();
      }
    } catch (e) {
      onError(e instanceof Error && !(e instanceof ApiError) ? e.message : errorText(e, 'Could not upload the document.'));
    } finally {
      setBusy(false);
    }
  };

  const status = current
    ? expired
      ? { label: 'Expired', tone: 'danger' as const }
      : { label: 'Uploaded', tone: 'success' as const }
    : REQUIRED.includes(type)
      ? { label: 'Required', tone: 'warning' as const }
      : { label: 'Optional', tone: 'neutral' as const };

  return (
    <View className="border-b border-surface-border py-3">
      <View className="flex-row items-center justify-between">
        <Text className="flex-1 pr-2 text-base text-ink">{DOCUMENT_TYPE[type]}</Text>
        <Badge label={status.label} tone={status.tone} />
      </View>
      {current ? (
        <Text className="mt-1 text-sm text-ink-muted">
          Uploaded {formatDateTime(current.uploaded_at)}
          {current.expiry_date ? ` · expires ${current.expiry_date}` : ''}
        </Text>
      ) : null}
      {open ? (
        <View className="mt-3">
          {needsExpiry ? (
            <TextField label="Expiry date" value={expiry} onChangeText={setExpiry} placeholder="YYYY-MM-DD" maxLength={10} error={expiryError} />
          ) : null}
          <View className="flex-row gap-3">
            <Button label="PDF or file" variant="secondary" className="flex-1" loading={busy} onPress={() => upload(pickDocument)} />
            <Button label="Photo" variant="secondary" className="flex-1" loading={busy} onPress={() => upload(() => pickImage(Platform.OS === 'web' ? 'library' : 'camera'))} />
          </View>
        </View>
      ) : vehicle.status !== 'SUSPENDED' ? (
        <Button label={current ? 'Upload a renewed one' : 'Upload'} variant="ghost" className="mt-1 self-start px-0" onPress={() => setOpen(true)} />
      ) : null}
    </View>
  );
}

function Actions({ vehicle, onChanged, onError }: { vehicle: OwnerVehicle; onChanged: () => void; onError: (m: string) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const run = async (name: string, action: () => Promise<unknown>, after = onChanged) => {
    setBusy(name);
    try {
      await action();
      after();
    } catch (e) {
      onError(errorText(e, 'That did not work. Please try again.'));
    } finally {
      setBusy(null);
    }
  };
  const ready = vehicle.photos.length >= MIN_PHOTOS && vehicle.compliance.ok;
  const editable = ['DRAFT', 'REJECTED', 'APPROVED', 'UNAVAILABLE'].includes(vehicle.status);
  const listed = vehicle.status === 'APPROVED' || vehicle.status === 'UNAVAILABLE';

  return (
    <View className="mt-6 gap-3">
      {vehicle.status === 'DRAFT' || vehicle.status === 'REJECTED' ? (
        <>
          {!ready ? (
            <Text className="text-sm text-ink-muted">
              To submit: a confirmed email address, at least {MIN_PHOTOS} photos and a current registration certificate, licence disc and proof of insurance.
            </Text>
          ) : null}
          <Button label="Submit for review" disabled={!ready} loading={busy === 'submit'} onPress={() => run('submit', () => submitVehicle(vehicle.id))} />
        </>
      ) : null}
      {vehicle.status === 'PENDING_APPROVAL' ? (
        <Button label="Withdraw from review" variant="secondary" loading={busy === 'withdraw'} onPress={() => run('withdraw', () => withdrawVehicle(vehicle.id))} />
      ) : null}
      {listed ? (
        <>
          <Button
            label={vehicle.status === 'APPROVED' ? 'Hide from the marketplace' : 'List again'}
            variant="secondary"
            loading={busy === 'listing'}
            onPress={() => run('listing', () => setListed(vehicle.id, vehicle.status !== 'APPROVED'))}
          />
          <Button
            label="Blocked dates"
            variant="secondary"
            onPress={() => router.push({ pathname: '/owner/vehicles/[id]/availability', params: { id: vehicle.id } })}
          />
        </>
      ) : null}
      {editable ? (
        <Button label="Edit details" variant="secondary" onPress={() => router.push({ pathname: '/owner/vehicles/[id]/edit', params: { id: vehicle.id } })} />
      ) : null}
      {vehicle.status === 'DRAFT' || vehicle.status === 'REJECTED' ? (
        <Button
          label="Delete this car"
          variant="ghost"
          loading={busy === 'delete'}
          onPress={async () => {
            if (await confirm('Delete this car?', 'Its photos and documents are deleted too.', 'Delete')) {
              await run('delete', () => deleteVehicle(vehicle.id), () => router.back());
            }
          }}
        />
      ) : null}
    </View>
  );
}

function VehicleDetails({ vehicle, reload }: { vehicle: OwnerVehicle; reload: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const status = VEHICLE_STATUS[vehicle.status];
  const changed = () => {
    setError(null);
    reload();
  };
  return (
    <Screen scroll>
      <Stack.Screen options={{ title: `${vehicle.make} ${vehicle.model}` }} />
      <View className="flex-row items-start justify-between">
        <View className="flex-1 pr-2">
          <Text className="text-2xl font-bold text-ink">
            {vehicle.year} {vehicle.make} {vehicle.model}
          </Text>
          <Text className="text-base text-ink-muted">
            {vehicle.registration_number} · {vehicle.city}, {vehicle.province}
          </Text>
        </View>
        <Badge label={status.label} tone={status.tone} />
      </View>

      {vehicle.status === 'REJECTED' && vehicle.rejection_reason ? (
        <View className="mt-4">
          <Notice tone="danger" message={`Not approved: ${vehicle.rejection_reason}. Fix this and submit again.`} />
        </View>
      ) : null}
      {vehicle.status === 'SUSPENDED' ? (
        <View className="mt-4">
          <Notice tone="danger" message={`Suspended${vehicle.suspension_reason ? `: ${vehicle.suspension_reason}` : ''}. Contact support.`} />
        </View>
      ) : null}
      {vehicle.status === 'APPROVED' && !vehicle.compliance.ok ? (
        <View className="mt-4">
          <Notice tone="danger" message="A document has expired, so renters cannot find this car. Upload the renewed one below." />
        </View>
      ) : null}

      <View className="mt-4 rounded-2xl bg-surface-muted p-4">
        <Text className="text-sm text-ink-muted">Official price (set by CarHire SA)</Text>
        <Text className="mt-1 text-lg font-semibold text-ink">
          {vehicle.current_price ? `${formatZar(vehicle.current_price.daily_rate)} per day` : 'Not set yet'}
        </Text>
        {vehicle.current_price ? (
          <Text className="text-sm text-ink-muted">
            Delivery {formatZar(vehicle.current_price.delivery_fee)} · deposit {formatZar(vehicle.current_price.deposit_amount)}
          </Text>
        ) : null}
      </View>

      {error ? (
        <View className="mt-4">
          <Notice tone="danger" message={error} />
        </View>
      ) : null}

      <Photos vehicle={vehicle} onChanged={changed} onError={setError} />
      <SectionTitle title="Documents" />
      {DOCUMENT_TYPES.map((type) => (
        <DocumentRow key={type} vehicle={vehicle} type={type} onChanged={changed} onError={setError} />
      ))}
      <Actions vehicle={vehicle} onChanged={changed} onError={setError} />
    </Screen>
  );
}

export default function OwnerVehicleScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const load = useCallback(() => getMyVehicle(id), [id]);
  const vehicle = useAsync(load);
  useReloadOnFocus(vehicle.reload);
  if (vehicle.status === 'loading') return <LoadingState />;
  if (vehicle.status === 'error') return <ErrorState message={vehicle.error.message} onAction={vehicle.reload} />;
  return <VehicleDetails vehicle={vehicle.data} reload={vehicle.reload} />;
}
