import Ionicons from '@expo/vector-icons/Ionicons';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { SectionTitle } from '@/components/dashboard';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { Screen } from '@/components/ui/screen';
import { ErrorState, LoadingState } from '@/components/ui/state-views';
import { TextField } from '@/components/ui/text-field';
import { COLORS } from '@/constants/brand';
import { useAsync } from '@/hooks/use-async';
import { ApiError } from '@/lib/api';
import { formatDateRange } from '@/lib/format';
import { blockPeriod } from '@/lib/owner';
import { addBlock, listBlocks, removeBlock } from '@/services/owner';
import type { AvailabilityBlock } from '@/types/owner';

function Blocks({ vehicleId, blocks, reload }: { vehicleId: string; blocks: AvailabilityBlock[]; reload: () => void }) {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const add = async () => {
    const period = blockPeriod(from, to);
    if (typeof period === 'string') {
      setError(period);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await addBlock(vehicleId, { ...period, reason: reason.trim() || null });
      setFrom('');
      setTo('');
      setReason('');
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not block those dates.');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (blockId: string) => {
    try {
      await removeBlock(vehicleId, blockId);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not remove the block.');
    }
  };

  return (
    <Screen scroll>
      <Stack.Screen options={{ title: 'Blocked dates' }} />
      <Text className="text-base text-ink-muted">
        Renters cannot book your car on blocked days (for example when you need it yourself or it is being serviced). Dates that
        are already booked cannot be blocked.
      </Text>

      <SectionTitle title="Block days" />
      <View className="flex-row gap-3">
        <View className="flex-1">
          <TextField label="First day" value={from} onChangeText={setFrom} placeholder="YYYY-MM-DD" maxLength={10} />
        </View>
        <View className="flex-1">
          <TextField label="Last day" value={to} onChangeText={setTo} placeholder="YYYY-MM-DD" maxLength={10} />
        </View>
      </View>
      <TextField label="Reason (optional, only you see it)" value={reason} onChangeText={setReason} maxLength={200} />
      {error ? (
        <View className="mb-3">
          <Notice tone="danger" message={error} />
        </View>
      ) : null}
      <Button label="Block these days" loading={busy} onPress={add} />

      <SectionTitle title="Blocked" />
      {blocks.length === 0 ? <Text className="text-base text-ink-muted">No blocked days.</Text> : null}
      {blocks.map((block) => (
        <View key={block.id} className="flex-row items-center border-b border-surface-border py-3">
          <View className="flex-1">
            <Text className="text-base text-ink">{formatDateRange(block.start_at, new Date(Date.parse(block.end_at) - 1).toISOString())}</Text>
            {block.reason ? <Text className="text-sm text-ink-muted">{block.reason}</Text> : null}
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="Remove block" onPress={() => remove(block.id)} className="p-2">
            <Ionicons name="trash-outline" size={20} color={COLORS.danger} />
          </Pressable>
        </View>
      ))}
    </Screen>
  );
}

export default function AvailabilityScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const load = useCallback(() => listBlocks(id), [id]);
  const blocks = useAsync(load);
  if (blocks.status === 'loading') return <LoadingState />;
  if (blocks.status === 'error') return <ErrorState message={blocks.error.message} onAction={blocks.reload} />;
  return <Blocks vehicleId={id} blocks={blocks.data} reload={blocks.reload} />;
}
