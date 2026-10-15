import { fireEvent, render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import BookingsScreen from '@/app/(tabs)/bookings';
import PaymentHistoryScreen from '@/app/payments/index';
import VerificationScreen from '@/app/verification';
import { useAuth } from '@/context/auth';
import { listMyBookings } from '@/services/bookings';
import * as customers from '@/services/customers';
import type { Booking } from '@/types/booking';
import type { CustomerProfile, DocumentSubmission } from '@/types/profile';

jest.mock('@/context/auth', () => ({ useAuth: jest.fn() }));
jest.mock('@/services/bookings', () => ({ listMyBookings: jest.fn() }));
jest.mock('@/services/customers', () => ({
  getCustomerProfile: jest.fn(),
  setDateOfBirth: jest.fn(),
  listMyDocuments: jest.fn(),
  submitDocument: jest.fn(),
  listMyPayments: jest.fn(),
}));
jest.mock('@/lib/upload', () => ({
  pickImage: jest.fn(async () => ({ uri: 'file:///id.jpg', name: 'id.jpg', mimeType: 'image/jpeg' })),
  pickDocument: jest.fn(async () => ({ uri: 'file:///id.pdf', name: 'id.pdf', mimeType: 'application/pdf' })),
}));
jest.mock('expo-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => children,
  Stack: { Screen: () => null },
  router: { replace: jest.fn(), push: jest.fn(), back: jest.fn() },
  useFocusEffect: jest.fn(),
}));

const mockRouter = jest.requireMock('expo-router').router as { push: jest.Mock };
const mocked = (fn: unknown) => fn as jest.Mock;
const METRICS = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const wrap = (ui: React.ReactElement) => render(<SafeAreaProvider initialMetrics={METRICS}>{ui}</SafeAreaProvider>);
const renter = { id: 'u1', email: 'a@b.co', full_name: 'Alice Renter', phone_number: null, status: 'ACTIVE', roles: ['RENTER'], email_verified: true, created_at: '' };

function profile(overrides: Partial<CustomerProfile> = {}): CustomerProfile {
  return {
    date_of_birth: '1995-06-15', id_verification_status: 'APPROVED', licence_verification_status: 'APPROVED',
    licence_expiry_date: '2030-01-01', minimum_age: 18, ...overrides,
  };
}

function booking(id: string, status: Booking['status'], overrides: Partial<Booking> = {}): Booking {
  return {
    id, reference: `REF-${id}`, status,
    vehicle: { id: 'v1', make: 'Toyota', model: 'Corolla', year: 2023, city: 'Durban', province: 'KwaZulu-Natal', primary_photo_url: null },
    start_at: '2026-11-20T08:00:00+02:00', end_at: '2026-11-23T08:00:00+02:00',
    hold_expires_at: status === 'PENDING_PAYMENT' ? '2026-10-15T10:15:00+02:00' : null,
    price: { daily_rate: '650.00', rental_days: 3, rental_amount: '1950.00', delivery_fee: '150.00', deposit_amount: '2000.00', total_amount: '2100.00', currency: 'ZAR' },
    delivery_address: '1 Beach Rd', created_at: '', confirmed_at: null, cancelled_at: null, cancellation_reason: null,
    ...overrides,
  };
}

beforeEach(() => {
  mocked(useAuth).mockReturnValue({ state: { status: 'signedIn', user: renter } });
});

describe('renter dashboard', () => {
  it('lists what needs doing, then current, upcoming and past bookings', async () => {
    mocked(listMyBookings).mockResolvedValue([
      booking('hold', 'PENDING_PAYMENT'),
      booking('handed', 'DELIVERED', { start_at: '2026-10-14T08:00:00+02:00' }),
      booking('done', 'COMPLETED', { start_at: '2026-01-10T08:00:00+02:00' }),
    ]);
    mocked(customers.getCustomerProfile).mockResolvedValue(profile());
    await wrap(<BookingsScreen />);

    expect(await screen.findByText('Needs your attention')).toBeTruthy();
    expect(screen.getByText('Pay for Toyota Corolla')).toBeTruthy();
    await fireEvent.press(screen.getByText('Confirm you have the Toyota Corolla'));
    expect(mockRouter.push).toHaveBeenCalledWith({ pathname: '/bookings/[id]', params: { id: 'handed' } });
    for (const title of ['Now', 'Upcoming', 'Past']) expect(screen.getByText(title)).toBeTruthy();
    expect(screen.queryByText('Verify your identity')).toBeNull();
  });

  it('asks unverified renters to verify', async () => {
    mocked(listMyBookings).mockResolvedValue([]);
    mocked(customers.getCustomerProfile).mockResolvedValue(profile({ date_of_birth: null, id_verification_status: 'NOT_SUBMITTED' }));
    await wrap(<BookingsScreen />);

    await fireEvent.press(await screen.findByText('Verify your identity'));
    expect(mockRouter.push).toHaveBeenCalledWith('/verification');
    expect(screen.getByText('No bookings yet')).toBeTruthy();
  });

  it('does not nag while documents are under review', async () => {
    mocked(listMyBookings).mockResolvedValue([]);
    mocked(customers.getCustomerProfile).mockResolvedValue(profile({ id_verification_status: 'PENDING' }));
    await wrap(<BookingsScreen />);
    await screen.findByText('No bookings yet');
    expect(screen.queryByText('Verify your identity')).toBeNull();
  });
});

