/**
 * Picking files on the phone (camera, photo library, PDF) and attaching them to a multipart
 * form. The backend checks every file's real type by content; these are only conveniences.
 */
import * as DocumentPicker from 'expo-document-picker';
import { File } from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';
import { Platform } from 'react-native';

export interface PickedFile {
  uri: string;
  name: string;
  mimeType: string;
}

export type ImageSource = 'camera' | 'library';

export class PermissionDeniedError extends Error {
  constructor(source: ImageSource) {
    super(
      source === 'camera'
        ? 'Allow camera access in your phone settings to take a photo.'
        : 'Allow photo access in your phone settings to choose a picture.',
    );
    this.name = 'PermissionDeniedError';
  }
}

/** A photo from the camera or library, or null if the user cancelled. */
export async function pickImage(source: ImageSource): Promise<PickedFile | null> {
  const permission =
    source === 'camera'
      ? await ImagePicker.requestCameraPermissionsAsync()
      : await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!permission.granted) throw new PermissionDeniedError(source);
  const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.8 };
  const result =
    source === 'camera' ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
  if (result.canceled || result.assets.length === 0) return null;
  const asset = result.assets[0];
  const mimeType = asset.mimeType ?? 'image/jpeg';
  return { uri: asset.uri, name: asset.fileName ?? `photo.${mimeType.split('/')[1] ?? 'jpg'}`, mimeType };
}

/** A PDF or image from the phone's files, or null if cancelled. */
export async function pickDocument(): Promise<PickedFile | null> {
  const result = await DocumentPicker.getDocumentAsync({
    type: ['application/pdf', 'image/jpeg', 'image/png'],
    copyToCacheDirectory: true,
  });
  if (result.canceled || result.assets.length === 0) return null;
  const asset = result.assets[0];
  return { uri: asset.uri, name: asset.name, mimeType: asset.mimeType ?? 'application/pdf' };
}

/** Adds a picked file to a form using the file representation supported by each fetch runtime. */
export async function appendFile(form: FormData, field: string, file: PickedFile): Promise<void> {
  if (Platform.OS === 'web') {
    const blob = await (await fetch(file.uri)).blob();
    form.append(field, blob, file.name);
    return;
  }
  form.append(field, new File(file.uri), file.name);
}
