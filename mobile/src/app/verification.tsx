import { Stack } from 'expo-router';
import { useCallback, useState } from 'react';
import { Platform, Text, View } from 'react-native';

import { SectionTitle } from '@/components/dashboard';
import { SignInPrompt } from '@/components/sign-in-prompt';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { ErrorState, LoadingState } from '@/components/ui/state-views';
import { TextField } from '@/components/ui/text-field';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { ApiError } from '@/lib/api';
import { formatDateTime, saToday } from '@/lib/dates';
import { isIsoDate } from '@/lib/labels';
import { pickDocument, type PickedFile, pickImage } from '@/lib/upload';
import { getCustomerProfile, listMyDocuments, setDateOfBirth, submitDocument } from '@/services/customers';
import type { CustomerProfile, DocumentSubmission, DocumentType, VerificationStatus } from '@/types/profile';

const STATUS: Record<VerificationStatus, { label: string; tone: BadgeTone }> = {
  NOT_SUBMITTED: { label: 'Not submitted', tone: 'neutral' },
  PENDING: { label: 'Under review', tone: 'info' },
  APPROVED: { label: 'Approved', tone: 'success' },
  REJECTED: { label: 'Rejected', tone: 'danger' },
  REQUIRES_MORE_INFORMATION: { label: 'More info needed', tone: 'warning' },
};

const message = (e: unknown, fallback: string) =>
  e instanceof ApiError ? e.message : e instanceof Error ? e.message : fallback;

