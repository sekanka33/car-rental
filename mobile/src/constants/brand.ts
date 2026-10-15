/**
 * Branding placeholders. Replace once the final product name, logo and
 * colours are chosen. Tailwind colour tokens live in tailwind.config.js.
 */
export const BRAND = {
  appName: 'CarHire SA',
  tagline: 'Rent trusted cars from local owners, delivered to your door.',
} as const;

/** Hex values for props that cannot take Tailwind classes (icons, placeholders). */
export const COLORS = {
  brand: '#1F6FEB',
  ink: '#111827',
  inkMuted: '#6B7280',
  inkSubtle: '#9CA3AF',
  danger: '#B91C1C',
  warning: '#B45309',
  white: '#FFFFFF',
} as const;