describe('identity verification', () => {
  const rejected: DocumentSubmission = {
    id: 's1', document_type: 'DRIVING_LICENCE', status: 'REJECTED', document_number_masked: '••••••789',
    licence_expiry_date: null, licence_codes: null, review_note: 'The photo is blurry', submitted_at: '2026-10-01T08:00:00Z',
    reviewed_at: '2026-10-02T08:00:00Z', files: [],
  };

  it('needs a date of birth before the ID upload', async () => {
    mocked(customers.getCustomerProfile).mockResolvedValue(profile({ date_of_birth: null, id_verification_status: 'NOT_SUBMITTED' }));
    mocked(customers.listMyDocuments).mockResolvedValue([]);
    await wrap(<VerificationScreen />);

    expect(await screen.findByText('Save your date of birth first.')).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('Date of birth'), '1995-02-30');
    await fireEvent.press(screen.getByText('Save date of birth'));
    expect(screen.getByText('Enter your date of birth as YYYY-MM-DD.')).toBeTruthy();
    await fireEvent.changeText(screen.getByLabelText('Date of birth'), '1995-06-15');
    await fireEvent.press(screen.getByText('Save date of birth'));
    expect(customers.setDateOfBirth).toHaveBeenCalledWith('1995-06-15');
  });

  it('uploads an ID after checking the number', async () => {
    mocked(customers.getCustomerProfile).mockResolvedValue(profile({ id_verification_status: 'NOT_SUBMITTED' }));
    mocked(customers.listMyDocuments).mockResolvedValue([]);
    await wrap(<VerificationScreen />);

    await fireEvent.press((await screen.findAllByText('Upload'))[0]);
    await fireEvent.changeText(screen.getByLabelText('ID number'), '95061512');
    await fireEvent.press(screen.getByText('Submit'));
    expect(screen.getByText('Your SA ID number has 13 digits.')).toBeTruthy();

    await fireEvent.changeText(screen.getByLabelText('ID number'), '9506155800085');
    await fireEvent.press(screen.getByText('Submit'));
    expect(screen.getByText('Add a photo or scan of the front.')).toBeTruthy();

    await fireEvent.press(screen.getAllByText('Take photo')[0]);
    await fireEvent.press(screen.getByText('Submit'));
    expect(customers.submitDocument).toHaveBeenCalledWith(
      expect.objectContaining({ documentType: 'SA_ID', documentNumber: '9506155800085', back: null, licenceExpiryDate: null }),
    );
  });

  it('shows why a document was rejected and lets the renter try again', async () => {
    mocked(customers.getCustomerProfile).mockResolvedValue(profile({ licence_verification_status: 'REJECTED' }));
    mocked(customers.listMyDocuments).mockResolvedValue([rejected]);
    await wrap(<VerificationScreen />);

    expect(await screen.findByText('Reviewer: The photo is blurry')).toBeTruthy();
    expect(screen.getByText('No. ••••••789')).toBeTruthy();
    await fireEvent.press(screen.getByText('Upload again'));
    expect(screen.getByLabelText('Expiry date')).toBeTruthy();
  });
});

describe('payment history', () => {
  it('shows payments with their refunds', async () => {
    mocked(customers.listMyPayments).mockResolvedValue([
      {
        id: 'p1', booking_id: 'b1', reference: 'r1', provider: 'paystack', status: 'PARTIALLY_REFUNDED', amount: '2100.00',
        currency: 'ZAR', checkout_url: null, paid_at: '2026-10-01T08:00:00Z', failure_reason: null, created_at: '2026-10-01T07:59:00Z',
        booking_status: null, booking_reference: 'BK1', vehicle: 'Toyota Corolla',
        refunds: [{ id: 'r1', amount: '500.00', currency: 'ZAR', status: 'PROCESSED', reason: 'x', created_at: '2026-10-02T08:00:00Z', processed_at: '2026-10-02T09:00:00Z' }],
      },
    ]);
    await wrap(<PaymentHistoryScreen />);

    expect(await screen.findByText('Partly refunded')).toBeTruthy();
    expect(screen.getByText('R 2 100.00')).toBeTruthy();
    expect(screen.getByText(/R 500.00 refunded/)).toBeTruthy();
  });
});
