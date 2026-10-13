import { router, Stack, useLocalSearchParams } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { useCallback } from 'react';

import { SignInPrompt } from '@/components/sign-in-prompt';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { refreshPayment } from '@/services/payments';

// On the web, checkout runs in a popup that the provider sends back here. This hands the
// result to the window that opened it and closes the popup; elsewhere it does nothing.
WebBrowser.maybeCompleteAuthSession();

const MESSAGES = {
  SUCCEEDED: { title: 'Payment received', message: 'Your booking is confirmed.', icon: 'checkmark-circle-outline' },
  PENDING: {
    title: 'Waiting for confirmation',
    message: 'We have not had confirmation from the payment provider yet. Your booking updates as soon as we do.',
    icon: 'time-outline',
  },
  FAILED: { title: 'Payment not completed', message: 'You were not charged. You can try again from the booking.', icon: 'close-circle-outline' },
  OTHER: {
    title: 'Payment received after the hold ended',
    message: 'We could not confirm the booking, so the full amount is being refunded to you.',
    icon: 'information-circle-outline',
  },
} as const;

/** Landing page after checkout (`?payment_id=`). The backend verifies the payment itself. */
function PaymentResult({ paymentId }: { paymentId: string }) {
  const load = useCallback(() => refreshPayment(paymentId), [paymentId]);
  const payment = useAsync(load);

  if (payment.status === 'loading') return <LoadingState message="Checking your payment…" />;
  if (payment.status === 'error') return <ErrorState message={payment.error.message} onAction={payment.reload} />;
  const { status, booking_id: bookingId } = payment.data;
  const copy = status === 'SUCCEEDED' || status === 'PENDING' || status === 'FAILED' ? MESSAGES[status] : MESSAGES.OTHER;
  return (
    <EmptyState
      icon={copy.icon}
      title={copy.title}
      message={copy.message}
      actionLabel="View booking"
      onAction={() => router.replace({ pathname: '/bookings/[id]', params: { id: bookingId } })}
    />
  );
}

export default function PaymentReturnScreen() {
  const { payment_id: paymentId } = useLocalSearchParams<{ payment_id?: string }>();
  const { state } = useAuth();
  return (
    <>
      <Stack.Screen options={{ title: 'Payment' }} />
      {state.status === 'loading' ? (
        <LoadingState />
      ) : state.status === 'signedOut' ? (
        <SignInPrompt message="Log in to see your payment." />
      ) : paymentId ? (
        <PaymentResult paymentId={paymentId} />
      ) : (
        <EmptyState title="No payment to show" message="Open your booking to see its payment status." />
      )}
    </>
  );
}
