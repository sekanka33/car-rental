import { router, Stack } from 'expo-router';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { useAsync } from '@/hooks/use-async';
import { useReloadOnFocus } from '@/hooks/use-reload-on-focus';
import { formatZar } from '@/lib/format';
import { VEHICLE_STATUS } from '@/lib/labels';
import { listMyVehicles } from '@/services/owner';
import type { OwnerVehicle } from '@/types/owner';

function nextStep(vehicle: OwnerVehicle): string {
  switch (vehicle.status) {
    case 'DRAFT':
      return 'Add photos and documents, then submit for review';
    case 'REJECTED':
      return vehicle.rejection_reason ? `Rejected: ${vehicle.rejection_reason}` : 'Rejected: see details';
    case 'PENDING_APPROVAL':
      return 'An administrator is reviewing it';
    case 'SUSPENDED':
      return 'Suspended by an administrator';
    case 'UNAVAILABLE':
      return 'Hidden from the marketplace';
    default:
      return vehicle.current_price ? `${formatZar(vehicle.current_price.daily_rate)} per day` : 'Waiting for an official price';
  }
}

function VehicleRow({ vehicle }: { vehicle: OwnerVehicle }) {
  const status = VEHICLE_STATUS[vehicle.status];
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => router.push({ pathname: '/owner/vehicles/[id]', params: { id: vehicle.id } })}
      className="mb-3 rounded-2xl border border-surface-border bg-white p-4 active:opacity-80">
      <View className="flex-row items-start justify-between">
        <Text className="flex-1 pr-2 text-lg font-semibold text-ink">
          {vehicle.year} {vehicle.make} {vehicle.model}
        </Text>
        <Badge label={status.label} tone={status.tone} />
      </View>
      <Text className="mt-0.5 text-sm text-ink-muted">{vehicle.registration_number}</Text>
      <Text className="mt-2 text-sm text-ink">{nextStep(vehicle)}</Text>
      {!vehicle.compliance.ok && vehicle.status !== 'DRAFT' ? (
        <Text className="mt-1 text-sm text-warning">Documents need attention</Text>
      ) : null}
    </Pressable>
  );
}

export default function MyVehiclesScreen() {
  const vehicles = useAsync(listMyVehicles);
  useReloadOnFocus(vehicles.reload);
  return (
    <>
      <Stack.Screen options={{ title: 'My cars' }} />
      {vehicles.status === 'loading' ? (
        <LoadingState />
      ) : vehicles.status === 'error' ? (
        <ErrorState message={vehicles.error.message} onAction={vehicles.reload} />
      ) : (
        <FlatList
          className="flex-1 bg-surface-muted"
          data={vehicles.data}
          keyExtractor={(v) => v.id}
          renderItem={({ item }) => <VehicleRow vehicle={item} />}
          contentContainerClassName="flex-grow p-5"
          refreshControl={<RefreshControl refreshing={false} onRefresh={vehicles.reload} />}
          ListHeaderComponent={<Button label="Register a car" className="mb-4" onPress={() => router.push('/owner/vehicles/new')} />}
          ListEmptyComponent={
            <EmptyState
              icon="car-sport-outline"
              title="No cars yet"
              message="Register your car, add photos and documents, and submit it for review."
            />
          }
        />
      )}
    </>
  );
}
