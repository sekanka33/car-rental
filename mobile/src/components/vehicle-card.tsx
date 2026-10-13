import Ionicons from '@expo/vector-icons/Ionicons';
import { Link } from 'expo-router';
import { Pressable, Text, View } from 'react-native';

import { COLORS } from '@/constants/brand';
import { formatTransmission, formatZar } from '@/lib/format';
import type { MarketplaceVehicle } from '@/types/vehicle';

import { VehiclePhoto } from './vehicle-photo';

export function VehicleCard({ vehicle }: { vehicle: MarketplaceVehicle }) {
  const title = `${vehicle.make} ${vehicle.model}`;
  return (
    <Link href={{ pathname: '/vehicles/[id]', params: { id: vehicle.id } }} asChild>
      <Pressable
        accessibilityLabel={`${title}, ${formatZar(vehicle.price.daily_rate)} per day`}
        className="mb-4 rounded-2xl border border-surface-border bg-white p-3 active:opacity-80">
        <VehiclePhoto url={vehicle.primary_photo_url} accessibilityLabel={title} />
        <View className="mt-3 flex-row items-start justify-between">
          <View className="flex-1 pr-3">
            <Text className="text-lg font-semibold text-ink">{title}</Text>
            <Text className="text-sm text-ink-muted">
              {vehicle.year} · {formatTransmission(vehicle.transmission)} · {vehicle.seats} seats
            </Text>
          </View>
          <View className="items-end">
            <Text className="text-lg font-bold text-brand-600">{formatZar(vehicle.price.daily_rate)}</Text>
            <Text className="text-xs text-ink-muted">per day</Text>
          </View>
        </View>
        <View className="mt-2 flex-row items-center">
          <Ionicons name="location-outline" size={14} color={COLORS.inkMuted} />
          <Text className="ml-1 text-sm text-ink-muted">
            {vehicle.city}, {vehicle.province}
          </Text>
        </View>
      </Pressable>
    </Link>
  );
}
