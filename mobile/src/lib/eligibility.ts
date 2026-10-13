/** Friendly text for the backend's eligibility reason codes (GET /customers/me/eligibility). */
const REASONS: Record<string, string> = {
  NOT_A_RENTER: 'Use a renter account to book.',
  ACCOUNT_NOT_ACTIVE: 'Your account is not active. Contact support.',
  EMAIL_NOT_VERIFIED: 'Confirm your email address (check your inbox for the link).',
  PROFILE_MISSING: 'Your renter profile is missing. Contact support.',
  DATE_OF_BIRTH_MISSING: 'Add your date of birth.',
  UNDER_MINIMUM_AGE: 'You do not meet the minimum age to rent.',
  ID_NOT_APPROVED: 'Your South African ID must be verified.',
  LICENCE_NOT_APPROVED: 'Your driving licence must be verified.',
  LICENCE_EXPIRES_BEFORE_RENTAL_ENDS: 'Your driving licence expires before this rental ends.',
};

export function describeReason(code: string): string {
  return REASONS[code] ?? 'A booking requirement is not met.';
}
