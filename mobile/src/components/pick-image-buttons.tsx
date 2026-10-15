import { useState } from 'react';
import { Platform, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { type PickedFile, pickImage } from '@/lib/upload';

/**
 * "Take photo" / "Choose photo". `onPicked` does the upload; its error (or a refused
 * permission) is passed to `onError` so the screen can show it.
 */
export function PickImageButtons({
  onPicked,
  onError,
  disabled = false,
  takeLabel = 'Take photo',
  chooseLabel = 'Choose photo',
}: {
  onPicked: (file: PickedFile) => Promise<void>;
  onError: (message: string) => void;
  disabled?: boolean;
  takeLabel?: string;
  chooseLabel?: string;
}) {
  const [busy, setBusy] = useState(false);
  const run = async (source: 'camera' | 'library') => {
    setBusy(true);
    try {
      const file = await pickImage(source);
      if (file) await onPicked(file);
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Could not add the photo.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <View className="mt-2 flex-row gap-3">
      {Platform.OS !== 'web' ? (
        <Button label={takeLabel} variant="secondary" className="flex-1" loading={busy} disabled={disabled} onPress={() => run('camera')} />
      ) : null}
      <Button label={chooseLabel} variant="secondary" className="flex-1" loading={busy} disabled={disabled} onPress={() => run('library')} />
    </View>
  );
}
