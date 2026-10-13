import * as Linking from 'expo-linking';
import { Stack, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useCallback, useEffect, useState } from 'react';
import { Text, View } from 'react-native';

import { BookingStatusBadge } from '@/components/booking-status-badge';
import { SignInPrompt } from '@/components/sign-in-prompt';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { VehiclePhoto } from '@/components/vehicle-photo';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/dates';
import { formatZar } from '@/lib/format';
import { cancelBooking, getBooking } from '@/services/bookings';
import { listBookingPayments, refreshPayment, startPayment } from '@/services/payments';
import type { Booking } from '@/types/booking';
import type { Payment } from '@/types/payment';

/** The current time, refreshed every 15 seconds (drives the hold countdown). */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View className="flex-row justify-between py-1.5">
      <Text className="text-base text-ink-muted">{label}</Text>
      <Text className="ml-4 flex-1 text-right text-base text-ink">{value}</Text>
    </View>
  );
}

const PAYMENT_LABELS: Record<Payment['status'], string> = {
  PENDING: 'Not completed yet',
  SUCCEEDED: 'Paid',
  FAILED: 'Not completed',
  CANCELLED: 'Cancelled',
  REFUND_PENDING: 'Being refunded',
  REFUNDED: 'Refunded',
  PARTIALLY_REFUNDED: 'Partly refunded',
};

function PaymentHistory({ payments }: { payments: Payment[] }) {
  // Abandoned checkouts are noise for the renter; show money that moved (or was attempted).
  const shown = payments.filter((p) => p.status !== 'PENDING');
  if (shown.length === 0) return null;
  return (
    <>
      <Text className="mb-1 mt-6 text-lg font-semibold text-ink">Payments</Text>
      {shown.map((payment) => (
        <View key={payment.id}>
          <Row
            label={`${PAYMENT_LABELS[payment.status]} · ${payment.reference}`}
            value={formatZar(payment.amount)}
          />
          {payment.paid_at ? <Row label="Paid on" value={formatDateTime(payment.paid_at)} /> : null}
          {payment.refunds.map((refund) => (
            <Row
              key={refund.id}
              label={refund.status === 'PROCESSED' ? 'Refunded' : refund.status === 'FAILED' ? 'Refund failed (we are on it)' : 'Refund in progress'}
              value={`− ${formatZar(refund.amount)}`}
            />
          ))}
        </View>
      ))}
    </>
  );
}

/** Opens checkout, then asks the backend to verify the payment. Never trusts the browser result. */
async function payForBooking(bookingId: string): Promise<Payment> {
  const payment = await startPayment(bookingId);
  if (payment.checkout_url) {
    await WebBrowser.openAuthSessionAsync(payment.checkout_url, Linking.createURL('payments/return'));
  }
  return refreshPayment(payment.id);
}

