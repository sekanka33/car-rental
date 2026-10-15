import { apiRequest } from '@/lib/api';
import { appendFile, type PickedFile } from '@/lib/upload';
import type { RenterPayment } from '@/types/payment';
import type { CustomerProfile, DocumentSubmission, DocumentType } from '@/types/profile';

const BASE = '/api/v1/customers/me';

export function getCustomerProfile(): Promise<CustomerProfile> {
  return apiRequest<CustomerProfile>('GET', `${BASE}/profile`, { auth: true });
}

export function setDateOfBirth(dateOfBirth: string): Promise<CustomerProfile> {
  return apiRequest<CustomerProfile>('PUT', `${BASE}/profile/date-of-birth`, {
    auth: true,
    body: { date_of_birth: dateOfBirth },
  });
}

export function listMyDocuments(): Promise<DocumentSubmission[]> {
  return apiRequest<DocumentSubmission[]>('GET', `${BASE}/documents`, { auth: true });
}

export interface DocumentUpload {
  documentType: DocumentType;
  documentNumber: string;
  front: PickedFile;
  back: PickedFile | null;
  licenceExpiryDate: string | null;
  licenceCodes: string | null;
}

export async function submitDocument(upload: DocumentUpload): Promise<DocumentSubmission> {
  const form = new FormData();
  form.append('document_type', upload.documentType);
  form.append('document_number', upload.documentNumber);
  if (upload.licenceExpiryDate) form.append('licence_expiry_date', upload.licenceExpiryDate);
  if (upload.licenceCodes) form.append('licence_codes', upload.licenceCodes);
  await appendFile(form, 'front', upload.front);
  if (upload.back) await appendFile(form, 'back', upload.back);
  return apiRequest<DocumentSubmission>('POST', `${BASE}/documents`, { auth: true, form, timeoutMs: 60_000 });
}

export function listMyPayments(): Promise<RenterPayment[]> {
  return apiRequest<RenterPayment[]>('GET', `${BASE}/payments`, { auth: true });
}
