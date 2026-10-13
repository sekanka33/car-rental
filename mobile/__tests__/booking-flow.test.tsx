import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import BookingsScreen from '@/app/(tabs)/bookings';
import BookingScreen from '@/app/bookings/[id]';
import BookVehicleScreen from '@/app/vehicles/[id]/book';
import { useAuth } from '@/context/auth';
import { ApiError } from '@/lib/api';
import { cancelBooking, createBooking, getBooking, getQuote, listMyBookings } from '@/services/bookings';
import { listBookingPayments, refreshPayment, startPayment } from '@/services/payments';
import { getVehicle } from '@/services/vehicles';
import type { Booking } from '@/types/booking';
import type { Payment } from '@/types/payment';

import { vehicleDetail } from './fixtures';

jest.mock('@/context/auth', () => ({ useAuth: jest.fn() }));
jest.mock('@/services/vehicles', () => ({ getVehicle: jest.fn() }));
jest.mock('@/services/bookings', () => ({
  getQuote: jest.fn(),
  createBooking: jest.fn(),
  listMyBookings: jest.fn(),
  getBooking: jest.fn(),
  cancelBooking: jest.fn(),
}));
jest.mock('@/services/payments', () => ({
  startPayment: jest.fn(),
  refreshPayment: jest.fn(),
  listBookingPayments: jest.fn(),
}));
jest.mock('expo-web-browser', () => ({
  openAuthSessionAsync: jest.fn(async () => ({ type: 'success' })),
  maybeCompleteAuthSession: jest.fn(),
}));
jest.mock('expo-linking', () => ({ createURL: (path: string) => `carrental://${path}` }));
const mockBrowser = jest.requireMock('expo-web-browser') as { openAuthSessionAsync: jest.Mock };
// jest.mock factories run before this file's own variables exist, so the router mock
// is created inside the factory and read back through the mocked module.
jest.mock('expo-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => children,
  Stack: { Screen: () => null },
  router: { replace: jest.fn(), push: jest.fn(), back: jest.fn() },
  useLocalSearchParams: () => ({ id: 'v1' }),
}));
const mockRouter = jest.requireMock('expo-router').router as { replace: jest.Mock };

const METRICS = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const wrap = (ui: React.ReactElement) => render(<SafeAreaProvider initialMetrics={METRICS}>{ui}</SafeAreaProvider>);

const renter = { id: 'u1', email: 'a@b.co', full_name: 'Alice Renter', phone_number: null, status: 'ACTIVE', roles: ['RENTER'], email_verified: true, created_at: '' };
const signedIn = { state: { status: 'signedIn', user: renter } };
const QUOTE = {
  available: true, rental_days: 3, daily_rate: '750.00', rental_amount: '2250.00',
  delivery_fee: '150.00', deposit_amount: '2000.00', total_amount: '2400.00', currency: 'ZAR' as const,
};

function booking(overrides: Partial<Booking> = {}): Booking {
  return {
    id: 'b1', reference: 'BKABCD2345', status: 'PENDING_PAYMENT',
    vehicle: { id: 'v1', make: 'Toyota', model: 'Corolla Cross', year: 2023, city: 'Johannesburg', province: 'Gauteng', primary_photo_url: null },
    start_at: '2026-10-20T08:00:00+02:00', end_at: '2026-10-23T08:00:00+02:00',
    hold_expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
    price: { ...QUOTE, currency: 'ZAR' },
    delivery_address: '12 Long Street', created_at: '', confirmed_at: null, cancelled_at: null, cancellation_reason: null,
    ...overrides,
  };
}

function payment(overrides: Partial<Payment> = {}): Payment {
  return {
    id: 'p1', booking_id: 'b1', reference: 'PAYABC', provider: 'paystack', status: 'PENDING',
    amount: '2400.00', currency: 'ZAR', checkout_url: 'https://checkout.test/PAYABC', paid_at: null,
    failure_reason: null, created_at: '', refunds: [], booking_status: null,
    ...overrides,
  };
}

