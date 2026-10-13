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
