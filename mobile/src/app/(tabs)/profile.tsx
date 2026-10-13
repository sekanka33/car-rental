import { router } from 'expo-router';
import { Text, View } from 'react-native';

import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { SAMPLE_CUSTOMER_PROFILE } from '@/data/sample-vehicles';
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

export default function ProfileScreen() {
  // Stage 02 preview: replaced by the authenticated user's profile from the backend.
  const profile = SAMPLE_CUSTOMER_PROFILE;
  const idStatus = STATUS_DISPLAY[profile.idDocumentStatus];
  const licenceStatus = STATUS_DISPLAY[profile.drivingLicenceStatus];
  const initials = profile.fullName
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <Screen scroll>
      <Notice message="Preview profile: sample data, not your account." />
      <View className="items-center">
        <View className="h-20 w-20 items-center justify-center rounded-full bg-brand-100">
          <Text className="text-2xl font-bold text-brand-700">{initials}</Text>
        </View>
        <Text className="mt-3 text-xl font-semibold text-ink">{profile.fullName}</Text>
        <Text className="text-base text-ink-muted">{profile.email}</Text>
      </View>

      <Text className="mb-1 mt-8 text-sm font-semibold uppercase text-ink-subtle">Contact</Text>
      <Row label="Mobile">
        <Text className="text-base text-ink">{profile.phone}</Text>
      </Row>

      <Text className="mb-1 mt-8 text-sm font-semibold uppercase text-ink-subtle">
        Verification
      </Text>
      <Row label="South African ID">
        <Badge label={idStatus.label} tone={idStatus.tone} />
      </Row>
      <Row label="Driving licence">
        <Badge label={licenceStatus.label} tone={licenceStatus.tone} />
      </Row>
      <Text className="mt-3 text-sm text-ink-muted">
        You need an approved ID and driving licence before you can book. Document upload opens
        in a later release.
      </Text>

      <Button
        label="Log out"
        variant="secondary"
        className="mt-10"
        onPress={() => router.replace('/')}
      />
    </Screen>
  );
}
