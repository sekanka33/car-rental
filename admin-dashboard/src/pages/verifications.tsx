import { useState } from 'react';
import { Link, useParams } from 'react-router';

import { AuditTrail } from '../components/audit-trail';
import { PrivateFile } from '../components/private-file';
import {
  Button,
  Card,
  Empty,
  errorMessage,
  Input,
  Loading,
  LoadError,
  Notice,
  PageHeader,
  Pager,
  Row,
  Select,
  StatusBadge,
  Table,
  TextArea,
} from '../components/ui';
import { get, post } from '../lib/api';
import { dateOnly, dateTime, SUBMISSION_TONE } from '../lib/format';
import type { Submission } from '../lib/types';
import { useFilters } from '../lib/use-filters';
import { useLoad } from '../lib/use-load';

const LIMIT = 25;
const TYPE_LABEL = { SA_ID: 'SA ID', DRIVING_LICENCE: 'Driving licence' };
const STATUSES = ['PENDING', 'REQUIRES_MORE_INFORMATION', 'APPROVED', 'REJECTED', 'SUPERSEDED'];

export function VerificationsPage() {
  const filters = useFilters(['status'] as const);
  const status = filters.values.status || 'PENDING';
  const list = useLoad(
    () => get<Submission[]>('/admin/verifications', { status, limit: LIMIT, offset: filters.offset }),
    filters.key,
  );
  return (
    <>
      <PageHeader title="Identity verification" subtitle="Check each renter's SA ID and driving licence against the uploaded document." />
      <Card
        actions={
          <Select
            label="Status"
            value={status}
            onChange={(e) => filters.set('status', e.target.value)}
            options={STATUSES.map((s) => ({ value: s, label: s.replace(/_/g, ' ').toLowerCase() }))}
          />
        }>
        {list.status === 'loading' ? <Loading /> : null}
        {list.status === 'error' ? <LoadError error={list.error} retry={list.reload} /> : null}
        {list.status === 'ready' ? (
          list.data.length === 0 ? (
            <Empty>Nothing here.</Empty>
          ) : (
            <>
              <Table head={['Submitted', 'Renter', 'Document', 'Number', 'Status']}>
                {list.data.map((s) => (
                  <tr key={s.id} className="hover:bg-surface-muted">
                    <td className="px-3 py-2">{dateTime(s.submitted_at)}</td>
                    <td className="px-3 py-2">
                      <Link className="font-medium text-brand-600" to={`/verifications/${s.id}`}>
                        {s.submitter.full_name}
                      </Link>
                      <div className="text-xs text-ink-muted">{s.submitter.email}</div>
                    </td>
                    <td className="px-3 py-2">{TYPE_LABEL[s.document_type]}</td>
                    <td className="px-3 py-2 font-mono">{s.document_number_masked}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={s.status} tones={SUBMISSION_TONE} />
                    </td>
                  </tr>
                ))}
              </Table>
              <Pager offset={filters.offset} limit={LIMIT} count={list.data.length} onChange={filters.setOffset} />
            </>
          )
        ) : null}
      </Card>
    </>
  );
}

type Decision = 'APPROVED' | 'REJECTED' | 'REQUIRES_MORE_INFORMATION';

/** Validates a review decision the way the backend does (a note is required unless approving). */
export function checkDecision(decision: Decision, note: string, isLicence: boolean, expiry: string, today: string): string | null {
  if (decision !== 'APPROVED' && note.trim().length < 3) return 'Explain to the renter what is wrong (at least 3 characters).';
  if (decision === 'APPROVED' && isLicence && expiry && expiry <= today) return 'The licence expiry must be in the future.';
  return null;
}

function DecisionForm({ submission, onDone }: { submission: Submission; onDone: () => void }) {
  const isLicence = submission.document_type === 'DRIVING_LICENCE';
  const [note, setNote] = useState('');
  const [expiry, setExpiry] = useState(submission.licence_expiry_date ?? '');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Decision | null>(null);

  const decide = async (decision: Decision) => {
    const problem = checkDecision(decision, note, isLicence, expiry, new Date().toISOString().slice(0, 10));
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(decision);
    setError(null);
    try {
      await post(`/admin/verifications/${submission.id}/decision`, {
        decision,
        note: note.trim() || null,
        licence_expiry_date: isLicence && decision === 'APPROVED' && expiry ? expiry : null,
      });
      onDone();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card title="Decision">
      {error ? <Notice tone="danger">{error}</Notice> : null}
      {isLicence ? (
        <Input
          label="Licence expiry (as printed on the card)"
          type="date"
          value={expiry}
          onChange={(e) => setExpiry(e.target.value)}
          hint="Bookings that end after this date are refused."
        />
      ) : null}
      <TextArea
        label="Note to the renter"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        maxLength={1000}
        hint="Required when rejecting or asking for more information. The renter sees it."
      />
      <div className="flex flex-wrap gap-2">
        <Button busy={busy === 'APPROVED'} disabled={busy !== null} onClick={() => decide('APPROVED')}>
          Approve
        </Button>
        <Button variant="secondary" busy={busy === 'REQUIRES_MORE_INFORMATION'} disabled={busy !== null} onClick={() => decide('REQUIRES_MORE_INFORMATION')}>
          Ask for more information
        </Button>
        <Button variant="danger" busy={busy === 'REJECTED'} disabled={busy !== null} onClick={() => decide('REJECTED')}>
          Reject
        </Button>
      </div>
    </Card>
  );
}

export function VerificationDetailPage() {
  const { id = '' } = useParams();
  const submission = useLoad(() => get<Submission>(`/admin/verifications/${id}`), id);
  const [version, setVersion] = useState(0);

  if (submission.status === 'loading') return <Loading />;
  if (submission.status === 'error') return <LoadError error={submission.error} retry={submission.reload} />;
  const s = submission.data;
  const done = () => {
    submission.reload();
    setVersion((v) => v + 1);
  };
  return (
    <>
      <PageHeader
        title={`${TYPE_LABEL[s.document_type]} · ${s.submitter.full_name}`}
        subtitle={s.submitter.email}
        actions={<StatusBadge status={s.status} tones={SUBMISSION_TONE} />}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <Card title="Submission">
            <dl>
              <Row label="Document number">
                <span className="font-mono">{s.document_number_masked}</span> (only the last digits are stored)
              </Row>
              <Row label="Date of birth on profile">{dateOnly(s.submitter.date_of_birth)}</Row>
              {s.document_type === 'DRIVING_LICENCE' ? (
                <>
                  <Row label="Expiry given by renter">{dateOnly(s.licence_expiry_date)}</Row>
                  <Row label="Licence codes">{s.licence_codes ?? '—'}</Row>
                </>
              ) : null}
              <Row label="Submitted">{dateTime(s.submitted_at)}</Row>
              <Row label="Reviewed">{dateTime(s.reviewed_at)}</Row>
              {s.review_note ? <Row label="Review note">{s.review_note}</Row> : null}
            </dl>
          </Card>
          {s.status === 'PENDING' ? <DecisionForm submission={s} onDone={done} /> : null}
          <AuditTrail entityType="verification_submission" entityId={s.id} version={version} />
        </div>
        <Card title="Document">
          <p className="mb-3 text-sm text-ink-muted">
            Check that the name and date of birth match the profile, and that the number ends in the digits above.
          </p>
          <div className="space-y-4">
            {s.files.map((f) => (
              <PrivateFile key={f.id} path={`/admin/verifications/${s.id}/files/${f.id}`} label={`${f.side.toLowerCase()} side`} />
            ))}
          </div>
        </Card>
      </div>
    </>
  );
}
