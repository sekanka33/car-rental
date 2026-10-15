import { router } from 'expo-router';
import { useCallback } from 'react';
import { Text, View } from 'react-native';

import { SignInPrompt } from '@/components/sign-in-prompt';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Screen } from '@/components/ui/screen';
import { LoadingState } from '@/components/ui/state-views';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { getCustomerProfile } from '@/services/customers';
import type { VerificationStatus } from '@/types/profile';

const STATUS_DISPLAY: Record<VerificationStatus, { label: string; tone: BadgeTone }> = {
  NOT_SUBMITTED: { label: 'Not submitted', tone: 'neutral' },
  PENDING: { label: 'Under review', tone: 'info' },
  APPROVED: { label: 'Approved', tone: 'success' },
  REJECTED: { label: 'Rejected', tone: 'danger' },
  REQUIRES_MORE_INFORMATION: { label: 'More info needed', tone: 'warning' },
};

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View className="flex-row items-center justify-between border-b border-surface-border py-3">
      <Text className="text-base text-ink-muted">{label}</Text>
      {children}
    </View>
  );
}

function RenterVerification() {
  const load = useCallback(() => getCustomerProfile(), []);
  const profile = useAsync(load);
  if (profile.status === 'loading') return <Text className="text-base text-ink-muted">Loading…</Text>;
  if (profile.status === 'error') return <Text className="text-base text-ink-muted">Could not load verification.</Text>;
  const id = STATUS_DISPLAY[profile.data.id_verification_status];
  const licence = STATUS_DISPLAY[profile.data.licence_verification_status];
  return (
    <>
      <Row label="South African ID">
        <Badge label={id.label} tone={id.tone} />
      </Row>
      <Row label="Driving licence">
        <Badge label={licence.label} tone={licence.tone} />
      </Row>
      <Text className="mt-3 text-sm text-ink-muted">
        You need an approved ID and driving licence before you can book. Uploading documents in
        the app arrives in a later release.
      </Text>
    </>
  );
}

export default function ProfileScreen() {
  const { state, logout } = useAuth();
  if (state.status === 'loading') return <LoadingState />;
  if (state.status === 'signedOut') return <SignInPrompt message="Log in to see your profile." />;

  const { user } = state;
  const initials = user.full_name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <Screen scroll>
      <View className="items-center">
        <View className="h-20 w-20 items-center justify-center rounded-full bg-brand-100">
          <Text className="text-2xl font-bold text-brand-700">{initials}</Text>
        </View>
        <Text className="mt-3 text-xl font-semibold text-ink">{user.full_name}</Text>
        <Text className="text-base text-ink-muted">{user.email}</Text>
      </View>

      <Text className="mb-1 mt-8 text-sm font-semibold uppercase text-ink-subtle">Account</Text>
      <Row label="Account type">
        <Text className="text-base text-ink">{user.roles.map((r) => r.toLowerCase()).join(', ')}</Text>
      </Row>
      <Row label="Email">
        <Badge
          label={user.email_verified ? 'Confirmed' : 'Not confirmed'}
          tone={user.email_verified ? 'success' : 'warning'}
        />
      </Row>
      {user.phone_number ? (
        <Row label="Mobile">
          <Text className="text-base text-ink">{user.phone_number}</Text>
        </Row>
      ) : null}

      {user.roles.includes('RENTER') ? (
        <>
          <Text className="mb-1 mt-8 text-sm font-semibold uppercase text-ink-subtle">Verification</Text>
          <RenterVerification />
        </>
      ) : null}

      {user.roles.includes('OWNER') ? (
        <Button label="My deliveries" variant="secondary" className="mt-8" onPress={() => router.push('/deliveries')} />
      ) : null}

      <Button
        label="Log out"
        variant="secondary"
        className="mt-10"
        onPress={async () => {
          await logout();
          router.replace('/');
        }}
      />
    </Screen>
  );
}
