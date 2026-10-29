import { appendFile, type PickedFile } from '@/lib/upload';
import { Platform } from 'react-native';

describe('appendFile', () => {
  it('preserves the native URI, name, and MIME type in multipart data', async () => {
    const form = { append: jest.fn() } as unknown as FormData;
    const picked: PickedFile = {
      uri: 'file:///cache/picked.jpg',
      name: 'car.jpg',
      mimeType: 'image/jpeg',
    };

    await appendFile(form, 'photo', picked);

    expect(form.append).toHaveBeenCalledWith(
      'photo',
      { uri: picked.uri, name: picked.name, type: picked.mimeType },
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
