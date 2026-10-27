import { appendFile, type PickedFile } from '@/lib/upload';
import { Platform } from 'react-native';
import { File } from 'expo-file-system';

jest.mock('expo-file-system', () => ({
  File: jest.fn((uri: string) => ({ uri, name: 'picked.jpg', type: 'image/jpeg', bytes: jest.fn() })),
}));

describe('appendFile', () => {
  it('uses an Expo File for native multipart uploads', async () => {
    const form = { append: jest.fn() } as unknown as FormData;
    const picked: PickedFile = {
      uri: 'file:///cache/picked.jpg',
      name: 'car.jpg',
      mimeType: 'image/jpeg',
    };

    await appendFile(form, 'photo', picked);

    expect(File).toHaveBeenCalledWith(picked.uri);
    expect(form.append).toHaveBeenCalledWith(
      'photo',
      expect.objectContaining({ uri: picked.uri }),
      picked.name,
    );
  });

  it('converts web file URIs to Blobs', async () => {
    const originalPlatform = Platform.OS;
    Object.defineProperty(Platform, 'OS', { configurable: true, value: 'web' });
    const blob = new Blob(['image']);
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue({
      blob: async () => blob,
    } as Response);
    const form = new FormData();

    try {
      await appendFile(form, 'photo', {
        uri: 'blob:car-photo',
        name: 'car.jpg',
        mimeType: 'image/jpeg',
      });

      expect(fetchMock).toHaveBeenCalledWith('blob:car-photo');
      expect(form.get('photo')).toMatchObject({ name: 'car.jpg', size: blob.size });
    } finally {
      fetchMock.mockRestore();
      Object.defineProperty(Platform, 'OS', { configurable: true, value: originalPlatform });
    }
  });
});
