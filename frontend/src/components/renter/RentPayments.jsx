/**
 * DORMORA — SYSTEM FUNCTIONALITY FILE 48
 * CREATE: frontend/src/components/renter/RentPayments.jsx
 *
 * Renter-only read-only monthly rent charges and balances.
 * GET /api/rent-records/mine (Files 43–45).
 * File 50 will connect this component to RoleHome's Rent Payments page.
 *
 * No payment recording or online money transfers occur here.
 * The property owner records payments received outside Dormora.
 */

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle, ArrowLeft, Building2, CalendarDays, CheckCircle2,
  Clock3, CreditCard, FileText, RefreshCw, Search, ShieldCheck,
  Wallet, X,
} from "lucide-react";

const API_URL = "http://localhost:8000/api/rent-records/mine";

const STATUS = {
  pending: { label: "Pending", icon: Clock3 },
  partially_paid: { label: "Partially Paid", icon: Wallet },
  paid: { label: "Paid", icon: CheckCircle2 },
  overdue: { label: "Overdue", icon: AlertCircle },
};

const styles = `
.rp-page{width:100%;min-width:0;color:var(--text);font-family:inherit}
.rp-page *{box-sizing:border-box}
.rp-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap;margin-bottom:22px}
.rp-head h1{margin:0 0 7px;font-size:clamp(25px,3vw,32px);font-weight:850}
.rp-muted,.rp-head p{color:var(--muted);font-size:13px;line-height:1.7;margin:0}
.rp-actions{display:flex;flex-wrap:wrap;gap:9px}
.rp-btn{border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:10px 14px;min-height:42px;font:inherit;font-size:13px;font-weight:750;cursor:pointer}
.rp-btn:hover:not(:disabled){filter:brightness(.97)}.rp-btn:disabled{opacity:.55;cursor:not-allowed}
.rp-btn.primary{background:var(--primary);color:var(--background);border-color:var(--primary)}
.rp-page button:focus-visible,.rp-page input:focus-visible,.rp-page select:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.rp-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin-bottom:18px}
.rp-stat{min-width:0;padding:19px;background:var(--card);border:1px solid var(--border);border-radius:15px}
.rp-stat-label{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)}
.rp-stat-label svg{color:var(--primary)}
.rp-stat-value{font-size:clamp(19px,2.25vw,25px);font-weight:850;margin-top:12px;overflow-wrap:anywhere}
.rp-stat-help{margin-top:5px;font-size:11px;color:var(--muted);line-height:1.5}
.rp-panel{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:21px;margin-bottom:19px}
.rp-panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.rp-panel h2{margin:0;font-size:18px;font-weight:800;display:flex;align-items:center;gap:9px}
.rp-panel h2 svg{color:var(--primary)}
.rp-toolbar{display:flex;align-items:center;flex-wrap:wrap;gap:11px;margin-bottom:13px}
.rp-search{flex:1;min-width:210px;display:flex;align-items:center;gap:9px;padding:0 12px;border:1px solid var(--border);border-radius:10px;background:var(--background);color:var(--muted)}
.rp-search input{flex:1;min-width:0;padding:12px 0;border:0;outline:0;background:transparent;color:var(--text);font:inherit;font-size:13px}
.rp-search button{border:0;padding:5px;display:grid;place-items:center;background:transparent;color:var(--muted);cursor:pointer}
.rp-select{min-height:43px;max-width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:10px;background:var(--background);color:var(--text);font:inherit;font-size:13px}
.rp-resultcount{color:var(--muted);font-size:12px;margin:0 0 14px}
.rp-list{display:grid;gap:13px}
.rp-entry{padding:18px;border-radius:13px;background:var(--background);border:1px solid var(--border);min-width:0}
.rp-entry-head{display:flex;justify-content:space-between;align-items:flex-start;gap:13px;flex-wrap:wrap;margin-bottom:16px}
.rp-entry h3{font-size:17px;margin:0 0 7px;font-weight:800;overflow-wrap:anywhere}
.rp-entry-sub{display:flex;align-items:center;gap:6px;flex-wrap:wrap;color:var(--muted);font-size:12px;line-height:1.65}
.rp-badge{display:inline-flex;align-items:center;gap:6px;padding:8px 10px;background:var(--soft);color:var(--primary);border-radius:9px;white-space:nowrap;font-weight:800;font-size:11px}
.rp-badge.overdue{color:#b45309}.rp-badge.pending{color:var(--muted)}
.rp-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding-top:14px;border-top:1px solid var(--border)}
.rp-label{display:block;margin-bottom:6px;font-size:11px;color:var(--muted)}
.rp-field-value{font-weight:800;font-size:16px;overflow-wrap:anywhere}
.rp-balance{color:var(--primary)}
.rp-progress-title{display:flex;justify-content:space-between;gap:10px;align-items:center;margin:16px 0 7px;color:var(--muted);font-size:11px}
.rp-track{width:100%;height:9px;border-radius:20px;background:var(--soft);overflow:hidden}
.rp-bar{height:100%;background:var(--primary);border-radius:20px;transition:width .2s}
.rp-foot{display:flex;gap:8px;align-items:flex-start;color:var(--muted);font-size:12px;line-height:1.65;margin-top:14px}
.rp-foot svg{flex-shrink:0;color:var(--primary);margin-top:2px}
.rp-notice{display:flex;gap:10px;align-items:flex-start;padding:13px 14px;background:var(--soft);border:1px solid var(--border);border-radius:11px;color:var(--muted);font-size:12px;line-height:1.7;margin-top:17px}
.rp-notice svg{color:var(--primary);flex-shrink:0;margin-top:2px}
.rp-state{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:11px;text-align:center;padding:38px 22px;min-height:195px;background:var(--card);border:1px dashed var(--border);border-radius:14px}
.rp-state svg{color:var(--primary)}.rp-state h3{font-size:17px;margin:0}
.rp-state p{font-size:13px;line-height:1.7;color:var(--muted);max-width:500px;margin:0}
@media(max-width:1080px){.rp-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:650px){.rp-head{flex-direction:column}.rp-summary,.rp-fields{grid-template-columns:1fr}.rp-panel{padding:15px}.rp-search,.rp-select{width:100%}.rp-entry{padding:14px}.rp-stat{padding:15px}}
`;

