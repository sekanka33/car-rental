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
        <Stack.Screen name="payments/return" options={{ title: 'Payment' }} />
        <Stack.Screen name="deliveries/index" options={{ title: 'My deliveries' }} />
        <Stack.Screen name="deliveries/[id]" options={{ title: 'Delivery' }} />
        <Stack.Screen name="payments/index" options={{ title: 'Payment history' }} />
        <Stack.Screen name="verification" options={{ title: 'Verify your identity' }} />
        <Stack.Screen name="owner/vehicles/index" options={{ title: 'My cars' }} />
        <Stack.Screen name="owner/vehicles/new" options={{ title: 'Register a car' }} />
        <Stack.Screen name="owner/vehicles/[id]/index" options={{ title: 'Car' }} />
        <Stack.Screen name="owner/vehicles/[id]/edit" options={{ title: 'Edit car' }} />
        <Stack.Screen name="owner/vehicles/[id]/availability" options={{ title: 'Blocked dates' }} />
        <Stack.Screen name="owner/bookings" options={{ title: 'Bookings of my cars' }} />
        <Stack.Screen name="owner/earnings" options={{ title: 'Earnings' }} />
      </Stack>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
