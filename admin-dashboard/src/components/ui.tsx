import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { useId } from 'react';

import { ApiError } from '../lib/api';
import { humanise, type Tone } from '../lib/format';

const TONES: Record<Tone, string> = {
  neutral: 'bg-surface-muted text-ink-muted',
  info: 'bg-brand-50 text-brand-700',
  success: 'bg-green-50 text-success',
  warning: 'bg-amber-50 text-warning',
  danger: 'bg-red-50 text-danger',
};

export function Badge({ label, tone = 'neutral' }: { label: string; tone?: Tone }) {
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[tone]}`}>{label}</span>;
}

/** A status code as a badge, e.g. PENDING_APPROVAL → "Pending approval". */
export function StatusBadge<S extends string>({ status, tones }: { status: S; tones: Record<S, Tone> }) {
  return <Badge label={humanise(status)} tone={tones[status]} />;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  busy?: boolean;
};

const VARIANTS = {
  primary: 'bg-brand-500 text-white hover:bg-brand-600',
  secondary: 'border border-surface-border bg-white text-ink hover:bg-surface-muted',
  danger: 'bg-danger text-white hover:bg-red-800',
  ghost: 'text-brand-600 hover:bg-brand-50',
};

export function Button({ variant = 'primary', busy = false, disabled, className = '', children, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={`inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
      {...rest}>
      {busy ? 'Working…' : children}
    </button>
  );
}

export function Card({ title, actions, children, className = '' }: { title?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-surface-border bg-white p-5 ${className}`}>
      {title || actions ? (
        <div className="mb-4 flex items-center justify-between gap-3">
          {title ? <h2 className="text-base font-semibold">{title}</h2> : <span />}
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-ink-muted">{subtitle}</p> : null}
      </div>
      {actions}
    </div>
  );
}

function Labelled({ label, hint, error, children, id }: { label: string; hint?: string; error?: string | null; children: ReactNode; id: string }) {
  return (
    <div className="mb-4">
      <label htmlFor={id} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && !error ? <p className="mt-1 text-xs text-ink-muted">{hint}</p> : null}
      {error ? (
        <p role="alert" className="mt-1 text-sm text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

const CONTROL = 'w-full rounded-lg border border-surface-border bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none';

export function Input({ label, hint, error, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string; error?: string | null }) {
  const id = useId();
  return (
    <Labelled label={label} hint={hint} error={error} id={id}>
      <input id={id} className={CONTROL} aria-invalid={error ? true : undefined} {...rest} />
    </Labelled>
  );
}

export function TextArea({ label, hint, error, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string; error?: string | null }) {
  const id = useId();
  return (
    <Labelled label={label} hint={hint} error={error} id={id}>
      <textarea id={id} rows={3} className={CONTROL} aria-invalid={error ? true : undefined} {...rest} />
    </Labelled>
  );
}

export function Select({
  label,
  options,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; options: { value: string; label: string }[] }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-ink-muted">
        {label}
      </label>
      <select id={id} className={`${CONTROL} min-w-40`} {...rest}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Notice({ tone = 'info', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={`mb-4 rounded-lg px-4 py-3 text-sm ${TONES[tone]}`}>
      {children}
    </div>
  );
}

export function errorMessage(error: unknown, fallback = 'Something went wrong.'): string {
  if (error instanceof ApiError) {
    if (error.code === 'validation_error' && error.details.length) {
      return error.details
        .map((d) => `${(d.location as string[] | undefined)?.slice(-1)[0] ?? 'field'}: ${String(d.message).replace(/^Value error, /, '')}`)
        .join('; ');
    }
    return error.message;
  }
  return error instanceof Error ? error.message : fallback;
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <p role="status" className="py-10 text-center text-sm text-ink-muted">
      {label}
    </p>
  );
}

export function LoadError({ error, retry }: { error: Error; retry: () => void }) {
  return (
    <Notice tone="danger">
      {errorMessage(error)}{' '}
      <button type="button" className="font-semibold underline" onClick={retry}>
        Try again
      </button>
    </Notice>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-10 text-center text-sm text-ink-muted">{children}</p>;
}

/** Previous / next for limit-offset lists. `hasMore` when a full page came back. */
export function Pager({ offset, limit, count, total, onChange }: { offset: number; limit: number; count: number; total?: number; onChange: (offset: number) => void }) {
  const hasMore = total !== undefined ? offset + count < total : count === limit;
  if (offset === 0 && !hasMore) return null;
  return (
    <div className="mt-4 flex items-center justify-between text-sm">
      <span className="text-ink-muted">
        {count === 0 ? 'No results' : `${offset + 1}–${offset + count}`}
        {total !== undefined ? ` of ${total}` : ''}
      </span>
      <div className="flex gap-2">
        <Button variant="secondary" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Previous
        </Button>
        <Button variant="secondary" disabled={!hasMore} onClick={() => onChange(offset + limit)}>
          Next
        </Button>
      </div>
    </div>
  );
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-surface-border text-xs uppercase text-ink-muted">
          <tr>
            {head.map((h) => (
              <th key={h} className="px-3 py-2 font-semibold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-border">{children}</tbody>
      </table>
    </div>
  );
}

export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-surface-border py-2 text-sm last:border-0">
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}
