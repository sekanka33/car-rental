import { useEffect, useState } from 'react';

import { fileUrl } from '../lib/api';
import { Button, errorMessage } from './ui';

/**
 * Shows a private file (ID document, vehicle document, photo) only when the administrator asks
 * for it: the backend records every view in the audit log, so nothing is fetched on page load.
 * The file is held as a blob: URL and released when closed.
 */
export function PrivateFile({ path, label, audited = true }: { path: string; label: string; audited?: boolean }) {
  const [file, setFile] = useState<{ url: string; type: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => () => {
    if (file) URL.revokeObjectURL(file.url);
  }, [file]);

  if (!file) {
    return (
      <div>
        <Button
          variant="secondary"
          busy={busy}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              setFile(await fileUrl(path));
            } catch (e) {
              setError(errorMessage(e));
            } finally {
              setBusy(false);
            }
          }}>
          View {label}
        </Button>
        {audited ? <p className="mt-1 text-xs text-ink-muted">Viewing is recorded in the audit log.</p> : null}
        {error ? <p className="mt-1 text-sm text-danger">{error}</p> : null}
      </div>
    );
  }
  return (
    <figure className="rounded-lg border border-surface-border p-2">
      {file.type === 'application/pdf' ? (
        <iframe title={label} src={file.url} className="h-96 w-full rounded" />
      ) : (
        <img src={file.url} alt={label} className="max-h-96 w-full rounded object-contain" />
      )}
      <figcaption className="mt-2 flex items-center justify-between text-xs text-ink-muted">
        {label}
        <Button variant="ghost" onClick={() => setFile(null)}>
          Close
        </Button>
      </figcaption>
    </figure>
  );
}
