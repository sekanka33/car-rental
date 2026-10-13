import { Link, router } from 'expo-router';
import { useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { useAuth } from '@/context/auth';
import { ApiError } from '@/lib/api';

import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { TextField } from '@/components/ui/text-field';
import {
  validateEmail,
  validatePassword,
  validateRequired,
  validateSaMobile,
} from '@/lib/validation';

type AccountType = 'RENTER' | 'OWNER';

const ACCOUNT_TYPES: { value: AccountType; label: string; hint: string }[] = [
  { value: 'RENTER', label: 'Rent a car', hint: 'Book vehicles from owners' },
  { value: 'OWNER', label: 'List my car', hint: 'Earn from your vehicle' },
];

type Field = 'fullName' | 'email' | 'phone' | 'password' | 'confirmPassword';

export default function RegisterScreen() {
  const { register } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [accountType, setAccountType] = useState<AccountType>('RENTER');
  const [form, setForm] = useState<Record<Field, string>>({
    fullName: '',
    email: '',
    phone: '',
    password: '',
    confirmPassword: '',
  });
  const [errors, setErrors] = useState<Partial<Record<Field, string | null>>>({});

  const update = (field: Field) => (value: string) => setForm((f) => ({ ...f, [field]: value }));

  const handleSubmit = async () => {
    const next = {
      fullName: validateRequired(form.fullName, 'Full name'),
      email: validateEmail(form.email),
      phone: validateSaMobile(form.phone),
      password: validatePassword(form.password),
      confirmPassword:
        form.confirmPassword === form.password ? null : 'Passwords do not match.',
    };
    setErrors(next);
    setFormError(null);
    if (Object.values(next).some(Boolean)) return;
    setSubmitting(true);
    try {
      await register({
        email: form.email.trim(),
        password: form.password,
        full_name: form.fullName.trim(),
        phone_number: form.phone.trim() || undefined,
        account_type: accountType,
      });
      router.replace('/home');
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'Could not create the account.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Screen scroll>
      <Text className="mb-1 text-2xl font-bold text-ink">Create your account</Text>
      <Text className="mb-6 text-base text-ink-muted">How will you use the app?</Text>
      {formError ? <Notice tone="danger" message={formError} /> : null}

      <View className="mb-6 flex-row gap-3" accessibilityRole="radiogroup">
        {ACCOUNT_TYPES.map((option) => {
          const selected = option.value === accountType;
          return (
            <Pressable
              key={option.value}
              accessibilityRole="radio"
              accessibilityState={{ checked: selected }}
              onPress={() => setAccountType(option.value)}
              className={`flex-1 rounded-xl border p-4 ${
                selected ? 'border-brand-500 bg-brand-50' : 'border-surface-border bg-white'
              }`}>
              <Text className={`font-semibold ${selected ? 'text-brand-700' : 'text-ink'}`}>
                {option.label}
              </Text>
              <Text className="mt-1 text-xs text-ink-muted">{option.hint}</Text>
            </Pressable>
          );
        })}
      </View>

      <TextField
        label="Full name"
        value={form.fullName}
        onChangeText={update('fullName')}
        error={errors.fullName}
        autoComplete="name"
        placeholder="e.g. Thandi Nkosi"
      />
      <TextField
        label="Email"
        value={form.email}
        onChangeText={update('email')}
        error={errors.email}
        autoCapitalize="none"
        autoComplete="email"
        keyboardType="email-address"
        placeholder="you@example.com"
      />
      <TextField
        label="Mobile number"
        value={form.phone}
        onChangeText={update('phone')}
        error={errors.phone}
        autoComplete="tel"
        keyboardType="phone-pad"
        placeholder="082 123 4567"
      />
      <TextField
        label="Password"
        value={form.password}
        onChangeText={update('password')}
        error={errors.password}
        secureTextEntry
        autoComplete="new-password"
        placeholder="At least 8 characters"
      />
      <TextField
        label="Confirm password"
        value={form.confirmPassword}
        onChangeText={update('confirmPassword')}
        error={errors.confirmPassword}
        secureTextEntry
        autoComplete="new-password"
        placeholder="Repeat your password"
      />
      <Button label="Create account" onPress={handleSubmit} loading={submitting} className="mt-2" />
      <Text className="mt-3 text-center text-sm text-ink-muted">
        We will email you a link to confirm your address.
      </Text>
      <Text className="mt-6 text-center text-base text-ink-muted">
        Already have an account?{' '}
        <Link href="/login" replace className="font-semibold text-brand-600">
          Log in
        </Link>
      </Text>
    </Screen>
  );
}
