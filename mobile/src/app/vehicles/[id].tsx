import Ionicons from '@expo/vector-icons/Ionicons';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import { useCallback, useState, type ComponentProps } from 'react';
import { ScrollView, Text, useWindowDimensions, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { Screen } from '@/components/ui/screen';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { VehiclePhoto } from '@/components/vehicle-photo';
import { COLORS } from '@/constants/brand';
import { useAsync } from '@/hooks/use-async';
import { ApiError } from '@/lib/api';
import { formatDateRange, formatFuelType, formatTransmission, formatZar } from '@/lib/format';
import { getAvailability, getVehicle } from '@/services/vehicles';
import type { MarketplaceVehicleDetail } from '@/types/vehicle';

type IconName = ComponentProps<typeof Ionicons>['name'];

function Spec({ icon, label }: { icon: IconName; label: string }) {
  return (
    <View className="w-[48%] flex-row items-center rounded-xl bg-surface-muted p-3">
      <Ionicons name={icon} size={18} color={COLORS.inkMuted} />
      <Text className="ml-2 text-sm text-ink">{label}</Text>
    </View>
  );
}

function PriceRow({ label, amount, strong = false }: { label: string; amount: string; strong?: boolean }) {
  return (
    <View className="flex-row justify-between py-1.5">
      <Text className={`text-base ${strong ? 'font-semibold text-ink' : 'text-ink-muted'}`}>{label}</Text>
      <Text className={`text-base ${strong ? 'font-semibold text-ink' : 'text-ink'}`}>{formatZar(amount)}</Text>
    </View>
  );
}

function PhotoCarousel({ vehicle }: { vehicle: MarketplaceVehicleDetail }) {
  const { width } = useWindowDimensions();
  const [index, setIndex] = useState(0);
  const photoWidth = width - 40; // Screen has 20px side padding
  if (vehicle.photos.length === 0) return <VehiclePhoto url={null} className="h-56" />;
  return (
    <View>
      <ScrollView
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={(event) =>
          setIndex(Math.round(event.nativeEvent.contentOffset.x / photoWidth))
        }>
        {vehicle.photos.map((photo, i) => (
          <View key={photo.id} style={{ width: photoWidth }}>
            <VehiclePhoto
              url={photo.url}
              className="h-56"
              accessibilityLabel={`${vehicle.make} ${vehicle.model} photo ${i + 1}`}
            />
          </View>
        ))}
      </ScrollView>
      {vehicle.photos.length > 1 ? (
        <Text className="mt-2 text-center text-xs text-ink-muted">
          Photo {index + 1} of {vehicle.photos.length}
        </Text>
      ) : null}
    </View>
  );
}

export default function VehicleDetailsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const loadVehicle = useCallback(() => getVehicle(id), [id]);
  const loadAvailability = useCallback(() => getAvailability(id), [id]);
  const result = useAsync(loadVehicle);
  const availability = useAsync(loadAvailability);

  if (result.status === 'loading') return <LoadingState />;
  if (result.status === 'error') {
    if (result.error instanceof ApiError && result.error.isNotFound) {
      return (
        <EmptyState
          icon="car-outline"
          title="Vehicle not found"
          message="This listing may no longer be available."
          actionLabel="Back to search"
          onAction={() => router.back()}
        />
      );
    }
    return <ErrorState message={result.error.message} onAction={result.reload} />;
  }

  const vehicle = result.data;
  const title = `${vehicle.make} ${vehicle.model}`;

  return (
    <Screen scroll>
      <Stack.Screen options={{ title }} />
      <PhotoCarousel vehicle={vehicle} />

      <View className="mt-5 flex-row items-start justify-between">
        <View className="flex-1 pr-3">
          <Text className="text-2xl font-bold text-ink">{title}</Text>
          <Text className="mt-1 text-base text-ink-muted">
            {vehicle.city}, {vehicle.province}
          </Text>
        </View>
        <View className="items-end">
          <Text className="text-2xl font-bold text-brand-600">{formatZar(vehicle.price.daily_rate)}</Text>
          <Text className="text-sm text-ink-muted">per day</Text>
        </View>
      </View>

      <View className="mt-6 flex-row flex-wrap justify-between gap-y-3">
        <Spec icon="calendar-outline" label={String(vehicle.year)} />
        <Spec icon="cog-outline" label={formatTransmission(vehicle.transmission)} />
        <Spec icon="water-outline" label={formatFuelType(vehicle.fuel_type)} />
        <Spec icon="people-outline" label={`${vehicle.seats} seats`} />
      </View>

      {vehicle.description ? (
        <>
          <Text className="mb-2 mt-8 text-lg font-semibold text-ink">About this car</Text>
          <Text className="text-base leading-6 text-ink-muted">{vehicle.description}</Text>
        </>
      ) : null}

      <Text className="mb-2 mt-8 text-lg font-semibold text-ink">Official pricing</Text>
      <View className="rounded-xl border border-surface-border p-4">
        <PriceRow label="Daily rate" amount={vehicle.price.daily_rate} strong />
        <PriceRow label="Delivery fee (once)" amount={vehicle.price.delivery_fee} />
        <PriceRow label="Refundable deposit" amount={vehicle.price.deposit_amount} />
        <Text className="mt-2 text-xs text-ink-subtle">Prices in ZAR, set by CarHire SA, VAT inclusive.</Text>
      </View>

      <Text className="mb-2 mt-8 text-lg font-semibold text-ink">Availability</Text>
      {availability.status === 'loading' ? (
        <Text className="text-base text-ink-muted">Checking dates…</Text>
      ) : availability.status === 'error' ? (
        <Text className="text-base text-ink-muted">Availability could not be loaded.</Text>
      ) : availability.data.unavailable.length === 0 ? (
        <Text className="text-base text-ink">Available for the next 60 days.</Text>
      ) : (
        <View>
          <Text className="mb-2 text-base text-ink-muted">Not available on these dates:</Text>
          {availability.data.unavailable.map((period) => (
            <View key={period.start_at} className="mb-1 flex-row items-center">
              <Ionicons name="close-circle-outline" size={16} color={COLORS.danger} />
              <Text className="ml-2 text-base text-ink">{formatDateRange(period.start_at, period.end_at)}</Text>
            </View>
          ))}
        </View>
      )}

      <View className="mt-8 flex-row items-center rounded-xl border border-surface-border p-4">
        <Ionicons name="person-circle-outline" size={36} color={COLORS.inkMuted} />
        <View className="ml-3">
          <Text className="text-sm text-ink-muted">Listed by</Text>
          <Text className="text-base font-semibold text-ink">
            {vehicle.owner.first_name} · {vehicle.owner.city}
          </Text>
        </View>
      </View>

      <Button label="Book this car" disabled className="mt-8" />
      <Text className="mt-2 text-center text-sm text-ink-muted">Booking opens in a later release.</Text>
    </Screen>
  );
}
