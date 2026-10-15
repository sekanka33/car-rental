/**
 * Charts for the overview. Palette: categorical slots 1 (blue) and 2 (orange), validated with
 * the dataviz palette checker (CVD ΔE 24.7, contrast ≥ 3:1 on the light surface). Bars have
 * rounded data ends, touching segments a 2 px surface gap; the grid is recessive. Every
 * two-series chart has a legend; values are also available as a table below the charts.
 */
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { humanise, monthLabel, zar } from '../lib/format';
import type { MonthRow, Overview } from '../lib/types';
import { Card } from './ui';

export const SERIES = { first: '#2a78d6', second: '#eb6834' };
const SURFACE = '#ffffff';
const GRID = '#e5e7eb';
const AXIS = { fontSize: 12, fill: '#6b7280' };
const TOOLTIP = {
  contentStyle: { borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 },
  cursor: { fill: '#f3f4f6' },
};

const rand = (value: number) => zar(value.toFixed(2));
/** Axis ticks: "R 1.5k", not "R 2k" for 1 500 (rounding made ticks look uneven). */
export const compactRand = (value: number) => (value >= 1000 ? `R ${Number((value / 1000).toFixed(1))}k` : `R ${value}`);

/** Recharts needs numbers; money arrives as exact decimal strings and is only drawn here. */
export function moneyRows(rows: MonthRow[]) {
  return rows.map((r) => ({
    label: monthLabel(r.month),
    Collected: Number(r.collected),
    Refunded: Number(r.refunded),
    net: r.net,
  }));
}

export function MoneyChart({ rows }: { rows: MonthRow[] }) {
  return (
    <figure aria-label="Money collected and refunded per month">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={moneyRows(rows)} barGap={2} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={compactRand} width={56} />
          <Tooltip
            {...TOOLTIP}
            formatter={(value, name) => [rand(Number(value)), String(name)]}
            labelFormatter={(label, payload) => {
              const net = payload?.[0]?.payload?.net as string | undefined;
              return net !== undefined ? `${label} · net ${zar(net)}` : String(label);
            }}
          />
          <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} itemSorter={null} />
          <Bar dataKey="Collected" fill={SERIES.first} radius={[4, 4, 0, 0]} maxBarSize={24} />
          <Bar dataKey="Refunded" fill={SERIES.second} radius={[4, 4, 0, 0]} maxBarSize={24} />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}

export function BookingsChart({ rows }: { rows: MonthRow[] }) {
  const data = rows.map((r) => ({ label: monthLabel(r.month), Bookings: r.bookings_confirmed }));
  return (
    <figure aria-label="Confirmed bookings per month">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} width={32} />
          <Tooltip {...TOOLTIP} />
          <Bar dataKey="Bookings" fill={SERIES.first} radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}

export function SignupsChart({ rows }: { rows: MonthRow[] }) {
  const data = rows.map((r) => ({ label: monthLabel(r.month), Renters: r.new_renters, Owners: r.new_owners }));
  return (
    <figure aria-label="New renter and owner accounts per month">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={GRID} />
          <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} width={32} />
          <Tooltip {...TOOLTIP} />
          <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} itemSorter={null} />
          {/* Stacked: the 2 px surface stroke is the gap between segments. */}
          <Bar dataKey="Renters" stackId="users" fill={SERIES.first} stroke={SURFACE} strokeWidth={2} maxBarSize={28} />
          <Bar dataKey="Owners" stackId="users" fill={SERIES.second} stroke={SURFACE} strokeWidth={2} radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}

/** Current counts per status, as horizontal bars with the count printed at the end. */
export function StatusBars({ counts, label }: { counts: Record<string, number>; label: string }) {
  const data = Object.entries(counts).map(([status, count]) => ({ status: humanise(status), count }));
  return (
    <figure aria-label={label}>
      <ResponsiveContainer width="100%" height={Math.max(160, data.length * 30)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 32, left: 8, bottom: 0 }}>
          <XAxis type="number" hide allowDecimals={false} />
          <YAxis type="category" dataKey="status" tick={AXIS} tickLine={false} axisLine={false} width={132} />
          <Tooltip {...TOOLTIP} />
          <Bar
            dataKey="count"
            name="Count"
            fill={SERIES.first}
            radius={[0, 4, 4, 0]}
            maxBarSize={16}
            label={{ position: 'right', fontSize: 12, fill: '#111827' }}
          />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}

/** All overview charts (the default export, so the page can load this module lazily). */
export default function OverviewCharts({ overview, months }: { overview: Overview; months: MonthRow[] }) {
  return (
    <div className="mt-6 grid gap-4 xl:grid-cols-2">
      <Card title="Money per month" className="xl:col-span-2">
        <p className="-mt-2 mb-3 text-xs text-ink-muted">
          Cash basis: payments in the month received, refunds in the month processed (South African time). Refunds pending
          at Paystack are not yet counted.
        </p>
        <MoneyChart rows={months} />
      </Card>
      <Card title="Confirmed bookings per month">
        <BookingsChart rows={months} />
      </Card>
      <Card title="New accounts per month">
        <SignupsChart rows={months} />
      </Card>
      <Card title="Bookings by status (now)">
        <StatusBars counts={overview.bookings_by_status} label="Bookings by status" />
      </Card>
      <Card title="Vehicles by status (now)">
        <StatusBars counts={overview.vehicles_by_status} label="Vehicles by status" />
      </Card>
    </div>
  );
}
