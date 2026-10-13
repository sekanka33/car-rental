import Ionicons from '@expo/vector-icons/Ionicons';
import { useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, RefreshControl, ScrollView, Text, TextInput, View } from 'react-native';

import { Chip } from '@/components/ui/chip';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { VehicleCard } from '@/components/vehicle-card';
import { COLORS } from '@/constants/brand';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { useVehicleSearch } from '@/hooks/use-vehicle-search';
import type { FuelType, SearchFilters, SortOrder, Transmission } from '@/types/vehicle';

const TRANSMISSIONS: { label: string; value?: Transmission }[] = [
  { label: 'Any gearbox' },
  { label: 'Automatic', value: 'AUTOMATIC' },
  { label: 'Manual', value: 'MANUAL' },
];
const FUELS: { label: string; value?: FuelType }[] = [
  { label: 'Any fuel' },
  { label: 'Petrol', value: 'PETROL' },
  { label: 'Diesel', value: 'DIESEL' },
  { label: 'Hybrid', value: 'HYBRID' },
  { label: 'Electric', value: 'ELECTRIC' },
];
const MAX_PRICES: { label: string; value?: string }[] = [
  { label: 'Any price' },
  { label: 'Up to R500/day', value: '500.00' },
  { label: 'Up to R800/day', value: '800.00' },
  { label: 'Up to R1 200/day', value: '1200.00' },
];
const SORTS: { label: string; value: SortOrder }[] = [
  { label: 'Lowest price', value: 'price_asc' },
  { label: 'Highest price', value: 'price_desc' },
  { label: 'Newest', value: 'newest' },
];

function ChipRow<T>({
  options,
  selected,
  onSelect,
}: {
  options: { label: string; value?: T }[];
  selected: T | undefined;
  onSelect: (value: T | undefined) => void;
}) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} className="mt-2">
      {options.map((option) => (
        <Chip
          key={option.label}
          label={option.label}
          selected={option.value === selected}
          onPress={() => onSelect(option.value)}
        />
      ))}
    </ScrollView>
  );
}

export default function HomeScreen() {
  const [query, setQuery] = useState('');
  const [transmission, setTransmission] = useState<Transmission>();
  const [fuel, setFuel] = useState<FuelType>();
  const [maxPrice, setMaxPrice] = useState<string>();
  const [sort, setSort] = useState<SortOrder>('price_asc');
  const debouncedQuery = useDebouncedValue(query.trim(), 400);

  const filters = useMemo<SearchFilters>(
    () => ({ q: debouncedQuery || undefined, transmission, fuel_type: fuel, max_daily_rate: maxPrice, sort }),
    [debouncedQuery, transmission, fuel, maxPrice, sort],
  );
  const search = useVehicleSearch(filters);
  const filtered = Boolean(debouncedQuery || transmission || fuel || maxPrice);

  const clearFilters = () => {
    setQuery('');
    setTransmission(undefined);
    setFuel(undefined);
    setMaxPrice(undefined);
  };

  let body;
  if (search.status === 'loading') {
    body = <LoadingState message="Finding cars near you…" />;
  } else if (search.status === 'error') {
    body = (
      <ErrorState
        message={search.error?.message ?? "We couldn't load vehicles."}
        onAction={search.refresh}
      />
    );
  } else {
    body = (
      <FlatList
        data={search.items}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <VehicleCard vehicle={item} />}
        contentContainerClassName="flex-grow p-5"
        keyboardShouldPersistTaps="handled"
        onEndReached={search.loadMore}
        onEndReachedThreshold={0.5}
        refreshControl={<RefreshControl refreshing={search.refreshing} onRefresh={search.refresh} />}
        ListHeaderComponent={
          search.total > 0 ? (
            <Text className="mb-3 text-sm text-ink-muted">
              {search.total} {search.total === 1 ? 'car' : 'cars'} available
            </Text>
          ) : null
        }
        ListFooterComponent={
          search.loadingMore ? <ActivityIndicator color={COLORS.brand} className="py-4" /> : null
        }
        ListEmptyComponent={
          filtered ? (
            <EmptyState
              title="No matching cars"
              message="Try a different search or fewer filters."
              actionLabel="Clear filters"
              onAction={clearFilters}
            />
          ) : (
            <EmptyState title="No cars available yet" message="Check back soon for new listings." />
          )
        }
      />
    );
  }

  return (
    <View className="flex-1 bg-surface-muted">
      <View className="border-b border-surface-border bg-white px-5 pb-3 pt-3">
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
        <ChipRow options={TRANSMISSIONS} selected={transmission} onSelect={setTransmission} />
        <ChipRow options={FUELS} selected={fuel} onSelect={setFuel} />
        <ChipRow options={MAX_PRICES} selected={maxPrice} onSelect={setMaxPrice} />
        <ChipRow options={SORTS} selected={sort} onSelect={(value) => setSort(value ?? 'price_asc')} />
      </View>
      {body}
    </View>
  );
}
