import Ionicons from '@expo/vector-icons/Ionicons';
import { useMemo, useState } from 'react';
import { FlatList, TextInput, View } from 'react-native';

import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { VehicleCard } from '@/components/vehicle-card';
import { COLORS } from '@/constants/brand';
import { useAsync } from '@/hooks/use-async';
import { listVehicles } from '@/services/vehicles';
import type { Vehicle } from '@/types/vehicle';

function matchesQuery(vehicle: Vehicle, query: string) {
  const haystack = `${vehicle.make} ${vehicle.model} ${vehicle.city} ${vehicle.province}`;
  return haystack.toLowerCase().includes(query.toLowerCase());
}

export default function HomeScreen() {
  const vehicles = useAsync(listVehicles);
  const [query, setQuery] = useState('');

  const results = useMemo(() => {
    const trimmed = query.trim();
    if (vehicles.status !== 'success') return [];
    return trimmed ? vehicles.data.filter((v) => matchesQuery(v, trimmed)) : vehicles.data;
  }, [vehicles.status, vehicles.data, query]);

  if (vehicles.status === 'loading') return <LoadingState message="Finding cars near you…" />;
  if (vehicles.status === 'error') {
    return (
      <ErrorState
        message="We couldn't load vehicles. Check your connection and try again."
        onAction={vehicles.reload}
      />
    );
  }

  return (
    <View className="flex-1 bg-surface-muted">
      <View className="border-b border-surface-border bg-white px-5 py-3">
        <View className="h-11 flex-row items-center rounded-xl bg-surface-muted px-3">
          <Ionicons name="search" size={18} color={COLORS.inkMuted} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder="Search by make, model or city"
            placeholderTextColor={COLORS.inkSubtle}
            accessibilityLabel="Search vehicles"
            autoCorrect={false}
            returnKeyType="search"
            className="ml-2 flex-1 text-base text-ink"
          />
        </View>
      </View>
      <FlatList
        data={results}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <VehicleCard vehicle={item} />}
        contentContainerClassName="flex-grow p-5"
        keyboardShouldPersistTaps="handled"
        ListEmptyComponent={
          query.trim() ? (
            <EmptyState
              title="No matching cars"
              message={`Nothing matches "${query.trim()}". Try another search.`}
              actionLabel="Clear search"
              onAction={() => setQuery('')}
            />
          ) : (
            <EmptyState title="No cars available yet" message="Check back soon for new listings." />
          )
        }
      />
    </View>
  );
}