function BookingDetails({
  booking,
  payments,
  onChanged,
}: {
  booking: Booking;
  payments: Payment[];
  onChanged: () => void;
}) {
  const now = useNow();
  const minutesLeft =
    booking.status === 'PENDING_PAYMENT' && booking.hold_expires_at
      ? Math.max(0, Math.ceil((new Date(booking.hold_expires_at).getTime() - now) / 60_000))
      : null;
  const [confirming, setConfirming] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const cancellable =
    booking.status === 'PENDING_PAYMENT' ||
    (booking.status === 'CONFIRMED' && new Date(booking.start_at).getTime() > now);

  const cancel = async () => {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setCancelling(true);
    try {
      await cancelBooking(booking.id, 'Cancelled in the app');
      onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not cancel the booking.');
    } finally {
      setCancelling(false);
      setConfirming(false);
    }
  };

  const pay = async () => {
    setPaying(true);
    setError(null);
    setInfo(null);
    try {
      const payment = await payForBooking(booking.id);
      // Reloading remounts this screen, so only reload when the booking actually changed.
      if (payment.status === 'FAILED') {
        setError(payment.failure_reason ?? 'The payment was not completed. You were not charged.');
      } else if (payment.status === 'PENDING') {
        setInfo('We have not had confirmation from the payment provider yet. If you paid, this booking updates shortly.');
      } else {
        onChanged();
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start the payment.');
    } finally {
      setPaying(false);
    }
  };

  return (
    <Screen scroll>
      <Stack.Screen options={{ title: `Booking ${booking.reference}` }} />
      <VehiclePhoto url={booking.vehicle.primary_photo_url} className="h-40" />
      <View className="mt-4 flex-row items-start justify-between">
        <Text className="flex-1 pr-2 text-2xl font-bold text-ink">
          {booking.vehicle.make} {booking.vehicle.model}
        </Text>
        <BookingStatusBadge status={booking.status} />
      </View>
      <Text className="text-base text-ink-muted">Reference {booking.reference}</Text>

      {booking.status === 'PENDING_PAYMENT' && minutesLeft !== null ? (
        <View className="mt-4">
          <Notice
            tone="info"
            message={`The car is held for you for ${minutesLeft} more ${minutesLeft === 1 ? 'minute' : 'minutes'}. Pay now to confirm it; unpaid holds expire automatically.`}
          />
        </View>
      ) : null}
      {booking.status === 'CANCELLED' && booking.cancellation_reason ? (
        <View className="mt-4">
          <Notice tone="info" message={`Cancelled: ${booking.cancellation_reason}`} />
        </View>
      ) : null}

      <Text className="mb-1 mt-6 text-lg font-semibold text-ink">Trip</Text>
      <Row label="Starts" value={formatDateTime(booking.start_at)} />
      <Row label="Ends" value={formatDateTime(booking.end_at)} />
      {booking.delivery_address ? <Row label="Delivery to" value={booking.delivery_address} /> : null}

      <Text className="mb-1 mt-6 text-lg font-semibold text-ink">Price (agreed at booking)</Text>
      <Row
        label={`${formatZar(booking.price.daily_rate)} × ${booking.price.rental_days} days`}
        value={formatZar(booking.price.rental_amount)}
      />
      <Row label="Delivery fee" value={formatZar(booking.price.delivery_fee)} />
      <Row label="Total" value={formatZar(booking.price.total_amount)} />
      <Row label="Refundable deposit" value={formatZar(booking.price.deposit_amount)} />
      {Number(booking.price.deposit_amount) > 0 ? (
        <Text className="mt-1 text-sm text-ink-muted">The deposit is not charged online; it is arranged at handover.</Text>
      ) : null}

      <PaymentHistory payments={payments} />

      {error ? (
        <View className="mt-4">
          <Notice tone="danger" message={error} />
        </View>
      ) : null}
      {info ? (
        <View className="mt-4">
          <Notice tone="info" message={info} />
        </View>
      ) : null}
      {booking.status === 'PENDING_PAYMENT' && minutesLeft ? (
        <Button
          label={`Pay ${formatZar(booking.price.total_amount)}`}
          loading={paying}
          onPress={pay}
          className="mt-8"
        />
      ) : null}
      {cancellable ? (
        <Button
          label={confirming ? 'Tap again to confirm cancellation' : 'Cancel booking'}
          variant="secondary"
          loading={cancelling}
          onPress={cancel}
          className="mt-4"
        />
      ) : null}
      {cancellable && booking.status === 'CONFIRMED' ? (
        <Text className="mt-2 text-center text-sm text-ink-muted">Cancelling before the trip starts refunds you in full.</Text>
      ) : null}
    </Screen>
  );
}

export default function BookingScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { state } = useAuth();
  const load = useCallback(
    () => Promise.all([getBooking(id), listBookingPayments(id)]).then(([b, p]) => ({ booking: b, payments: p })),
    [id],
  );
  const booking = useAsync(load);

  if (state.status === 'signedOut') return <SignInPrompt message="Log in to see this booking." />;
  if (booking.status === 'loading' || state.status === 'loading') return <LoadingState />;
  if (booking.status === 'error') {
    if (booking.error instanceof ApiError && booking.error.isNotFound) {
      return <EmptyState title="Booking not found" message="It may belong to another account." />;
    }
    return <ErrorState message={booking.error.message} onAction={booking.reload} />;
  }
  return <BookingDetails booking={booking.data.booking} payments={booking.data.payments} onChanged={booking.reload} />;
}
