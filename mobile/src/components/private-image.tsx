import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import { useEffect, useState } from 'react';
import { View } from 'react-native';

import { COLORS } from '@/constants/brand';
import { getAccessToken, resolveApiUrl } from '@/lib/api';

/** An image the API serves only to signed-in, authorised users (sent with the access token). */
export function PrivateImage({ path, className = 'h-24 w-24', label }: { path: string; className?: string; label: string }) {
  const [token, setToken] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    void getAccessToken().then((value) => {
      if (active) setToken(value);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <View className={`overflow-hidden rounded-xl bg-surface-muted ${className}`}>
      {token && !failed ? (
        <Image
          source={{ uri: resolveApiUrl(path), headers: { Authorization: `Bearer ${token}` } }}
          style={{ width: '100%', height: '100%' }}
          contentFit="cover"
          accessibilityLabel={label}
          onError={() => setFailed(true)}
        />
      ) : (
        <View className="flex-1 items-center justify-center">
          <Ionicons name="image-outline" size={28} color={COLORS.inkSubtle} />
        </View>
      )}
    </View>
  );
}
