import { Link, router } from 'expo-router';
import { useState } from 'react';
import { Text } from 'react-native';

import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { TextField } from '@/components/ui/text-field';
import { validateEmail, validatePassword } from '@/lib/validation';

export default function LoginScreen() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: string | null; password?: string | null }>({});

  const handleSubmit = () => {
    const next = { email: validateEmail(email), password: validatePassword(password) };
    setErrors(next);
    if (next.email || next.password) return;
    // Stage 02 preview: no server authentication yet (added in Stage 05).
    router.replace('/home');
  };

  return (
    <Screen scroll>
      <Text className="mb-1 text-2xl font-bold text-ink">Welcome back</Text>
      <Text className="mb-6 text-base text-ink-muted">Log in to manage your rentals.</Text>
      <Notice message="Preview build: sign-in is not connected to a server yet." />
      <TextField
        label="Email"
        value={email}
        onChangeText={setEmail}
        error={errors.email}
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        placeholder="you@example.com"
      />
      <TextField
        label="Password"
        value={password}
        onChangeText={setPassword}
        error={errors.password}
        secureTextEntry
        autoComplete="password"
        placeholder="Your password"
      />
      <Button label="Log in" onPress={handleSubmit} className="mt-2" />
      <Text className="mt-6 text-center text-base text-ink-muted">
        New here?{' '}
        <Link href="/register" replace className="font-semibold text-brand-600">
          Create an account
        </Link>
      </Text>
    </Screen>
  );
}
