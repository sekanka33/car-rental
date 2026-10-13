import { Link, router } from 'expo-router';
import { useState } from 'react';
import { Text } from 'react-native';

import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { TextField } from '@/components/ui/text-field';
import { useAuth } from '@/context/auth';
import { ApiError } from '@/lib/api';
import { validateEmail } from '@/lib/validation';

export default function LoginScreen() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: string | null; password?: string | null }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    const next = { email: validateEmail(email), password: password ? null : 'Password is required.' };
    setErrors(next);
    setFormError(null);
    if (next.email || next.password) return;
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      if (router.canGoBack()) router.back();
      else router.replace('/home');
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'Could not log in. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Screen scroll>
      <Text className="mb-1 text-2xl font-bold text-ink">Welcome back</Text>
      <Text className="mb-6 text-base text-ink-muted">Log in to book and manage your rentals.</Text>
      {formError ? <Notice tone="danger" message={formError} /> : null}
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
      <Button label="Log in" onPress={handleSubmit} loading={submitting} className="mt-2" />
      <Text className="mt-6 text-center text-base text-ink-muted">
        New here?{' '}
        <Link href="/register" replace className="font-semibold text-brand-600">
          Create an account
        </Link>
      </Text>
    </Screen>
  );
}
