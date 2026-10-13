import { fireEvent, render, screen } from '@testing-library/react-native';

import HomeScreen from '@/app/(tabs)/home';
import { ApiError } from '@/lib/api';
import { searchVehicles } from '@/services/vehicles';

import { vehicle } from './fixtures';

jest.mock('@/services/vehicles', () => ({ searchVehicles: jest.fn(), PAGE_SIZE: 20 }));
jest.mock('expo-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => children,
}));

const mockSearch = searchVehicles as jest.MockedFunction<typeof searchVehicles>;

function page(items = [vehicle()], total = items.length) {
  return { items, total, limit: 20, offset: 0 };
}

it('shows vehicles and official prices from the API', async () => {
  mockSearch.mockResolvedValue(
    page([vehicle(), vehicle({ id: 'v2', make: 'Ford', model: 'Ranger XLT', price: { ...vehicle().price, daily_rate: '1450.00' } })]),
  );

  await render(<HomeScreen />);

  expect(await screen.findByText('Toyota Corolla Cross')).toBeTruthy();
  expect(screen.getByText('Ford Ranger XLT')).toBeTruthy();
  expect(screen.getByText('R 1 450.00')).toBeTruthy();
  expect(screen.getByText('2 cars available')).toBeTruthy();
  expect(mockSearch).toHaveBeenCalledWith({ sort: 'price_asc' });
});

it('sends filters to the backend', async () => {
  mockSearch.mockResolvedValue(page());
  await render(<HomeScreen />);
  await screen.findByText('Toyota Corolla Cross');

  await fireEvent.press(screen.getByText('Manual'));
  await fireEvent.press(screen.getByText('Diesel'));

  await screen.findByText('Toyota Corolla Cross');
  expect(mockSearch).toHaveBeenLastCalledWith({ transmission: 'MANUAL', fuel_type: 'DIESEL', sort: 'price_asc' });
});

it('shows an empty state', async () => {
  mockSearch.mockResolvedValue(page([], 0));

  await render(<HomeScreen />);

  expect(await screen.findByText('No cars available yet')).toBeTruthy();
});

it('shows API errors and retries', async () => {
  mockSearch.mockRejectedValueOnce(new ApiError('Could not reach the server.', 0, 'network_error'));
  mockSearch.mockResolvedValueOnce(page());

  await render(<HomeScreen />);

  expect(await screen.findByText('Could not reach the server.')).toBeTruthy();
  await fireEvent.press(screen.getByText('Try again'));
  expect(await screen.findByText('Toyota Corolla Cross')).toBeTruthy();
});