function cents(value) {
  const raw = String(value ?? "").trim();
  if (!/^[0-9]{1,10}(?:\.[0-9]{1,2})?$/.test(raw)) return null;
  const [whole, fraction = ""] = raw.split(".");
  const result = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return Number.isSafeInteger(result) ? result : null;
}

function pesoFromCents(value) {
  if (value === null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-PH", {
    style: "currency", currency: "PHP", minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value / 100);
}

function peso(value) {
  return pesoFromCents(cents(value));
}

function formatDate(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return "Not recorded";
  const [year, month, day] = match.slice(1).map(Number);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return "Not recorded";
  }
  return new Intl.DateTimeFormat("en-PH", {
    month: "short", day: "numeric", year: "numeric",
  }).format(date);
}

function formatMonth(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-01$/);
  if (!match) return "Unknown billing month";
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (month < 1 || month > 12) return "Unknown billing month";
  return new Intl.DateTimeFormat("en-PH", { month: "long", year: "numeric" })
    .format(new Date(year, month - 1, 1));
}

function requestError(response, data) {
  if (response.status === 401) return "Your session expired. Please sign in again.";
  if (response.status === 403) return "Rent Payments is available to active renter accounts only.";
  if (response.status === 429) return "Too many requests. Please refresh later.";
  if (response.status < 500 && typeof data?.detail === "string") return data.detail;
  return "Unable to load rent records. Check that Dormora's backend is running.";
}

function StatusPill({ status }) {
  const item = STATUS[status] || STATUS.pending;
  const Icon = item.icon;
  return <span className={`rp-badge ${status || "pending"}`}><Icon size={14} />{item.label}</span>;
}

function StatePanel({ icon: Icon, heading, description, children }) {
  return (
    <div className="rp-state">
      <Icon size={32} />
      <h3>{heading}</h3>
      <p>{description}</p>
      {children}
    </div>
  );
}

