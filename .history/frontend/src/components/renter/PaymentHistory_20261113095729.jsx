
/**
 * DORMORA — SYSTEM FUNCTIONALITY FILE 49
 * CREATE: frontend/src/components/renter/PaymentHistory.jsx
 *
 * Renter's read-only owner-recorded rent payment history.
 * GET /api/rent-records/mine
 * GET /api/rent-records/charges/{charge_id}/payments
 *
 * File 50 will connect this page to RoleHome.jsx.
 * No new backend routes, database tables, or payment mutations are needed.
 */

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  Building2,
  CalendarDays,
  CheckCircle2,
  CreditCard,
  FileText,
  History,
  Receipt,
  RefreshCw,
  ShieldCheck,
  Wallet,
} from "lucide-react";

const API_BASE = "http://localhost:8000";
const RENT_API = `${API_BASE}/api/rent-records`;

const styles = `
.ph-page{width:100%;min-width:0;color:var(--text);font-family:inherit}
.ph-page *{box-sizing:border-box}
.ph-head{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:14px;margin-bottom:23px}
.ph-head h1{font-size:clamp(25px,3vw,32px);font-weight:850;margin:0 0 7px}
.ph-head p,.ph-muted{font-size:13px;line-height:1.7;color:var(--muted);margin:0}
.ph-actions{display:flex;flex-wrap:wrap;gap:9px}
.ph-btn{min-height:42px;display:inline-flex;align-items:center;justify-content:center;gap:8px;border-radius:10px;border:1px solid var(--border);background:var(--card);color:var(--text);padding:10px 14px;font:inherit;font-weight:700;font-size:13px;cursor:pointer}
.ph-btn:hover:not(:disabled){filter:brightness(.97)}
.ph-btn:disabled{opacity:.55;cursor:not-allowed}
.ph-btn.primary{background:var(--primary);color:var(--background);border-color:var(--primary)}
.ph-page button:focus-visible,.ph-page select:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.ph-overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;margin:16px 0 20px}
.ph-stat{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;min-width:0}
.ph-stat-label{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)}
.ph-stat-label svg{color:var(--primary);flex-shrink:0}
.ph-stat-value{font-weight:850;font-size:clamp(18px,2.1vw,23px);margin:12px 0 3px;overflow-wrap:anywhere}
.ph-stat-sub{font-size:11px;line-height:1.6;color:var(--muted)}
.ph-panel{border:1px solid var(--border);background:var(--card);border-radius:16px;padding:22px;margin-bottom:18px}
.ph-panel-title{display:flex;align-items:center;gap:10px;font-weight:800;font-size:18px;margin:0 0 16px}
.ph-panel-title svg{color:var(--primary)}
.ph-field{display:block;font-size:13px;font-weight:700;margin-bottom:9px}
.ph-select{width:100%;max-width:100%;background:var(--background);border:1px solid var(--border);border-radius:11px;color:var(--text);padding:13px 12px;font:inherit;font-size:13px;min-height:48px}
.ph-selection{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:14px;margin-top:17px;padding:17px 0 0;border-top:1px solid var(--border)}
.ph-property{font-size:17px;font-weight:800;margin:0 0 6px;overflow-wrap:anywhere}
.ph-location{display:flex;gap:7px;align-items:center;color:var(--muted);font-size:12px;line-height:1.6}
.ph-badge{display:inline-flex;align-items:center;gap:6px;white-space:nowrap;border-radius:9px;background:var(--soft);color:var(--primary);font-size:11px;font-weight:800;padding:8px 10px}
.ph-badge.overdue{color:#b45309}.ph-badge.pending{color:var(--muted)}
.ph-payments{display:grid;gap:12px}
.ph-payment{background:var(--background);border:1px solid var(--border);border-radius:13px;padding:17px;min-width:0}
.ph-payment-head{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px}
.ph-payment-title{display:flex;align-items:center;gap:9px;font-size:16px;font-weight:800}
.ph-payment-title svg{color:var(--primary)}
.ph-amount{font-size:19px;font-weight:850;color:var(--primary)}
.ph-payment-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px;margin-top:16px;padding-top:14px;border-top:1px solid var(--border)}
.ph-label{display:block;font-size:11px;color:var(--muted);margin-bottom:5px}
.ph-value{font-size:13px;font-weight:700;overflow-wrap:anywhere;white-space:pre-wrap}
.ph-note{margin-top:13px;padding:11px 13px;background:var(--soft);border-radius:9px;font-size:12px;line-height:1.65;overflow-wrap:anywhere;white-space:pre-wrap}
.ph-empty{border:1px dashed var(--border);background:var(--card);border-radius:15px;padding:37px 20px;min-height:185px;display:flex;flex-direction:column;gap:11px;align-items:center;justify-content:center;text-align:center}
.ph-empty svg{color:var(--primary)}.ph-empty h3{margin:0;font-size:17px}
.ph-empty p{margin:0;max-width:510px;font-size:13px;line-height:1.7;color:var(--muted)}
.ph-notice{display:flex;gap:10px;align-items:flex-start;padding:15px;background:var(--soft);border:1px solid var(--border);border-radius:12px;color:var(--muted);font-size:12px;line-height:1.75}
.ph-notice svg{flex-shrink:0;color:var(--primary);margin-top:2px}
@media(max-width:820px){.ph-overview{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:570px){.ph-overview{grid-template-columns:1fr}.ph-panel{padding:16px}.ph-payment-grid{grid-template-columns:1fr}.ph-stat{padding:15px}}
`;

