import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Pressable, Text } from 'react-native';

import { AuthProvider, useAuth } from '@/context/auth';

const order: string[] = [];
jest.mock('@/lib/push', () => ({
  setUpPush: jest.fn(async () => ({ status: 'registered' })),
  forgetPushToken: jest.fn(async () => void order.push('forget push token')),
}));
jest.mock('@/services/auth', () => ({
  hasStoredSession: jest.fn(async () => true),
  getCurrentUser: jest.fn(async () => ({ id: 'u1', full_name: 'Naledi Dlamini', roles: ['RENTER'] })),
  logout: jest.fn(async () => void order.push('end session')),
}));
const push = jest.requireMock('@/lib/push') as { setUpPush: jest.Mock };

function Probe() {
  const auth = useAuth();
  return (
    <>
      <Text>{auth.state.status}</Text>
      <Pressable accessibilityRole="button" onPress={() => void auth.logout()}>
        <Text>Log out</Text>
      </Pressable>
    </>
  );
}

it('refreshes push silently after sign-in and forgets it before signing out', async () => {
  await render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
  expect(await screen.findByText('signedIn')).toBeTruthy();
  await waitFor(() => expect(push.setUpPush).toHaveBeenCalledWith({ ask: false }));

  await fireEvent.press(screen.getByText('Log out'));
  expect(await screen.findByText('signedOut')).toBeTruthy();
  expect(order).toEqual(['forget push token', 'end session']);
});
