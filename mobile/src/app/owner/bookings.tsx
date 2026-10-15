import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { BookingStatusBadge } from '@/components/booking-status-badge';
import { Chip } from '@/components/ui/chip';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { useAsync } from '@/hooks/use-async';
import { useReloadOnFocus } from '@/hooks/use-reload-on-focus';
import { formatDateTime } from '@/lib/dates';
import { formatZar } from '@/lib/format';
import { DELIVERY_STATUS } from '@/lib/labels';
import { listOwnerBookings } from '@/services/owner';
import type { OwnerBooking, OwnerBookingScope } from '@/types/owner';

const SCOPES: { value: OwnerBookingScope; label: string }[] = [
  { value: 'upcoming', label: 'Upcoming' },
  { value: 'active', label: 'On the road' },
  { value: 'past', label: 'Past' },
];

const EMPTY: Record<OwnerBookingScope, string> = {
  upcoming: 'Paid bookings of your cars appear here.',
  active: 'No car is on its way or rented out right now.',
  past: 'Completed and cancelled bookings appear here.',
  all: 'No bookings yet.',
};

function BookingRow({ booking }: { booking: OwnerBooking }) {
  const deliveryId = booking.delivery_id;
  return (
    <Pressable
      accessibilityRole="button"
      disabled={!deliveryId}
      onPress={() => deliveryId && router.push({ pathname: '/deliveries/[id]', params: { id: deliveryId } })}
      className="mb-3 rounded-2xl border border-surface-border bg-white p-4 active:opacity-80">
      <View className="flex-row items-start justify-between">
        <Text className="flex-1 pr-2 text-lg font-semibold text-ink">
          {booking.vehicle.make} {booking.vehicle.model}
        </Text>
        <BookingStatusBadge status={booking.status} />
      </View>
      <Text className="mt-1 text-sm text-ink-muted">
        {formatDateTime(booking.start_at)} → {formatDateTime(booking.end_at)}
      </Text>
      <Text className="mt-1 text-sm text-ink-muted">
        {booking.renter_first_name} · Ref {booking.reference}
        {booking.delivery_status && booking.status !== 'CANCELLED' ? ` · ${DELIVERY_STATUS[booking.delivery_status]}` : ''}
      </Text>
      <Text className="mt-2 text-base font-semibold text-ink">{formatZar(booking.total_amount)}</Text>
    </Pressable>
  );
}

export default function OwnerBookingsScreen() {
  const params = useLocalSearchParams<{ scope?: OwnerBookingScope }>();
  const [scope, setScope] = useState<OwnerBookingScope>(
    SCOPES.some((s) => s.value === params.scope) ? params.scope! : 'upcoming',
  );
  const load = useCallback(() => listOwnerBookings(scope), [scope]);
  const bookings = useAsync(load);
  useReloadOnFocus(bookings.reload);

  return (
    <View className="flex-1 bg-surface-muted">
      <Stack.Screen options={{ title: 'Bookings of my cars' }} />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} className="max-h-16 grow-0" contentContainerClassName="px-5 py-3">
        {SCOPES.map((s) => (
          <Chip key={s.value} label={s.label} selected={scope === s.value} onPress={() => setScope(s.value)} />
        ))}
      </ScrollView>
      {bookings.status === 'loading' ? (
        <LoadingState />
      ) : bookings.status === 'error' ? (
        <ErrorState message={bookings.error.message} onAction={bookings.reload} />
      ) : (
        <FlatList
          data={bookings.data}
          keyExtractor={(b) => b.id}
          renderItem={({ item }) => <BookingRow booking={item} />}
          contentContainerClassName="flex-grow px-5 pb-5"
          refreshControl={<RefreshControl refreshing={false} onRefresh={bookings.reload} />}
          ListEmptyComponent={<EmptyState icon="calendar-outline" title="Nothing here" message={EMPTY[scope]} />}
        />
      )}
    </View>
  );
}
