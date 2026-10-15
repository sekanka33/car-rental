import { type FormEvent, useState } from 'react';

import { Button, errorMessage, Input, Notice } from '../components/ui';
import { useAuth } from '../lib/auth';

export function LoginPage({ expired = false }: { expired?: boolean }) {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (e) {
      setError(errorMessage(e, 'Could not sign in.'));
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <form onSubmit={submit} className="w-full max-w-sm rounded-xl border border-surface-border bg-white p-8" noValidate>
        <h1 className="text-xl font-bold">CarHire SA Admin</h1>
        <p className="mb-6 mt-1 text-sm text-ink-muted">Administrator accounts only.</p>
        {expired ? <Notice tone="warning">Your session ended. Please sign in again.</Notice> : null}
        {error ? <Notice tone="danger">{error}</Notice> : null}
        <Input label="Email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <Button type="submit" busy={busy} className="w-full" disabled={!email || !password}>
          Sign in
        </Button>
      </form>
    </div>
  );
}
