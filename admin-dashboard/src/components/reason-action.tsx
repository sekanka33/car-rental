import { useState } from 'react';

import { Button, errorMessage, Notice, TextArea } from './ui';

/**
 * A button that opens a short form asking for a reason, then runs `onSubmit(reason)`. Used for
 * every action the backend audits with a reason (reject, suspend, cancel, refund…).
 */
export function ReasonAction({
  label,
  confirmLabel = label,
  variant = 'danger',
  reasonLabel = 'Reason (recorded in the audit log)',
  explanation,
  minLength = 3,
  onSubmit,
}: {
  label: string;
  confirmLabel?: string;
  variant?: 'primary' | 'danger' | 'secondary';
  reasonLabel?: string;
  explanation?: string;
  minLength?: number;
  onSubmit: (reason: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!open) {
    return (
      <Button variant={variant === 'danger' ? 'secondary' : variant} onClick={() => setOpen(true)}>
        {label}
      </Button>
    );
  }
  const submit = async () => {
    if (reason.trim().length < minLength) {
      setError(`Give a reason of at least ${minLength} characters.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit(reason.trim());
      setOpen(false);
      setReason('');
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="w-full rounded-lg border border-surface-border bg-surface-muted p-4">
      {explanation ? <Notice tone="warning">{explanation}</Notice> : null}
      <TextArea label={reasonLabel} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} error={error} />
      <div className="flex gap-2">
        <Button variant={variant} busy={busy} onClick={submit}>
          {confirmLabel}
        </Button>
        <Button variant="secondary" onClick={() => setOpen(false)} disabled={busy}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