beforeEach(() => {
  (listBookingPayments as jest.Mock).mockResolvedValue([]);
  (useAuth as jest.Mock).mockReturnValue(signedIn);
  (getVehicle as jest.Mock).mockResolvedValue(vehicleDetail());
  (getQuote as jest.Mock).mockResolvedValue(QUOTE);
});

describe('booking a car', () => {
  it('quotes the selected period from the backend', async () => {
    await wrap(<BookVehicleScreen />);

    expect(await screen.findByText('R 2 400.00')).toBeTruthy();
    const [vehicleId, start, end] = (getQuote as jest.Mock).mock.calls.at(-1);
    expect(vehicleId).toBe('v1');
    expect(start).toMatch(/T10:00:00\+02:00$/);
    expect(new Date(end).getTime() - new Date(start).getTime()).toBe(3 * 24 * 3600 * 1000);

    await fireEvent.press(screen.getByText('7 days'));
    await fireEvent.press(screen.getByText('14:00'));
    const [, start2, end2] = (getQuote as jest.Mock).mock.calls.at(-1);
    expect(start2).toMatch(/T14:00:00\+02:00$/);
    expect(new Date(end2).getTime() - new Date(start2).getTime()).toBe(7 * 24 * 3600 * 1000);
  });

  it('requires a delivery address, then creates the booking and opens it', async () => {
    (createBooking as jest.Mock).mockResolvedValue(booking());
    await wrap(<BookVehicleScreen />);
    await screen.findByText('R 2 400.00');

    await fireEvent.press(screen.getByText('Reserve this car'));
    expect(screen.getByText('Enter the delivery address.')).toBeTruthy();
    expect(createBooking).not.toHaveBeenCalled();

    await fireEvent.changeText(screen.getByLabelText('Where should we bring the car?'), '12 Long Street, Cape Town');
    await fireEvent.press(screen.getByText('Reserve this car'));

    const input = (createBooking as jest.Mock).mock.calls[0][0];
    expect(input).toEqual({
      vehicle_id: 'v1', start_at: expect.stringMatching(/\+02:00$/), end_at: expect.any(String),
      delivery_address: '12 Long Street, Cape Town',
    });
    expect(Object.keys(input)).not.toContain('total_amount'); // the price is never sent
    await waitFor(() =>
      expect(mockRouter.replace).toHaveBeenCalledWith({ pathname: '/bookings/[id]', params: { id: 'b1' } }),
    );
  });

  it('explains why an ineligible renter cannot book', async () => {
    (createBooking as jest.Mock).mockRejectedValue(
      new ApiError('You cannot book yet.', 403, 'renter_not_eligible', [{ reason: 'ID_NOT_APPROVED' }, { reason: 'LICENCE_NOT_APPROVED' }]),
    );
    await wrap(<BookVehicleScreen />);
    await screen.findByText('R 2 400.00');
    await fireEvent.changeText(screen.getByLabelText('Where should we bring the car?'), '12 Long Street');

    await fireEvent.press(screen.getByText('Reserve this car'));

    expect(await screen.findByText('• Your South African ID must be verified.')).toBeTruthy();
    expect(screen.getByText('• Your driving licence must be verified.')).toBeTruthy();
  });

  it('disables booking when the car is not available', async () => {
    (getQuote as jest.Mock).mockResolvedValue({ ...QUOTE, available: false });
    await wrap(<BookVehicleScreen />);

    expect(await screen.findByText('Not available for these dates. Try other dates.')).toBeTruthy();
  });

  it('asks signed-out visitors to log in', async () => {
    (useAuth as jest.Mock).mockReturnValue({ state: { status: 'signedOut', user: null } });
    await wrap(<BookVehicleScreen />);

    expect(screen.getByText('Log in to book this car.')).toBeTruthy();
  });
});

