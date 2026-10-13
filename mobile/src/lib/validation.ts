/**
 * Client-side form checks for fast feedback only. The backend repeats and
 * enforces all validation (Stage 05) — never rely on these for security.
 */
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
/** South African mobile numbers: 0XX XXX XXXX or +27 XX XXX XXXX. */
const SA_MOBILE_PATTERN = /^(?:0|\+27)[6-8]\d{8}$/;

export const MIN_PASSWORD_LENGTH = 8;

export function validateEmail(email: string): string | null {
  if (!email.trim()) return 'Email is required.';
  return EMAIL_PATTERN.test(email.trim()) ? null : 'Enter a valid email address.';
}

export function validatePassword(password: string): string | null {
  if (!password) return 'Password is required.';
  return password.length >= MIN_PASSWORD_LENGTH
    ? null
    : `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
}

export function validateSaMobile(phone: string): string | null {
  if (!phone.trim()) return 'Mobile number is required.';
  return SA_MOBILE_PATTERN.test(phone.replace(/\s/g, ''))
    ? null
    : 'Enter a South African mobile number, e.g. 082 123 4567.';
}

export function validateRequired(value: string, label: string): string | null {
  return value.trim() ? null : `${label} is required.`;
}
