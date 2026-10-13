import '@/global.css';

import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { COLORS } from '@/constants/brand';
import { AuthProvider } from '@/context/auth';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerTintColor: COLORS.ink,
          headerTitleStyle: { fontWeight: '600' },
          headerBackButtonDisplayMode: 'minimal',
          contentStyle: { backgroundColor: COLORS.white },
        }}>
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="(auth)" options={{ headerShown: false }} />
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="vehicles/[id]/index" options={{ title: 'Vehicle details' }} />
        <Stack.Screen name="vehicles/[id]/book" options={{ title: 'Book this car' }} />
        <Stack.Screen name="bookings/[id]" options={{ title: 'Booking' }} />
      </Stack>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
