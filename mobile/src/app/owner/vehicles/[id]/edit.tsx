import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useCallback } from 'react';

import { Screen } from '@/components/ui/screen';
import { ErrorState, LoadingState } from '@/components/ui/state-views';
import { VehicleForm } from '@/components/vehicle-form';
import { useAsync } from '@/hooks/use-async';
import { getMyVehicle, updateVehicle } from '@/services/owner';
import type { VehicleInput } from '@/types/owner';

const FIELDS: (keyof VehicleInput)[] = [
  'make',
  'model',
  'year',
  'registration_number',
  'vin',
  'colour',
  'transmission',
  'fuel_type',
  'seats',
  'city',
  'province',
  'description',
];

export default function EditVehicleScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const load = useCallback(() => getMyVehicle(id), [id]);
  const vehicle = useAsync(load);
  if (vehicle.status === 'loading') return <LoadingState />;
  if (vehicle.status === 'error') return <ErrorState message={vehicle.error.message} onAction={vehicle.reload} />;
  const reviewed = vehicle.data.status === 'APPROVED' || vehicle.data.status === 'UNAVAILABLE';
  return (
    <Screen scroll>
      <Stack.Screen options={{ title: 'Edit car' }} />
      <VehicleForm
        initial={vehicle.data}
        submitLabel="Save changes"
        note={
          reviewed
            ? 'Changing the make, model, year, registration, VIN, transmission, fuel type or seats sends the car back for review, and it leaves the marketplace until approved. Colour, location and description do not.'
            : undefined
        }
        onSubmit={async (input) => {
          // Send only what changed, so cosmetic edits never trigger a review.
          const changes = Object.fromEntries(
            FIELDS.filter((key) => input[key] !== vehicle.data[key]).map((key) => [key, input[key]]),
          ) as Partial<VehicleInput>;
          if (Object.keys(changes).length > 0) await updateVehicle(id, changes);
          router.back();
        }}
      />
    </Screen>
  );
}
