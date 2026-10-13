/**
 * Where the session tokens live.
 * - iOS/Android: expo-secure-store (Keychain / Keystore, encrypted by the OS).
 * - Web: expo-secure-store is not available, so localStorage is used. That is readable by
 *   any script on the page; acceptable for the development web preview only.
 */
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const KEY = 'carhire.session';

export interface StoredTokens {
  accessToken: string;
  refreshToken: string;
}

let cache: StoredTokens | null | undefined;

export async function loadTokens(): Promise<StoredTokens | null> {
  if (cache !== undefined) return cache;
  let raw: string | null = null;
  try {
    raw = Platform.OS === 'web' ? globalThis.localStorage?.getItem(KEY) ?? null : await SecureStore.getItemAsync(KEY);
  } catch {
    raw = null;
  }
  try {
    cache = raw ? (JSON.parse(raw) as StoredTokens) : null;
  } catch {
    cache = null;
  }
  return cache;
}

export async function saveTokens(tokens: StoredTokens): Promise<void> {
  cache = tokens;
  const raw = JSON.stringify(tokens);
  if (Platform.OS === 'web') globalThis.localStorage?.setItem(KEY, raw);
  else await SecureStore.setItemAsync(KEY, raw);
}

export async function clearTokens(): Promise<void> {
  cache = null;
  if (Platform.OS === 'web') globalThis.localStorage?.removeItem(KEY);
  else await SecureStore.deleteItemAsync(KEY);
}
