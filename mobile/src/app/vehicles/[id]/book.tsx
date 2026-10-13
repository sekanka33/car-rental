import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { SignInPrompt } from '@/components/sign-in-prompt';
import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { TextField } from '@/components/ui/text-field';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { ApiError } from '@/lib/api';
import { addDays, dayLabel, formatDateTime, saIso, saToday } from '@/lib/dates';
import { describeReason } from '@/lib/eligibility';
import { formatZar } from '@/lib/format';
import { createBooking, getQuote } from '@/services/bookings';
import { getVehicle } from '@/services/vehicles';

const HOURS = [8, 10, 12, 14, 16];
const DURATIONS = [1, 2, 3, 5, 7, 10, 14, 21, 30];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View className="mt-6">
      <Text className="mb-2 text-base font-semibold text-ink">{title}</Text>
      {children}
    </View>
  );
}

function Line({ label, amount, strong = false }: { label: string; amount: string; strong?: boolean }) {
  return (
    <View className="flex-row justify-between py-1">
      <Text className={`text-base ${strong ? 'font-semibold text-ink' : 'text-ink-muted'}`}>{label}</Text>
      <Text className={`text-base ${strong ? 'font-bold text-ink' : 'text-ink'}`}>{formatZar(amount)}</Text>
    </View>
  );
}

function BookingForm({ vehicleId }: { vehicleId: string }) {
  const days = useMemo(() => {
    const today = saToday();
    return Array.from({ length: 30 }, (_, i) => addDays(today, i + 1));
  }, []);
  const [date, setDate] = useState(days[0]);
  const [hour, setHour] = useState(10);
  const [duration, setDuration] = useState(3);
  const [address, setAddress] = useState('');
  const [addressError, setAddressError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const startAt = saIso(date, hour);
  const endAt = saIso(addDays(date, duration), hour);
  const loadVehicle = useCallback(() => getVehicle(vehicleId), [vehicleId]);
  const loadQuote = useCallback(() => getQuote(vehicleId, startAt, endAt), [vehicleId, startAt, endAt]);
  const vehicle = useAsync(loadVehicle);
  const quote = useAsync(loadQuote);

  const submit = async () => {
    if (address.trim().length < 5) {
      setAddressError('Enter the delivery address.');
      return;
    }
    setAddressError(null);
    setSubmitError(null);
    setSubmitting(true);
    try {
      const booking = await createBooking({
        vehicle_id: vehicleId,
        start_at: startAt,
        end_at: endAt,
        delivery_address: address.trim(),
      });
      router.replace({ pathname: '/bookings/[id]', params: { id: booking.id } });
    } catch (error) {
      setSubmitError(error instanceof ApiError ? error : new ApiError('Could not create the booking.', 0, 'unknown'));
      quote.reload();
    } finally {
      setSubmitting(false);
    }
  };

  if (vehicle.status === 'loading') return <LoadingState />;
  if (vehicle.status === 'error') return <ErrorState message={vehicle.error.message} onAction={vehicle.reload} />;

  const unavailable = quote.status === 'success' && !quote.data.available;
  return (
    <Screen scroll>
      <Text className="text-2xl font-bold text-ink">
        {vehicle.data.make} {vehicle.data.model}
      </Text>
      <Text className="text-base text-ink-muted">
        {vehicle.data.city}, {vehicle.data.province}
      </Text>

      <Section title="Start date">
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {days.map((day) => (
            <Chip key={day} label={dayLabel(day)} selected={day === date} onPress={() => setDate(day)} />
          ))}
        </ScrollView>
      </Section>
      <Section title="Delivery time">
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {HOURS.map((h) => (
            <Chip key={h} label={`${String(h).padStart(2, '0')}:00`} selected={h === hour} onPress={() => setHour(h)} />
          ))}
        </ScrollView>
      </Section>
      <Section title="Rental length">
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {DURATIONS.map((d) => (
            <Chip key={d} label={d === 1 ? '1 day' : `${d} days`} selected={d === duration} onPress={() => setDuration(d)} />
          ))}
        </ScrollView>
      </Section>
      <Text className="mt-3 text-sm text-ink-muted">
        {formatDateTime(startAt)} → {formatDateTime(endAt)}
      </Text>

      <Section title="Price">
        <View className="rounded-xl border border-surface-border p-4">
          {quote.status === 'loading' ? (
            <Text className="text-base text-ink-muted">Calculating…</Text>
          ) : quote.status === 'error' ? (
            <Text className="text-base text-danger">{quote.error.message}</Text>
          ) : (
            <>
              <Line
                label={`${formatZar(quote.data.daily_rate)} × ${quote.data.rental_days} ${quote.data.rental_days === 1 ? 'day' : 'days'}`}
                amount={quote.data.rental_amount}
              />
              <Line label="Delivery fee" amount={quote.data.delivery_fee} />
              <Line label="Total" amount={quote.data.total_amount} strong />
              <Text className="mt-2 text-sm text-ink-muted">
                Plus a refundable deposit of {formatZar(quote.data.deposit_amount)}. ZAR, VAT inclusive.
              </Text>
            </>
          )}
        </View>
        {unavailable ? (
          <Text className="mt-2 text-base text-danger">Not available for these dates. Try other dates.</Text>
        ) : null}
      </Section>

      <Section title="Delivery address">
        <TextField
          label="Where should we bring the car?"
          value={address}
          onChangeText={setAddress}
          error={addressError}
          placeholder="Street, suburb, city"
          autoComplete="street-address"
        />
      </Section>

      {submitError ? (
        <View className="mt-2">
          <Notice tone="danger" message={submitError.message} />
          {submitError.details.map((detail) =>
            detail.reason ? (
              <Text key={detail.reason} className="mb-1 text-base text-ink">
                • {describeReason(detail.reason)}
              </Text>
            ) : null,
          )}
        </View>
      ) : null}

      <Button
        label="Reserve this car"
        onPress={submit}
        loading={submitting}
        disabled={quote.status !== 'success' || unavailable}
        className="mt-6"
      />
      <Text className="mt-2 text-center text-sm text-ink-muted">
        The car is held for you for 15 minutes while you pay on the next screen.
      </Text>
    </Screen>
  );
}

export default function BookVehicleScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { state } = useAuth();
  if (state.status === 'loading') return <LoadingState />;
  if (state.status === 'signedOut') return <SignInPrompt message="Log in to book this car." />;
  if (!state.user.roles.includes('RENTER')) {
    return <EmptyState title="Renter accounts only" message="Log in with a renter account to book." />;
  }
  return <BookingForm vehicleId={id} />;
}
