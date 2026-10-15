import { apiRequest } from '@/lib/api';
import { appendFile, type PickedFile } from '@/lib/upload';
import type {
  AvailabilityBlock,
  Earnings,
  OwnerBooking,
  OwnerBookingScope,
  OwnerDashboard,
  OwnerVehicle,
  VehicleDocumentType,
  VehicleInput,
} from '@/types/owner';

const VEHICLES = '/api/v1/owners/me/vehicles';
const UPLOAD_TIMEOUT_MS = 60_000;
const id = (value: string) => encodeURIComponent(value);

export function getOwnerDashboard(): Promise<OwnerDashboard> {
  return apiRequest<OwnerDashboard>('GET', '/api/v1/owners/me/dashboard', { auth: true });
}

export function listOwnerBookings(scope: OwnerBookingScope): Promise<OwnerBooking[]> {
  return apiRequest<OwnerBooking[]>('GET', '/api/v1/owners/me/bookings', { auth: true, params: { scope } });
}

export function getEarnings(year: number): Promise<Earnings> {
  return apiRequest<Earnings>('GET', '/api/v1/owners/me/earnings', { auth: true, params: { year } });
}

// --- vehicles -----------------------------------------------------------------------------

export function listMyVehicles(): Promise<OwnerVehicle[]> {
  return apiRequest<OwnerVehicle[]>('GET', VEHICLES, { auth: true });
}

export function getMyVehicle(vehicleId: string): Promise<OwnerVehicle> {
  return apiRequest<OwnerVehicle>('GET', `${VEHICLES}/${id(vehicleId)}`, { auth: true });
}

export function registerVehicle(input: VehicleInput): Promise<OwnerVehicle> {
  return apiRequest<OwnerVehicle>('POST', VEHICLES, { auth: true, body: input });
}

export function updateVehicle(vehicleId: string, changes: Partial<VehicleInput>): Promise<OwnerVehicle> {
  return apiRequest<OwnerVehicle>('PATCH', `${VEHICLES}/${id(vehicleId)}`, { auth: true, body: changes });
}

export function deleteVehicle(vehicleId: string): Promise<void> {
  return apiRequest<void>('DELETE', `${VEHICLES}/${id(vehicleId)}`, { auth: true });
}

export function submitVehicle(vehicleId: string): Promise<OwnerVehicle> {
  return apiRequest<OwnerVehicle>('POST', `${VEHICLES}/${id(vehicleId)}/submit`, { auth: true });
}

export function withdrawVehicle(vehicleId: string): Promise<OwnerVehicle> {
  return apiRequest<OwnerVehicle>('POST', `${VEHICLES}/${id(vehicleId)}/withdraw`, { auth: true });
}

export function setListed(vehicleId: string, available: boolean): Promise<OwnerVehicle> {
  return apiRequest<OwnerVehicle>('PUT', `${VEHICLES}/${id(vehicleId)}/listing`, { auth: true, body: { available } });
}

/** Path of a private vehicle photo (needs the access token to load). */
export function vehiclePhotoPath(vehicleId: string, photoId: string): string {
  return `${VEHICLES}/${id(vehicleId)}/photos/${id(photoId)}`;
}

export async function uploadVehiclePhoto(vehicleId: string, file: PickedFile): Promise<void> {
  const form = new FormData();
  await appendFile(form, 'photo', file);
  await apiRequest('POST', `${VEHICLES}/${id(vehicleId)}/photos`, { auth: true, form, timeoutMs: UPLOAD_TIMEOUT_MS });
}

export function deleteVehiclePhoto(vehicleId: string, photoId: string): Promise<void> {
  return apiRequest<void>('DELETE', vehiclePhotoPath(vehicleId, photoId), { auth: true });
}

export async function uploadVehicleDocument(
  vehicleId: string,
  documentType: VehicleDocumentType,
  file: PickedFile,
  expiryDate: string | null,
): Promise<void> {
  const form = new FormData();
  form.append('document_type', documentType);
  if (expiryDate) form.append('expiry_date', expiryDate);
  await appendFile(form, 'file', file);
  await apiRequest('POST', `${VEHICLES}/${id(vehicleId)}/documents`, { auth: true, form, timeoutMs: UPLOAD_TIMEOUT_MS });
}

// --- availability -------------------------------------------------------------------------

export function listBlocks(vehicleId: string): Promise<AvailabilityBlock[]> {
  return apiRequest<AvailabilityBlock[]>('GET', `${VEHICLES}/${id(vehicleId)}/availability-blocks`, { auth: true });
}

export function addBlock(
  vehicleId: string,
  block: { start_at: string; end_at: string; reason: string | null },
): Promise<AvailabilityBlock> {
  return apiRequest<AvailabilityBlock>('POST', `${VEHICLES}/${id(vehicleId)}/availability-blocks`, {
    auth: true,
    body: block,
  });
}

export function removeBlock(vehicleId: string, blockId: string): Promise<void> {
  return apiRequest<void>('DELETE', `${VEHICLES}/${id(vehicleId)}/availability-blocks/${id(blockId)}`, { auth: true });
}
