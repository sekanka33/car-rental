import Ionicons from '@expo/vector-icons/Ionicons';
import { Redirect, router } from 'expo-router';
import { Text, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { Screen } from '@/components/ui/screen';
import { LoadingState } from '@/components/ui/state-views';
import { BRAND, COLORS } from '@/constants/brand';
import { useAuth } from '@/context/auth';

export default function WelcomeScreen() {
  const { state } = useAuth();
  if (state.status === 'loading') return <LoadingState />;
  if (state.status === 'signedIn') return <Redirect href="/home" />;

  return (
    <Screen edgeTop className="justify-between px-6 py-10">
      <View className="flex-1 items-center justify-center">
        <View className="h-24 w-24 items-center justify-center rounded-3xl bg-brand-500">
          <Ionicons name="car-sport" size={52} color={COLORS.white} />
        </View>
        <Text className="mt-6 text-3xl font-bold text-ink">{BRAND.appName}</Text>
        <Text className="mt-3 text-center text-base text-ink-muted">{BRAND.tagline}</Text>
      </View>
      <View className="gap-3">
        <Button label="Create an account" onPress={() => router.push('/register')} />
        <Button label="Log in" variant="secondary" onPress={() => router.push('/login')} />
        <Button label="Browse cars" variant="ghost" onPress={() => router.replace('/home')} />
      </View>
    </Screen>
  );
}