describe('my bookings', () => {
  it('lists bookings with status and total', async () => {
    (listMyBookings as jest.Mock).mockResolvedValue([booking(), booking({ id: 'b2', reference: 'BKZZZZ2345', status: 'CANCELLED' })]);
    await wrap(<BookingsScreen />);

    expect(await screen.findByText('BKABCD2345', { exact: false })).toBeTruthy();
    expect(screen.getByText('Awaiting payment')).toBeTruthy();
    expect(screen.getByText('Cancelled')).toBeTruthy();
    expect(screen.getAllByText('R 2 400.00')).toHaveLength(2);
  });

  it('shows a hold countdown and cancels after confirmation', async () => {
    (getBooking as jest.Mock).mockResolvedValueOnce(booking()).mockResolvedValueOnce(booking({ status: 'CANCELLED', cancellation_reason: 'Cancelled in the app' }));
    (cancelBooking as jest.Mock).mockResolvedValue(booking({ status: 'CANCELLED' }));
    await wrap(<BookingScreen />);

    expect(await screen.findByText(/held for you for 10 more minutes/)).toBeTruthy();
    await fireEvent.press(screen.getByText('Cancel booking'));
    expect(cancelBooking).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByText('Tap again to confirm cancellation'));

    expect(cancelBooking).toHaveBeenCalledWith('b1', 'Cancelled in the app');
    expect(await screen.findByText('Cancelled: Cancelled in the app')).toBeTruthy();
  });
});

describe('paying for a booking', () => {
  it('opens checkout and confirms only after the backend verifies the payment', async () => {
    (getBooking as jest.Mock)
      .mockResolvedValueOnce(booking())
      .mockResolvedValueOnce(booking({ status: 'CONFIRMED', hold_expires_at: null }));
    (listBookingPayments as jest.Mock)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([payment({ status: 'SUCCEEDED', checkout_url: null, paid_at: '2026-10-13T12:00:00+02:00' })]);
    (startPayment as jest.Mock).mockResolvedValue(payment());
    (refreshPayment as jest.Mock).mockResolvedValue(payment({ status: 'SUCCEEDED', checkout_url: null }));
    await wrap(<BookingScreen />);

    await fireEvent.press(await screen.findByText('Pay R 2 400.00'));

    expect(startPayment).toHaveBeenCalledWith('b1');
    expect(mockBrowser.openAuthSessionAsync).toHaveBeenCalledWith(
      'https://checkout.test/PAYABC',
      'carrental://payments/return',
    );
    expect(refreshPayment).toHaveBeenCalledWith('p1');
    expect(await screen.findByText('Confirmed')).toBeTruthy();
    expect(screen.getByText('Paid · PAYABC')).toBeTruthy();
    expect(screen.queryByText(/^Pay R/)).toBeNull();
  });

  it('explains a declined payment and lets the renter try again', async () => {
    (getBooking as jest.Mock).mockResolvedValue(booking());
    (startPayment as jest.Mock).mockResolvedValue(payment());
    (refreshPayment as jest.Mock).mockResolvedValue(
      payment({ status: 'FAILED', checkout_url: null, failure_reason: 'Declined' }),
    );
    await wrap(<BookingScreen />);

    await fireEvent.press(await screen.findByText('Pay R 2 400.00'));

    expect(await screen.findByText('Declined')).toBeTruthy();
    expect(await screen.findByText('Pay R 2 400.00')).toBeTruthy();
  });

  it('does not offer payment once the hold has expired', async () => {
    (getBooking as jest.Mock).mockResolvedValue(booking({ hold_expires_at: new Date(Date.now() - 60_000).toISOString() }));
    await wrap(<BookingScreen />);

    expect(await screen.findByText(/held for you for 0 more minutes/)).toBeTruthy();
    expect(screen.queryByText(/^Pay R/)).toBeNull();
  });

  it('shows refunds on a cancelled paid booking', async () => {
    (getBooking as jest.Mock).mockResolvedValue(booking({ status: 'CANCELLED', hold_expires_at: null }));
    (listBookingPayments as jest.Mock).mockResolvedValue([
      payment({
        status: 'REFUNDED', checkout_url: null,
        refunds: [{ id: 'r1', amount: '2400.00', currency: 'ZAR', status: 'PROCESSED', reason: 'Booking cancelled', created_at: '', processed_at: '' }],
      }),
    ]);
    await wrap(<BookingScreen />);

    expect(await screen.findByText('Refunded · PAYABC')).toBeTruthy();
    expect(screen.getByText('− R 2 400.00')).toBeTruthy();
  });
});
