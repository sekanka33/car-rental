export type VerificationStatus =
  | 'NOT_SUBMITTED'
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'REQUIRES_MORE_INFORMATION';

export interface CustomerProfile {
  fullName: string;
  email: string;
  phone: string;
  idDocumentStatus: VerificationStatus;
  drivingLicenceStatus: VerificationStatus;
}
