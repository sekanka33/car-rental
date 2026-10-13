import { Stack } from 'expo-router';

import { COLORS } from '@/constants/brand';

export default function AuthLayout() {
  return (
    <Stack
      screenOptions={{
        headerTintColor: COLORS.ink,
        headerShadowVisible: false,
        headerBackButtonDisplayMode: 'minimal',
        contentStyle: { backgroundColor: COLORS.white },
      }}>
      <Stack.Screen name="login" options={{ title: 'Log in' }} />
      <Stack.Screen name="register" options={{ title: 'Create account' }} />
    </Stack>
  );
}
