/**
 * PROTOTYPE DATA — the profile screen still shows this placeholder until it is
 * connected to the authenticated user's data (Stage 14). Must never ship to production.
 * (The prototype vehicles that lived here were removed in Stage 09: vehicles now come
 * from the backend.)
 */
import type { CustomerProfile } from '@/types/profile';

export const SAMPLE_CUSTOMER_PROFILE: CustomerProfile = {
  fullName: 'Preview Renter',
  email: 'renter@example.com',
  phone: '082 000 0000',
  idDocumentStatus: 'NOT_SUBMITTED',
  drivingLicenceStatus: 'NOT_SUBMITTED',
};
