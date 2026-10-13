import Ionicons from '@expo/vector-icons/Ionicons';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import { useCallback, type ComponentProps } from 'react';
import { Text, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { Screen } from '@/components/ui/screen';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { VehiclePhoto } from '@/components/vehicle-photo';
import { COLORS } from '@/constants/brand';
import { useAsync } from '@/hooks/use-async';
import { formatFuelType, formatTransmission, formatZar } from '@/lib/format';
import { getVehicle } from '@/services/vehicles';

type IconName = ComponentProps<typeof Ionicons>['name'];

function Spec({ icon, label }: { icon: IconName; label: string }) {
  return (
    <View className="w-[48%] flex-row items-center rounded-xl bg-surface-muted p-3">
      <Ionicons name={icon} size={18} color={COLORS.inkMuted} />
      <Text className="ml-2 text-sm text-ink">{label}</Text>
    </View>
  );
}

export default function VehicleDetailsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const loader = useCallback(() => getVehicle(id), [id]);
  const result = useAsync(loader);

  if (result.status === 'loading') return <LoadingState />;
  if (result.status === 'error') {
    return <ErrorState message="We couldn't load this vehicle." onAction={result.reload} />;
  }
  if (!result.data) {
    return (
      <EmptyState
        icon="car-outline"
        title="Vehicle not found"
        message="This listing may have been removed."
        actionLabel="Back to search"
        onAction={() => router.back()}
      />
    );
  }

  const vehicle = result.data;
  const title = `${vehicle.make} ${vehicle.model}`;

  return (
    <Screen scroll>
      <Stack.Screen options={{ title }} />
      <VehiclePhoto className="h-56" />

      <View className="mt-5 flex-row items-start justify-between">
        <View className="flex-1 pr-3">
          <Text className="text-2xl font-bold text-ink">{title}</Text>
          <Text className="mt-1 text-base text-ink-muted">
            {vehicle.city}, {vehicle.province}
          </Text>
        </View>
        <View className="items-end">
          <Text className="text-2xl font-bold text-brand-600">{formatZar(vehicle.dailyRate)}</Text>
          <Text className="text-sm text-ink-muted">per day</Text>
        </View>
      </View>

      <View className="mt-6 flex-row flex-wrap justify-between gap-y-3">
        <Spec icon="calendar-outline" label={String(vehicle.year)} />
        <Spec icon="cog-outline" label={formatTransmission(vehicle.transmission)} />
        <Spec icon="water-outline" label={formatFuelType(vehicle.fuelType)} />
        <Spec icon="people-outline" label={`${vehicle.seats} seats`} />
      </View>

      <Text className="mb-2 mt-8 text-lg font-semibold text-ink">About this car</Text>
      <Text className="text-base leading-6 text-ink-muted">{vehicle.description}</Text>

      {vehicle.features.length > 0 ? (
        <>
          <Text className="mb-2 mt-6 text-lg font-semibold text-ink">Features</Text>
          {vehicle.features.map((feature) => (
            <View key={feature} className="mb-2 flex-row items-center">
              <Ionicons name="checkmark-circle" size={18} color={COLORS.brand} />
              <Text className="ml-2 text-base text-ink">{feature}</Text>
            </View>
          ))}
        </>
      ) : null}

      <View className="mt-6 flex-row items-center rounded-xl border border-surface-border p-4">
        <Ionicons name="person-circle-outline" size={36} color={COLORS.inkMuted} />
        <View className="ml-3">
          <Text className="text-sm text-ink-muted">Listed by</Text>
          <Text className="text-base font-semibold text-ink">{vehicle.ownerFirstName}</Text>
        </View>
      </View>

      <Button label="Book this car" disabled className="mt-8" />
      <Text className="mt-2 text-center text-sm text-ink-muted">
        Booking opens in a later release.
      </Text>
    </Screen>
  );
}