function toCents(value) {
  const raw = String(value ?? "").trim();
  if (!/^[0-9]{1,10}(?:\.[0-9]{1,2})?$/.test(raw)) return null;
  const [whole, fraction = ""] = raw.split(".");
  const result = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return Number.isSafeInteger(result) ? result : null;
}

function moneyFromCents(cents) {
  if (cents === null || !Number.isFinite(cents)) return "—";
  return new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

function peso(value) {
  return moneyFromCents(toCents(value));
}

function formatDate(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return "Not recorded";
  const [year, month, day] = match.slice(1).map(Number);
  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return "Not recorded";
  }
  return new Intl.DateTimeFormat("en-PH", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

function formatMonth(value) {
  const match = String(value || "").match(/^(\d{4})-(\d{2})-01$/);
  if (!match) return "Unknown billing month";
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (month < 1 || month > 12) return "Unknown billing month";
  return new Intl.DateTimeFormat("en-PH", {
    year: "numeric",
    month: "long",
  }).format(new Date(year, month - 1, 1));
}

function methodName(value) {
  const names = {
    cash: "Cash",
    bank_transfer: "Bank Transfer",
    e_wallet: "E-Wallet",
    other: "Other",
  };
  return names[value] || "Not specified";
}

function statusName(value) {
  const names = {
    pending: "Pending",
    partially_paid: "Partially Paid",
    paid: "Paid",
    overdue: "Overdue",
  };
  return names[value] || "Unknown";
}

function apiError(response, data) {
  if (response.status === 401) {
    return "Your session has expired. Please sign in again.";
  }
  if (response.status === 403) {
    return "Only an active renter can view this payment history.";
  }
  if (response.status === 404) {
    return "That rent charge is no longer available to your account.";
  }
  if (response.status === 429) {
    return "Too many requests. Please try again later.";
  }
  if (response.status < 500 && typeof data?.detail === "string") {
    return data.detail;
  }
  return "Unable to retrieve the payment history from Dormora.";
}

async function fetchJson(url, signal) {
  const response = await fetch(url, {
    method: "GET",
    credentials: "include",
    mode: "cors",
    cache: "no-store",
    redirect: "error",
    signal,
  });

  let data = null;
  try {
    data = await response.json();
  } catch {
    // A server error may not return JSON.
  }

  if (!response.ok) throw new Error(apiError(response, data));
  return data;
}

function StatePanel({ icon: Icon, heading, description, children }) {
  return (
    <div className="ph-empty" role="status">
      <Icon size={31} />
      <h3>{heading}</h3>
      <p>{description}</p>
      {children}
    </div>
  );
}

export default function PaymentHistory({ account, onBack }) {
  const isRenter = account?.role === "renter";

  const [charges, setCharges] = useState([]);
  const [selectedChargeId, setSelectedChargeId] = useState(null);
  const [loadingCharges, setLoadingCharges] = useState(isRenter);
  const [chargesError, setChargesError] = useState("");

  const [payments, setPayments] = useState([]);
  const [loadingPayments, setLoadingPayments] = useState(false);
  const [paymentsError, setPaymentsError] = useState("");
  const [refreshCount, setRefreshCount] = useState(0);

  useEffect(() => {
    if (!isRenter) {
      setCharges([]);
      setSelectedChargeId(null);
      setLoadingCharges(false);
      setChargesError("");
      return undefined;
    }

    const controller = new AbortController();
    setLoadingCharges(true);
    setChargesError("");

    async function loadCharges() {
      try {
        const data = await fetchJson(
          `${RENT_API}/mine`,
          controller.signal
        );

        if (!Array.isArray(data?.records)) {
          throw new Error(
            "The server returned an unexpected rent-record response."
          );
        }

        if (controller.signal.aborted) return;

        setCharges(data.records);

        setSelectedChargeId((previous) => {
          if (
            previous !== null &&
            data.records.some((item) => item.charge_id === previous)
          ) {
            return previous;
          }

          const mostRecentWithPayments = data.records.find(
            (item) => (toCents(item.total_paid) ?? 0) > 0
          );

          return mostRecentWithPayments?.charge_id ??
            data.records[0]?.charge_id ??
            null;
        });
      } catch (error) {
        if (controller.signal.aborted) return;

        setCharges([]);
        setSelectedChargeId(null);
        setChargesError(
          error instanceof Error
            ? error.message
            : "Unable to load rent records."
        );
      } finally {
        if (!controller.signal.aborted) {
          setLoadingCharges(false);
        }
      }
    }

    loadCharges();
    return () => controller.abort();
  }, [isRenter, refreshCount]);

  const selectedCharge = useMemo(
    () =>
      charges.find(
        (item) => item.charge_id === selectedChargeId
      ) || null,
    [charges, selectedChargeId]
  );

  useEffect(() => {
    if (!isRenter || !selectedCharge) {
      setPayments([]);
      setPaymentsError("");
      setLoadingPayments(false);
      return undefined;
    }

    const controller = new AbortController();

    setLoadingPayments(true);
    setPaymentsError("");
    setPayments([]);

    async function loadPayments() {
      try {
        const data = await fetchJson(
          `${RENT_API}/charges/${encodeURIComponent(
            selectedCharge.charge_id
          )}/payments`,
          controller.signal
        );

        if (!Array.isArray(data?.payments)) {
          throw new Error(
            "The server returned an unexpected payment-history response."
          );
        }

        if (!controller.signal.aborted) {
          setPayments(data.payments);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setPaymentsError(
            error instanceof Error
              ? error.message
              : "Unable to load payment history."
          );
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoadingPayments(false);
        }
      }
    }

    loadPayments();
    return () => controller.abort();
  }, [isRenter, selectedChargeId, selectedCharge, refreshCount]);

  const paidForMonth = useMemo(
    () =>
      payments.reduce(
        (sum, payment) => sum + (toCents(payment.amount) ?? 0),
        0
      ),
    [payments]
  );

  return (
    <section className="ph-page" aria-label="Payment History">
      <style>{styles}</style>

      <div className="ph-head">
        <div>
          <h1>Payment History</h1>
          <p>
            View individual rent payments recorded by your property owner.
          </p>
        </div>

        <div className="ph-actions">
          {typeof onBack === "function" && (
            <button
              type="button"
              className="ph-btn"
              onClick={onBack}
            >
              <ArrowLeft size={16} /> Home
            </button>
          )}

          {isRenter && (
            <button
              type="button"
              className="ph-btn"
              disabled={loadingCharges || loadingPayments}
              onClick={() => setRefreshCount((count) => count + 1)}
            >
              <RefreshCw size={16} /> Refresh
            </button>
          )}
        </div>
      </div>

      {!isRenter ? (
        <StatePanel
          icon={ShieldCheck}
          heading="Renter access required"
          description="Only an authenticated renter can view personal payment history."
        />
      ) : loadingCharges ? (
        <StatePanel
          icon={RefreshCw}
          heading="Loading rent history"
          description="Retrieving your rent charges from Dormora."
        />
      ) : chargesError ? (
        <StatePanel
          icon={AlertCircle}
          heading="Unable to load rent charges"
          description={chargesError}
        >
          <button
            type="button"
            className="ph-btn primary"
            onClick={() => setRefreshCount((count) => count + 1)}
          >
            <RefreshCw size={16} /> Try Again
          </button>
        </StatePanel>
      ) : charges.length === 0 ? (
        <StatePanel
          icon={CalendarDays}
          heading="No rent charges yet"
          description="Your property owner has not created a monthly rent charge. No payment history is available yet."
        />
      ) : (
        <>
          <div className="ph-panel">
            <h2 className="ph-panel-title">
              <CalendarDays size={20} /> Select Billing Month
            </h2>

            <label
              className="ph-field"
              htmlFor="ph-charge-select"
            >
              Rent charge to review
            </label>

            <select
              id="ph-charge-select"
              className="ph-select"
              value={selectedChargeId ?? ""}
              onChange={(event) =>
                setSelectedChargeId(Number(event.target.value))
              }
            >
              {charges.map((charge) => (
                <option
                  key={charge.charge_id}
                  value={charge.charge_id}
                >
                  {formatMonth(charge.billing_month)}
                  {" — "}
                  {charge.property_name ||
                    `Property #${charge.property_id}`}
                  {` — ${charge.room_label || "Room"} — ${
                    statusName(charge.payment_status)
                  }`}
                </option>
              ))}
            </select>

            {selectedCharge && (
              <div className="ph-selection">
                <div>
                  <h3 className="ph-property">
                    {selectedCharge.property_name ||
                      `Property #${selectedCharge.property_id}`}
                  </h3>
                  <div className="ph-location">
                    <Building2 size={15} />
                    {selectedCharge.room_label ||
                      "Room not recorded"}
                  </div>
                  <div className="ph-location">
                    <CalendarDays size={15} />
                    Due {formatDate(selectedCharge.due_date)}
                    {" · "}Charge #{selectedCharge.charge_id}
                  </div>
                </div>

                <span className={`ph-badge ${
                  selectedCharge.payment_status || ""
                }`}>
                  <CheckCircle2 size={14} />
                  {statusName(selectedCharge.payment_status)}
                </span>
              </div>
            )}
          </div>

          {selectedCharge && (
            <>
              <div
                className="ph-overview"
                aria-label="Selected month rent summary"
              >
                <div className="ph-stat">
                  <div className="ph-stat-label">
                    <FileText size={18} /> Monthly Rent
                  </div>
                  <div className="ph-stat-value">
                    {peso(selectedCharge.amount_due)}
                  </div>
                  <div className="ph-stat-sub">
                    Charge for {formatMonth(selectedCharge.billing_month)}
                  </div>
                </div>

                <div className="ph-stat">
                  <div className="ph-stat-label">
                    <Wallet size={18} /> Total Recorded Paid
                  </div>
                  <div className="ph-stat-value">
                    {peso(selectedCharge.total_paid)}
                  </div>
                  <div className="ph-stat-sub">
                    Payments confirmed by the owner
                  </div>
                </div>

                <div className="ph-stat">
                  <div className="ph-stat-label">
                    <CreditCard size={18} /> Remaining Balance
                  </div>
                  <div className="ph-stat-value">
                    {peso(selectedCharge.balance_due)}
                  </div>
                  <div className="ph-stat-sub">
                    Unpaid amount for this month
                  </div>
                </div>
              </div>

              <div className="ph-panel">
                <h2 className="ph-panel-title">
                  <History size={21} /> Recorded Payments
                </h2>

                {loadingPayments ? (
                  <StatePanel
                    icon={RefreshCw}
                    heading="Loading transactions"
                    description="Checking owner-recorded payments for the selected month."
                  />
                ) : paymentsError ? (
                  <StatePanel
                    icon={AlertCircle}
                    heading="Unable to load transactions"
                    description={paymentsError}
                  >
                    <button
                      type="button"
                      className="ph-btn"
                      onClick={() =>
                        setRefreshCount((count) => count + 1)
                      }
                    >
                      <RefreshCw size={16} /> Try Again
                    </button>
                  </StatePanel>
                ) : payments.length === 0 ? (
                  <StatePanel
                    icon={Receipt}
                    heading="No payments recorded"
                    description="Your owner has not recorded a payment for this billing month. The rent charge will remain in your records."
                  />
                ) : (
                  <>
                    <p
                      className="ph-muted"
                      style={{ marginBottom: 14 }}
                    >
                      {payments.length}{" "}
                      {payments.length === 1
                        ? "payment"
                        : "payments"}{" "}
                      recorded for this charge
                      {paidForMonth === toCents(selectedCharge.total_paid)
                        ? "."
                        : ". Refresh to check for more recent changes."}
                    </p>

                    <div className="ph-payments">
                      {payments.map((payment) => (
                        <article
                          key={payment.id}
                          className="ph-payment"
                        >
                          <div className="ph-payment-head">
                            <div className="ph-payment-title">
                              <Receipt size={19} />
                              Payment #{payment.id}
                            </div>
                            <div className="ph-amount">
                              {peso(payment.amount)}
                            </div>
                          </div>

                          <div className="ph-payment-grid">
                            <div>
                              <span className="ph-label">
                                Date received
                              </span>
                              <div className="ph-value">
                                {formatDate(payment.paid_on)}
                              </div>
                            </div>

                            <div>
                              <span className="ph-label">
                                Payment method
                              </span>
                              <div className="ph-value">
                                {methodName(payment.payment_method)}
                              </div>
                            </div>
                          </div>

                          {payment.reference_note && (
                            <div className="ph-note">
                              <span className="ph-label">
                                Reference or note
                              </span>
                              {payment.reference_note}
                            </div>
                          )}
                        </article>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </>
          )}

          <div className="ph-notice">
            <ShieldCheck size={18} />
            <span>
              These entries are owner-recorded rent payments, not
              online transfers or bank-verified receipts. This page
              is read-only. Fully paid billing months remain
              selectable so you can review earlier payments.
              If a recorded payment is incorrect, contact the
              property owner.
            </span>
          </div>
        </>
      )}
    </section>
  );
}