function ChargeCard({ record }) {
  const due = cents(record.amount_due);
  const paid = cents(record.total_paid);
  const balance = cents(record.balance_due);
  const progress = due !== null && due > 0 && paid !== null
    ? Math.min(100, Math.max(0, (paid / due) * 100))
    : 0;

  return (
    <article className="rp-entry">
      <div className="rp-entry-head">
        <div>
          <h3>{record.property_name || `Property #${record.property_id}`}</h3>
          <div className="rp-entry-sub">
            <Building2 size={14} />
            <span>{record.room_label || "Room not listed"} · {formatMonth(record.billing_month)}</span>
          </div>
          <div className="rp-entry-sub">
            <CalendarDays size={14} />
            <span>Due {formatDate(record.due_date)} · Charge #{record.charge_id}</span>
          </div>
        </div>
        <StatusPill status={record.payment_status} />
      </div>
      <div className="rp-fields">
        <div><span className="rp-label">Monthly Rent Due</span><div className="rp-field-value">{peso(record.amount_due)}</div></div>
        <div><span className="rp-label">Total Paid (Owner Recorded)</span><div className="rp-field-value">{peso(record.total_paid)}</div></div>
        <div><span className="rp-label">Remaining Balance</span><div className="rp-field-value rp-balance">{peso(record.balance_due)}</div></div>
      </div>
      <div className="rp-progress-title">
        <span>Payment progress</span>
        <span>{Math.round(progress)}% recorded</span>
      </div>
      <div
        className="rp-track" role="progressbar"
        aria-label={`Payment progress for ${formatMonth(record.billing_month)}`}
        aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}
      >
        <div className="rp-bar" style={{ width: `${progress}%` }} />
      </div>
      {record.payment_status === "overdue" && (
        <div className="rp-foot"><AlertCircle size={16} />This charge has an outstanding balance past its due date.</div>
      )}
      {record.payment_status === "paid" && (
        <div className="rp-foot"><CheckCircle2 size={16} />Fully paid. This record remains visible for your reference.</div>
      )}
    </article>
  );
}