function DateOfBirth({ profile, onSaved }: { profile: CustomerProfile; onSaved: () => void }) {
  const [value, setValue] = useState(profile.date_of_birth ?? '');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const locked = profile.id_verification_status === 'APPROVED' || profile.id_verification_status === 'PENDING';
  const save = async () => {
    if (!isIsoDate(value) || value >= saToday()) return setError('Enter your date of birth as YYYY-MM-DD.');
    setBusy(true);
    setError(null);
    try {
      await setDateOfBirth(value);
      onSaved();
    } catch (e) {
      setError(message(e, 'Could not save your date of birth.'));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <SectionTitle title="1. Date of birth" />
      {locked ? (
        <Text className="text-base text-ink">{profile.date_of_birth}</Text>
      ) : (
        <>
          <Text className="mb-2 text-sm text-ink-muted">You must be at least {profile.minimum_age} to rent. It must match your ID.</Text>
          <TextField label="Date of birth" value={value} onChangeText={setValue} placeholder="YYYY-MM-DD" maxLength={10} error={error} />
          <Button label="Save date of birth" variant="secondary" loading={busy} onPress={save} />
        </>
      )}
    </>
  );
}

function FileChoice({ label, file, onPick }: { label: string; file: PickedFile | null; onPick: (f: PickedFile) => void }) {
  const [error, setError] = useState<string | null>(null);
  const choose = async (pick: () => Promise<PickedFile | null>) => {
    setError(null);
    try {
      const picked = await pick();
      if (picked) onPick(picked);
    } catch (e) {
      setError(message(e, 'Could not open the file.'));
    }
  };
  return (
    <View className="mb-3">
      <Text className="mb-1.5 text-sm font-medium text-ink">{label}</Text>
      {file ? <Text className="mb-1 text-sm text-success">Selected: {file.name}</Text> : null}
      <View className="flex-row gap-3">
        {Platform.OS !== 'web' ? (
          <Button label="Take photo" variant="secondary" className="flex-1" onPress={() => choose(() => pickImage('camera'))} />
        ) : null}
        <Button label="Choose file" variant="secondary" className="flex-1" onPress={() => choose(pickDocument)} />
      </View>
      {error ? <Text className="mt-1 text-sm text-danger">{error}</Text> : null}
    </View>
  );
}

function DocumentForm({
  type,
  status,
  latest,
  disabledReason,
  onSubmitted,
}: {
  type: DocumentType;
  status: VerificationStatus;
  latest: DocumentSubmission | undefined;
  disabledReason: string | null;
  onSubmitted: () => void;
}) {
  const isId = type === 'SA_ID';
  const [open, setOpen] = useState(false);
  const [number, setNumber] = useState('');
  const [expiry, setExpiry] = useState('');
  const [codes, setCodes] = useState('');
  const [front, setFront] = useState<PickedFile | null>(null);
  const [back, setBack] = useState<PickedFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const badge = STATUS[status];
  const canSubmit = status !== 'APPROVED' && status !== 'PENDING';

  const submit = async () => {
    const digits = number.replace(/\s/g, '');
    if (isId && !/^\d{13}$/.test(digits)) return setError('Your SA ID number has 13 digits.');
    if (!isId && !/^[A-Za-z0-9]{6,20}$/.test(digits)) return setError('Enter the licence number (6–20 letters or digits).');
    if (!isId && (!isIsoDate(expiry) || expiry <= saToday())) return setError('Enter the licence expiry date as YYYY-MM-DD.');
    if (!front) return setError('Add a photo or scan of the front.');
    setBusy(true);
    setError(null);
    try {
      await submitDocument({
        documentType: type,
        documentNumber: digits,
        front,
        back,
        licenceExpiryDate: isId ? null : expiry,
        licenceCodes: isId ? null : codes.trim() || null,
      });
      setOpen(false);
      onSubmitted();
    } catch (e) {
      setError(message(e, 'Could not upload the document.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <SectionTitle title={isId ? '2. South African ID' : '3. Driving licence'} />
      <View className="flex-row items-center justify-between">
        <Text className="text-base text-ink">{latest ? `No. ${latest.document_number_masked}` : 'Nothing uploaded yet'}</Text>
        <Badge label={badge.label} tone={badge.tone} />
      </View>
      {latest ? <Text className="mt-1 text-sm text-ink-muted">Submitted {formatDateTime(latest.submitted_at)}</Text> : null}
      {latest?.review_note && (status === 'REJECTED' || status === 'REQUIRES_MORE_INFORMATION') ? (
        <View className="mt-2">
          <Notice tone="danger" message={`Reviewer: ${latest.review_note}`} />
        </View>
      ) : null}
      {status === 'PENDING' ? <Text className="mt-2 text-sm text-ink-muted">An administrator is checking it. This is usually done within one working day.</Text> : null}

      {canSubmit && !open ? (
        <Button
          label={latest ? 'Upload again' : 'Upload'}
          className="mt-3"
          disabled={disabledReason !== null}
          onPress={() => setOpen(true)}
        />
      ) : null}
      {canSubmit && disabledReason ? <Text className="mt-1 text-sm text-ink-muted">{disabledReason}</Text> : null}

      {open ? (
        <View className="mt-3">
          <TextField
            label={isId ? 'ID number' : 'Licence number'}
            value={number}
            onChangeText={setNumber}
            keyboardType={isId ? 'number-pad' : 'default'}
            autoCapitalize="characters"
            maxLength={isId ? 13 : 20}
          />
          {!isId ? (
            <>
              <TextField label="Expiry date" value={expiry} onChangeText={setExpiry} placeholder="YYYY-MM-DD" maxLength={10} />
              <TextField label="Licence codes (optional)" value={codes} onChangeText={setCodes} placeholder="B, EB" maxLength={50} />
            </>
          ) : null}
          <FileChoice label="Front" file={front} onPick={setFront} />
          <FileChoice label={isId ? 'Back (ID card only, optional)' : 'Back (optional)'} file={back} onPick={setBack} />
          {error ? (
            <View className="mb-3">
              <Notice tone="danger" message={error} />
            </View>
          ) : null}
          <View className="flex-row gap-3">
            <Button label="Cancel" variant="secondary" className="flex-1" onPress={() => setOpen(false)} />
            <Button label="Submit" className="flex-1" loading={busy} onPress={submit} />
          </View>
        </View>
      ) : null}
    </>
  );
}

function Verification() {
  const profile = useAsync(getCustomerProfile);
  const documents = useAsync(listMyDocuments);
  const { reload: reloadProfile } = profile;
  const { reload: reloadDocuments } = documents;
  const reload = useCallback(() => {
    reloadProfile();
    reloadDocuments();
  }, [reloadProfile, reloadDocuments]);

  if (profile.status === 'loading' || documents.status === 'loading') return <LoadingState />;
  if (profile.status === 'error') return <ErrorState message={profile.error.message} onAction={reload} />;
  if (documents.status === 'error') return <ErrorState message={documents.error.message} onAction={reload} />;

  const latest = (type: DocumentType) =>
    documents.data.filter((d) => d.document_type === type && d.status !== 'SUPERSEDED')[0] ??
    documents.data.find((d) => d.document_type === type);
  const p = profile.data;
  const done = p.id_verification_status === 'APPROVED' && p.licence_verification_status === 'APPROVED';

  return (
    <Screen scroll>
      <Text className="text-base text-ink-muted">
        Before your first booking we check your ID and driving licence. Files are stored privately and only CarHire SA reviewers
        can see them. We keep only the last digits of your numbers.
      </Text>
      {done ? (
        <View className="mt-4">
          <Notice tone="success" message="You are verified and can book." />
        </View>
      ) : null}
      <DateOfBirth profile={p} onSaved={reload} />
      <DocumentForm
        type="SA_ID"
        status={p.id_verification_status}
        latest={latest('SA_ID')}
        disabledReason={p.date_of_birth ? null : 'Save your date of birth first.'}
        onSubmitted={reload}
      />
      <DocumentForm
        type="DRIVING_LICENCE"
        status={p.licence_verification_status}
        latest={latest('DRIVING_LICENCE')}
        disabledReason={null}
        onSubmitted={reload}
      />
    </Screen>
  );
}

export default function VerificationScreen() {
  const { state } = useAuth();
  return (
    <>
      <Stack.Screen options={{ title: 'Verify your identity' }} />
      {state.status === 'loading' ? (
        <LoadingState />
      ) : state.status === 'signedOut' ? (
        <SignInPrompt message="Log in to verify your identity." />
      ) : (
        <Verification />
      )}
    </>
  );
}
