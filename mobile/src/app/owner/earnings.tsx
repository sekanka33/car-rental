import Ionicons from '@expo/vector-icons/Ionicons';
import { Stack } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { SectionTitle } from '@/components/dashboard';
import { BookingStatusBadge } from '@/components/booking-status-badge';
import { ErrorState, LoadingState } from '@/components/ui/state-views';
import { COLORS } from '@/constants/brand';
import { useAsync } from '@/hooks/use-async';
import { formatDateRange, formatZar } from '@/lib/format';
import { monthLabel } from '@/lib/labels';
import { saToday } from '@/lib/dates';
import { barShares } from '@/lib/owner';
import { getEarnings } from '@/services/owner';
import type { Earnings } from '@/types/owner';

function MonthChart({ data }: { data: Earnings }) {
  const shares = barShares(data.months);
  if (data.months.length === 0) return null;
  return (
    <View
      className="mt-4 h-40 flex-row items-end gap-2 rounded-2xl border border-surface-border bg-white p-4"
      accessibilityLabel={`Net per month: ${data.months.map((m) => `${monthLabel(m.month)} ${formatZar(m.net)}`).join(', ')}`}>
      {data.months.map((m, i) => (
        <View key={m.month} className="flex-1 items-center justify-end">
          <View className="w-full rounded-t-md bg-brand-500" style={{ height: `${Math.max(shares[i] * 100, 2)}%` }} />
          <Text className="mt-1 text-xs text-ink-muted">{monthLabel(m.month)}</Text>
        </View>
      ))}
    </View>
  );
}

function EarningsView({ data, year, setYear, reload }: { data: Earnings; year: number; setYear: (y: number) => void; reload: () => void }) {
  const thisYear = Number(saToday().slice(0, 4));
  return (
    <ScrollView className="flex-1 bg-surface-muted" contentContainerClassName="p-5 pb-10" refreshControl={<RefreshControl refreshing={false} onRefresh={reload} />}>
      <View className="flex-row items-center justify-between">
        <Pressable accessibilityRole="button" accessibilityLabel="Previous year" onPress={() => setYear(year - 1)} className="p-2">
          <Ionicons name="chevron-back" size={22} color={COLORS.brand} />
        </Pressable>
        <Text className="text-lg font-semibold text-ink">{year}</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Next year"
          disabled={year >= thisYear + 1}
          onPress={() => setYear(year + 1)}
          className={`p-2 ${year >= thisYear + 1 ? 'opacity-30' : ''}`}>
          <Ionicons name="chevron-forward" size={22} color={COLORS.brand} />
        </Pressable>
      </View>

      <View className="mt-2 rounded-2xl bg-brand-500 p-5">
        <Text className="text-sm text-white/80">Net collected in {year}</Text>
        <Text className="mt-1 text-3xl font-bold text-white">{formatZar(data.net)}</Text>
        <Text className="mt-1 text-sm text-white/80">
          {formatZar(data.collected)} paid · {formatZar(data.refunded)} refunded
        </Text>
      </View>
      <Text className="mt-3 text-sm text-ink-muted">{data.basis}</Text>

      <MonthChart data={data} />

      <SectionTitle title="Per month" />
      {data.months.length === 0 ? <Text className="text-base text-ink-muted">No paid bookings started in {year}.</Text> : null}
      {data.months.map((m) => (
        <View key={m.month} className="flex-row justify-between border-b border-surface-border py-2.5">
          <Text className="text-base text-ink">
            {monthLabel(m.month)} · {m.bookings} {m.bookings === 1 ? 'booking' : 'bookings'}
          </Text>
          <Text className="text-base font-semibold text-ink">{formatZar(m.net)}</Text>
        </View>
      ))}

      {data.bookings.length > 0 ? <SectionTitle title="Per booking" /> : null}
      {data.bookings.map((b) => (
        <View key={b.booking_id} className="mb-2 rounded-2xl border border-surface-border bg-white p-4">
          <View className="flex-row items-start justify-between">
            <Text className="flex-1 pr-2 text-base font-semibold text-ink">{b.vehicle}</Text>
            <BookingStatusBadge status={b.status} />
          </View>
          <Text className="mt-1 text-sm text-ink-muted">
            {formatDateRange(b.start_at, b.end_at)} · Ref {b.reference}
          </Text>
          <View className="mt-2 flex-row justify-between">
            <Text className="text-sm text-ink-muted">
              {formatZar(b.collected)}
              {b.refunded !== '0.00' ? ` − ${formatZar(b.refunded)} refunded` : ''}
            </Text>
            <Text className="text-base font-semibold text-ink">{formatZar(b.net)}</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

export default function EarningsScreen() {
  const [year, setYear] = useState(() => Number(saToday().slice(0, 4)));
  const load = useCallback(() => getEarnings(year), [year]);
  const earnings = useAsync(load);
  return (
    <>
      <Stack.Screen options={{ title: 'Earnings' }} />
      {earnings.status === 'loading' ? (
        <LoadingState />
      ) : earnings.status === 'error' ? (
        <ErrorState message={earnings.error.message} onAction={earnings.reload} />
      ) : (
        <EarningsView data={earnings.data} year={year} setYear={setYear} reload={earnings.reload} />
      )}
    </>
  );
}
