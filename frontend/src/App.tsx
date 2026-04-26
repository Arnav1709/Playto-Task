import {
  AlertCircle,
  ArrowDownToLine,
  Building2,
  CheckCircle2,
  Clock3,
  Landmark,
  Loader2,
  RefreshCw,
  Send,
  Wallet,
} from 'lucide-react';
import { FormEvent, useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

type Merchant = {
  id: string;
  name: string;
  email: string;
};

type BankAccount = {
  id: string;
  account_holder_name: string;
  bank_name: string;
  masked_account_number: string;
  ifsc: string;
};

type LedgerEntry = {
  id: string;
  entry_type: 'credit' | 'debit' | 'release';
  amount_paise: number;
  signed_amount_paise: number;
  description: string;
  payout_id: string | null;
  created_at: string;
};

type Payout = {
  id: string;
  amount_paise: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  attempt_count: number;
  bank_account: BankAccount;
  failure_reason: string;
  created_at: string;
  updated_at: string;
};

type Dashboard = {
  merchant: Merchant;
  available_balance_paise: number;
  held_balance_paise: number;
  total_balance_paise: number;
  bank_accounts: BankAccount[];
  recent_ledger_entries: LedgerEntry[];
  recent_payouts: Payout[];
};

type ApiError = {
  error: string;
  message: string;
};

function formatMoney(amountPaise: number): string {
  const sign = amountPaise < 0 ? '-' : '';
  const absolute = Math.abs(amountPaise);
  const rupees = Math.floor(absolute / 100);
  const paise = String(absolute % 100).padStart(2, '0');
  return `${sign}₹${rupees.toLocaleString('en-IN')}.${paise}`;
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat('en-IN', {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function parseRupeesToPaise(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+(\.\d{0,2})?$/.test(trimmed)) {
    return null;
  }
  const [rupees, paise = ''] = trimmed.split('.');
  const paisePart = (paise + '00').slice(0, 2);
  const amount = Number(rupees) * 100 + Number(paisePart);
  return Number.isSafeInteger(amount) && amount > 0 ? amount : null;
}

async function apiFetch<T>(path: string, merchantId?: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');
  if (merchantId) {
    headers.set('X-Merchant-ID', merchantId);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const body = await response.json();
  if (!response.ok) {
    const errorBody = body as ApiError;
    throw new Error(errorBody.message || errorBody.error || 'Request failed');
  }
  return body as T;
}

function StatusBadge({ status }: { status: Payout['status'] }) {
  const styles = {
    pending: 'bg-amber-100 text-amber-800 border-amber-200',
    processing: 'bg-sky-100 text-sky-800 border-sky-200',
    completed: 'bg-emerald-100 text-emerald-800 border-emerald-200',
    failed: 'bg-rose-100 text-rose-800 border-rose-200',
  }[status];

  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold ${styles}`}>
      {status}
    </span>
  );
}

function BalanceTile({
  label,
  caption,
  amount,
  icon,
  tone,
}: {
  label: string;
  caption: string;
  amount: number;
  icon: React.ReactNode;
  tone: string;
}) {
  return (
    <section className="panel min-h-32 p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-ink-500">{label}</span>
        <span className={`grid h-10 w-10 place-items-center rounded-md ${tone}`}>{icon}</span>
      </div>
      <p className="mt-6 font-display text-3xl font-semibold text-ink-950">{formatMoney(amount)}</p>
      <p className="mt-2 text-sm font-medium text-ink-500">{caption}</p>
    </section>
  );
}

function EmptyRow({ label }: { label: string }) {
  return <div className="border-t border-ink-100 px-4 py-8 text-center text-sm text-ink-500">{label}</div>;
}

export default function App() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [selectedMerchantId, setSelectedMerchantId] = useState<string>('');
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [amount, setAmount] = useState('');
  const [bankAccountId, setBankAccountId] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const activeBankAccounts = dashboard?.bank_accounts ?? [];

  async function loadMerchants() {
    const data = await apiFetch<{ merchants: Merchant[] }>('/api/v1/merchants');
    setMerchants(data.merchants);
    setSelectedMerchantId((current) => current || data.merchants[0]?.id || '');
  }

  async function loadDashboard(merchantId: string) {
    const data = await apiFetch<Dashboard>('/api/v1/merchant/dashboard', merchantId);
    setDashboard(data);
    setBankAccountId((current) => current || data.bank_accounts[0]?.id || '');
  }

  useEffect(() => {
    loadMerchants().catch((error) => setNotice({ type: 'error', message: error.message })).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedMerchantId) {
      return;
    }
    loadDashboard(selectedMerchantId).catch((error) => setNotice({ type: 'error', message: error.message }));
    const timer = window.setInterval(() => {
      loadDashboard(selectedMerchantId).catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [selectedMerchantId]);

  useEffect(() => {
    if (!activeBankAccounts.some((account) => account.id === bankAccountId)) {
      setBankAccountId(activeBankAccounts[0]?.id || '');
    }
  }, [activeBankAccounts, bankAccountId]);

  const selectedMerchant = useMemo(
    () => merchants.find((merchant) => merchant.id === selectedMerchantId),
    [merchants, selectedMerchantId],
  );

  async function submitPayout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedMerchantId) {
      return;
    }
    const amountPaise = parseRupeesToPaise(amount);
    if (!amountPaise) {
      setNotice({ type: 'error', message: 'Enter an INR amount with up to two decimal places.' });
      return;
    }
    if (!bankAccountId) {
      setNotice({ type: 'error', message: 'Select a bank account.' });
      return;
    }

    setSubmitting(true);
    setNotice(null);
    try {
      await apiFetch('/api/v1/payouts', selectedMerchantId, {
        method: 'POST',
        headers: {
          'Idempotency-Key': crypto.randomUUID(),
        },
        body: JSON.stringify({
          amount_paise: amountPaise,
          bank_account_id: bankAccountId,
        }),
      });
      setAmount('');
      setNotice({ type: 'success', message: 'Payout request created. That money is now being paid out.' });
      await loadDashboard(selectedMerchantId);
    } catch (error) {
      setNotice({ type: 'error', message: error instanceof Error ? error.message : 'Payout failed.' });
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-paper text-ink-900">
        <Loader2 className="h-8 w-8 animate-spin text-mint-700" />
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-paper text-ink-950">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-ink-200 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-mint-800">
              <Landmark className="h-4 w-4" />
              Playto Payout Engine
            </div>
            <h1 className="font-display text-4xl font-semibold leading-tight text-ink-950">Merchant ledger console</h1>
          </div>
          <label className="flex min-w-72 flex-col gap-2 text-sm font-semibold text-ink-700">
            Merchant
            <select
              className="h-11 rounded-md border border-ink-300 bg-white px-3 text-sm text-ink-950 outline-none transition focus:border-mint-700 focus:ring-4 focus:ring-mint-100"
              value={selectedMerchantId}
              onChange={(event) => {
                setSelectedMerchantId(event.target.value);
                setDashboard(null);
                setNotice(null);
                setBankAccountId('');
              }}
            >
              {merchants.map((merchant) => (
                <option key={merchant.id} value={merchant.id}>
                  {merchant.name}
                </option>
              ))}
            </select>
          </label>
        </header>

        {notice && (
          <div
            className={`flex items-center gap-3 rounded-md border px-4 py-3 text-sm font-medium ${
              notice.type === 'success'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
                : 'border-rose-200 bg-rose-50 text-rose-900'
            }`}
          >
            {notice.type === 'success' ? <CheckCircle2 className="h-5 w-5" /> : <AlertCircle className="h-5 w-5" />}
            {notice.message}
          </div>
        )}

        <section className="grid gap-4 md:grid-cols-3">
          <BalanceTile
            label="Ready to withdraw"
            caption="Can be requested right now"
            amount={dashboard?.available_balance_paise ?? 0}
            icon={<Wallet className="h-5 w-5" />}
            tone="bg-mint-100 text-mint-800"
          />
          <BalanceTile
            label="Being paid out"
            caption="Requested, waiting on bank result"
            amount={dashboard?.held_balance_paise ?? 0}
            icon={<Clock3 className="h-5 w-5" />}
            tone="bg-amber-100 text-amber-800"
          />
          <BalanceTile
            label="Still with Playto"
            caption="Ready to withdraw + being paid out"
            amount={dashboard?.total_balance_paise ?? 0}
            icon={<Building2 className="h-5 w-5" />}
            tone="bg-ink-100 text-ink-800"
          />
        </section>

        <section className="grid gap-4 lg:grid-cols-[380px_1fr]">
          <form className="panel p-5" onSubmit={submitPayout}>
            <div className="mb-6 flex items-center justify-between">
              <h2 className="font-display text-xl font-semibold">Request payout</h2>
              <Send className="h-5 w-5 text-mint-700" />
            </div>

            <div className="space-y-4">
              <label className="block text-sm font-semibold text-ink-700">
                Amount
                <div className="mt-2 flex h-11 items-center rounded-md border border-ink-300 bg-white focus-within:border-mint-700 focus-within:ring-4 focus-within:ring-mint-100">
                  <span className="pl-3 text-ink-500">₹</span>
                  <input
                    className="h-full min-w-0 flex-1 rounded-md bg-transparent px-2 text-sm outline-none"
                    inputMode="decimal"
                    placeholder="6000.00"
                    value={amount}
                    onChange={(event) => setAmount(event.target.value)}
                  />
                </div>
              </label>

              <label className="block text-sm font-semibold text-ink-700">
                Bank account
                <select
                  className="mt-2 h-11 w-full rounded-md border border-ink-300 bg-white px-3 text-sm outline-none transition focus:border-mint-700 focus:ring-4 focus:ring-mint-100"
                  value={bankAccountId}
                  onChange={(event) => setBankAccountId(event.target.value)}
                >
                  {activeBankAccounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.bank_name} · {account.masked_account_number}
                    </option>
                  ))}
                </select>
              </label>

              <button
                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-ink-950 px-4 text-sm font-semibold text-white transition hover:bg-mint-800 focus:outline-none focus:ring-4 focus:ring-mint-200 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={submitting || !dashboard}
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowDownToLine className="h-4 w-4" />}
                Submit payout
              </button>
            </div>

            {selectedMerchant && (
              <p className="mt-5 border-t border-ink-100 pt-4 text-xs leading-5 text-ink-500">
                {selectedMerchant.email}
              </p>
            )}
          </form>

          <section className="panel overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4">
              <h2 className="font-display text-xl font-semibold">Payout history</h2>
              <RefreshCw className="h-4 w-4 text-ink-500" />
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-y border-ink-100 bg-ink-50 text-xs uppercase tracking-[0.16em] text-ink-500">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Amount</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">Bank</th>
                    <th className="px-4 py-3 font-semibold">Attempts</th>
                    <th className="px-4 py-3 font-semibold">Updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  {dashboard?.recent_payouts.map((payout) => (
                    <tr key={payout.id} className="bg-white">
                      <td className="px-4 py-4 font-semibold text-ink-950">{formatMoney(payout.amount_paise)}</td>
                      <td className="px-4 py-4">
                        <StatusBadge status={payout.status} />
                      </td>
                      <td className="px-4 py-4 text-ink-600">
                        {payout.bank_account.bank_name} {payout.bank_account.masked_account_number}
                      </td>
                      <td className="px-4 py-4 text-ink-600">{payout.attempt_count}</td>
                      <td className="px-4 py-4 text-ink-600">{formatTime(payout.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {dashboard?.recent_payouts.length === 0 && <EmptyRow label="No payouts yet" />}
          </section>
        </section>

        <section className="panel overflow-hidden">
          <div className="px-5 py-4">
            <h2 className="font-display text-xl font-semibold">Recent ledger entries</h2>
          </div>
          <div className="grid border-t border-ink-100 md:grid-cols-2 xl:grid-cols-3">
            {dashboard?.recent_ledger_entries.map((entry) => (
              <article key={entry.id} className="min-h-28 border-b border-r border-ink-100 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <span className="rounded-md border border-ink-200 px-2 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-ink-600">
                    {entry.entry_type}
                  </span>
                  <span className={`font-semibold ${entry.signed_amount_paise < 0 ? 'text-rose-700' : 'text-mint-800'}`}>
                    {formatMoney(entry.signed_amount_paise)}
                  </span>
                </div>
                <p className="text-sm font-medium text-ink-800">{entry.description}</p>
                <p className="mt-3 text-xs text-ink-500">{formatTime(entry.created_at)}</p>
              </article>
            ))}
          </div>
          {dashboard?.recent_ledger_entries.length === 0 && <EmptyRow label="No ledger entries yet" />}
        </section>
      </div>
    </main>
  );
}
