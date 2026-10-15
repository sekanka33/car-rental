import { ApiError } from '@/lib/api';

/**
 * Per-field messages from a backend 422 (`details: [{location: ["body", "vin"], message}]`),
 * keyed by field name. Pydantic's "Value error, " prefix is removed.
 */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || error.code !== 'validation_error') return {};
  const result: Record<string, string> = {};
  for (const detail of error.details) {
    const location = detail.location;
    const message = detail.message;
    if (!Array.isArray(location) || typeof message !== 'string') continue;
    const field = String(location[location.length - 1]);
    result[field] ??= message.replace(/^Value error, /, '');
  }
  return result;
}

/** A sentence for the top of a form: the API message, or a generic one. */
export function formMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (error instanceof ApiError) {
    return error.code === 'validation_error' ? 'Please correct the highlighted fields.' : error.message;
  }
  return fallback;
}