export default function RentPayments({ account, onBack }) {
  const isRenter = account?.role === "renter";
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(isRenter);
  const [error, setError] = useState("");
  const [refreshCount, setRefreshCount] = useState(0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  useEffect(() => {
    if (!isRenter) {
      setRecords([]);
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setLoading(true);
    setError("");

    async function loadRecords() {
      try {
        const response = await fetch(API_URL, {
          method: "GET", credentials: "include", mode: "cors",
          cache: "no-store", redirect: "error", signal: controller.signal,
        });
        let data = null;
        try { data = await response.json(); } catch { /* Ignore non-JSON server errors. */ }
        if (!response.ok) throw new Error(requestError(response, data));
        if (!Array.isArray(data?.records)) {
          throw new Error("The backend returned an unexpected rent-record response.");
        }
        if (!controller.signal.aborted) setRecords(data.records);
      } catch (caught) {
        if (!controller.signal.aborted) {
          setRecords([]);
          setError(caught instanceof Error ? caught.message : "Unable to load rent records.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    loadRecords();
    return () => controller.abort();
  }, [isRenter, refreshCount]);

  const summary = useMemo(() => {
    let amountDue = 0;
    let totalPaid = 0;
    let outstanding = 0;
    let overdue = 0;
    for (const record of records) {
      amountDue += cents(record.amount_due) ?? 0;
      totalPaid += cents(record.total_paid) ?? 0;
      outstanding += cents(record.balance_due) ?? 0;
      if (record.payment_status === "overdue") overdue += 1;
    }
    return { amountDue, totalPaid, outstanding, overdue };
  }, [records]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return records.filter((record) => {
      if (statusFilter !== "all" && record.payment_status !== statusFilter) return false;
      if (!query) return true;
      return [record.property_name, record.room_label, record.billing_month, record.charge_id]
        .some((part) => String(part ?? "").toLowerCase().includes(query));
    });
  }, [records, search, statusFilter]);

  return (
    <section className="rp-page" aria-label="Rent Payments">
      <style>{styles}</style>
      <div className="rp-head">
        <div>
          <h1>Rent Payments</h1>
          <p>Track your monthly charges, amounts recorded as paid, and outstanding balances.</p>
        </div>
        <div className="rp-actions">
          {typeof onBack === "function" && (
            <button className="rp-btn" type="button" onClick={onBack}>
              <ArrowLeft size={17} /> Home
            </button>
          )}
          {isRenter && (
            <button className="rp-btn" type="button" disabled={loading}
              onClick={() => setRefreshCount((count) => count + 1)}>
              <RefreshCw size={16} /> Refresh
            </button>
          )}
        </div>
      </div>

      {!isRenter ? (
        <StatePanel icon={ShieldCheck} heading="Renter access required"
          description="Only authenticated renter accounts can view their personal rent records." />
      ) : loading ? (
        <StatePanel icon={RefreshCw} heading="Loading rent records"
          description="Retrieving your latest rent charges and balances from Dormora." />
      ) : error ? (
        <StatePanel icon={AlertCircle} heading="Unable to load rent records" description={error}>
          <button className="rp-btn primary" type="button"
            onClick={() => setRefreshCount((count) => count + 1)}>
            <RefreshCw size={16} /> Try Again
          </button>
        </StatePanel>
      ) : (
        <>
          <div className="rp-summary" aria-label="Rent account summary">
            <div className="rp-stat">
              <div className="rp-stat-label"><FileText size={18} /> Total Charges</div>
              <div className="rp-stat-value">{pesoFromCents(summary.amountDue)}</div>
              <div className="rp-stat-help">Across all displayed rental periods</div>
            </div>
            <div className="rp-stat">
              <div className="rp-stat-label"><CheckCircle2 size={18} /> Total Recorded Paid</div>
              <div className="rp-stat-value">{pesoFromCents(summary.totalPaid)}</div>
              <div className="rp-stat-help">Confirmed by property owners</div>
            </div>
            <div className="rp-stat">
              <div className="rp-stat-label"><Wallet size={18} /> Outstanding Balance</div>
              <div className="rp-stat-value">{pesoFromCents(summary.outstanding)}</div>
              <div className="rp-stat-help">Across your rent charges</div>
            </div>
            <div className="rp-stat">
              <div className="rp-stat-label"><Clock3 size={18} /> Overdue Charges</div>
              <div className="rp-stat-value">{summary.overdue}</div>
              <div className="rp-stat-help">Unpaid balances past due</div>
            </div>
          </div>

          <div className="rp-panel">
            <div className="rp-panel-head">
              <h2><CreditCard size={21} /> Monthly Rent Charges</h2>
            </div>
            <div className="rp-toolbar">
              <label className="rp-search">
                <Search size={18} />
                <input type="search" aria-label="Search rent records"
                  placeholder="Search property, room, or billing month"
                  maxLength={100} value={search}
                  onChange={(event) => setSearch(event.target.value)} />
                {search && <button type="button" aria-label="Clear search"
                  onClick={() => setSearch("")}><X size={15} /></button>}
              </label>
              <select className="rp-select" aria-label="Filter rent status" value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="all">All statuses</option>
                <option value="pending">Pending</option>
                <option value="partially_paid">Partially Paid</option>
                <option value="overdue">Overdue</option>
                <option value="paid">Paid</option>
              </select>
            </div>
            <p className="rp-resultcount">{filtered.length} of {records.length} rent charges shown</p>

            {records.length === 0 ? (
              <StatePanel icon={CalendarDays} heading="No rent charges yet"
                description="Your property owner has not created a monthly rent charge. Your assigned room can still appear in My Rental." />
            ) : filtered.length === 0 ? (
              <StatePanel icon={Search} heading="No matching rent charges"
                description="Try a different search or status filter.">
                <button type="button" className="rp-btn" onClick={() => {
                  setSearch(""); setStatusFilter("all");
                }}>Clear Filters</button>
              </StatePanel>
            ) : (
              <div className="rp-list">
                {filtered.map((record) => (
                  <ChargeCard key={record.charge_id} record={record} />
                ))}
              </div>
            )}
            <div className="rp-notice">
              <ShieldCheck size={18} />
              <span>
                Rent Payments is read-only. Your property owner records payments actually received
                outside Dormora. Fully paid charges remain listed under All statuses; they only
                disappear from the owner's unpaid-payment dropdown. Individual payment receipts
                will be available in the separate Payment History page.
              </span>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
