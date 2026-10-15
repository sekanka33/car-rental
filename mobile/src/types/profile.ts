export type VerificationStatus =
  | 'NOT_SUBMITTED'
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'REQUIRES_MORE_INFORMATION';

/** GET /api/v1/customers/me/profile */
export interface CustomerProfile {
  date_of_birth: string | null;
  id_verification_status: VerificationStatus;
  licence_verification_status: VerificationStatus;
  licence_expiry_date: string | null;
  minimum_age: number;
}

export type DocumentType = 'SA_ID' | 'DRIVING_LICENCE';

/** GET /api/v1/customers/me/documents (numbers are masked by the backend). */
export interface DocumentSubmission {
  id: string;
  document_type: DocumentType;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'REQUIRES_MORE_INFORMATION' | 'SUPERSEDED';
  document_number_masked: string;
  licence_expiry_date: string | null;
  licence_codes: string | null;
  review_note: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  files: { id: string; side: 'FRONT' | 'BACK'; content_type: string; size_bytes: number }[];
}
