
/**
 * DORMORA — SYSTEM FUNCTIONALITY FILE 40
 * CREATE: frontend/src/components/renter/MyRental.jsx
 *
 * Renter-only read-only view of assigned room and rental history.
 * File 41 will connect this component to RoleHome's My Rental navigation.
 *
 * API: GET /api/tenancies/mine (File 36)
 * Security: authenticated session cookie, server-side renter validation.
 * No rent invoices, payments, or tenant mutations are performed here.
 */

import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft, Building2, CalendarDays, CheckCircle2, Clock3,
  DoorOpen, History, MapPin, RefreshCw, ShieldCheck, Wallet,
} from "lucide-react";

const API_BASE = "http://localhost:8000";
const TENANCIES_API = `${API_BASE}/api/tenancies/mine`;

const styles = `
.mr-page{width:100%;min-width:0;color:var(--text);font-family:inherit}
.mr-page *{box-sizing:border-box}
.mr-head{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:14px;margin-bottom:22px}
.mr-head h1{font-size:clamp(25px,3vw,31px);margin:0 0 8px;font-weight:800}
.mr-subtitle,.mr-muted{color:var(--muted);font-size:13px;line-height:1.7;margin:0}
.mr-head-actions{display:flex;gap:9px;flex-wrap:wrap}
.mr-btn{border:1px solid var(--border);background:var(--card);color:var(--text);border-radius:10px;min-height:42px;padding:10px 14px;display:inline-flex;align-items:center;justify-content:center;gap:8px;font:inherit;font-size:13px;font-weight:700;cursor:pointer}
.mr-btn.primary{background:var(--primary);border-color:var(--primary);color:var(--background)}
.mr-btn:disabled{opacity:.55;cursor:not-allowed}.mr-btn:hover:not(:disabled){filter:brightness(.97)}
.mr-page button:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.mr-section{margin-bottom:21px}.mr-section-title{font-size:18px;font-weight:800;margin:0 0 13px;display:flex;align-items:center;gap:9px}
.mr-section-title svg{color:var(--primary)}
.mr-hero{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;background:linear-gradient(115deg,var(--hero),var(--card));border:1px solid var(--border);border-radius:17px;padding:23px;margin-bottom:18px}
.mr-hero-left{display:flex;gap:14px;align-items:center;min-width:0}
.mr-hero-icon{width:52px;height:52px;flex-shrink:0;display:grid;place-items:center;background:var(--card);color:var(--primary);border-radius:14px;border:1px solid var(--border)}
.mr-hero h2{font-size:clamp(19px,2.4vw,23px);margin:0 0 7px;overflow-wrap:anywhere}
.mr-location{display:flex;align-items:flex-start;gap:7px;color:var(--muted);font-size:12px;line-height:1.6;overflow-wrap:anywhere}
.mr-location svg{flex-shrink:0;margin-top:2px}
.mr-status{display:inline-flex;align-items:center;gap:6px;padding:8px 11px;background:var(--soft);color:var(--primary);border-radius:10px;font-size:12px;font-weight:800;white-space:nowrap}
.mr-status.ended{color:var(--muted)}
.mr-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;margin-bottom:16px}
.mr-stat{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;min-width:0}
.mr-stat-head{display:flex;gap:8px;align-items:center;color:var(--muted);font-size:12px}
.mr-stat-head svg{flex-shrink:0;color:var(--primary)}
.mr-stat-value{font-size:21px;font-weight:850;overflow-wrap:anywhere;margin-top:11px}
.mr-stat-hint{font-size:11px;color:var(--muted);margin-top:5px;line-height:1.5}
.mr-card{background:var(--card);border:1px solid var(--border);border-radius:15px;padding:21px;margin-bottom:16px}
.mr-card h3{font-size:17px;margin:0 0 16px}
.mr-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:24px;row-gap:19px}
.mr-field-label{display:block;font-size:12px;color:var(--muted);margin-bottom:5px}
.mr-field-value{font-size:14px;font-weight:750;overflow-wrap:anywhere}
.mr-notice{display:flex;gap:10px;align-items:flex-start;border:1px solid var(--border);border-radius:12px;background:var(--soft);padding:14px;color:var(--muted);font-size:12px;line-height:1.7}
.mr-notice svg{flex-shrink:0;color:var(--primary);margin-top:2px}
.mr-history{display:grid;gap:12px}
.mr-history-item{border:1px solid var(--border);background:var(--card);border-radius:14px;padding:18px}
.mr-history-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:13px}
.mr-history-head h3{margin:0 0 5px;font-size:16px;overflow-wrap:anywhere}
.mr-history-meta{color:var(--muted);font-size:12px;line-height:1.6}
.mr-history-fields{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px;padding-top:13px;border-top:1px solid var(--border)}
.mr-state{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;gap:12px;min-height:215px;border:1px dashed var(--border);border-radius:15px;padding:30px 22px;background:var(--card)}
.mr-state svg{color:var(--primary)}.mr-state h2{font-size:18px;margin:0}
.mr-state p{margin:0;color:var(--muted);font-size:13px;line-height:1.7;max-width:500px}
@media(max-width:900px){.mr-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.mr-grid,.mr-details,.mr-history-fields{grid-template-columns:1fr}.mr-hero,.mr-card{padding:16px}.mr-head{flex-direction:column}.mr-stat{padding:15px}.mr-hero-icon{width:43px;height:43px}}
`;

function peso(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return "—";
  return new Intl.NumberFormat("en-PH", {
    style: "currency", currency: "PHP", minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(number);
}

function displayDate(value) {
  if (!value) return "Not recorded";
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match) return "Not recorded";
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
    return "Not recorded";
  }
  return new Intl.DateTimeFormat("en-PH", {
    month: "long", day: "numeric", year: "numeric",
  }).format(date);
}

function todayInPhilippines() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Manila", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const part = (type) => parts.find((item) => item.type === type)?.value || "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

function errorMessage(response, data) {
  if (response.status === 401) return "Your session has expired. Please sign in again.";
  if (response.status === 403) return "This page requires an active renter account.";
  if (response.status === 429) return "Too many requests. Please try again later.";
  if (response.status < 500 && typeof data?.detail === "string") return data.detail;
  return "Could not load rental information. Check that your backend is running.";
}

function Status({ item, future = false }) {
  const ended = item.status === "ended";
  return (
    <span className={`mr-status ${ended ? "ended" : ""}`}>
      {ended ? <History size={14} /> : future ? <Clock3 size={14} /> : <CheckCircle2 size={14} />}
      {ended ? "Ended" : future ? "Upcoming move-in" : "Active rental"}
    </span>
  );
}

function Detail({ label, value }) {
  return (
    <div>
      <span className="mr-field-label">{label}</span>
      <div className="mr-field-value">{value}</div>
    </div>
  );
}

export default function MyRental({ account, onBack }) {
  const isRenter = account?.role === "renter";
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(isRenter);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    if (!isRenter) {
      setRecords([]);
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setLoading(true);
    setError("");

    async function loadRental() {
      try {
        const response = await fetch(TENANCIES_API, {
          method: "GET", credentials: "include", mode: "cors",
          cache: "no-store", redirect: "error", signal: controller.signal,
        });
        let body = null;
        try { body = await response.json(); } catch { /* Do not display HTML errors. */ }

        if (!response.ok) throw new Error(errorMessage(response, body));
        if (!Array.isArray(body?.tenancies)) {
          throw new Error("The backend returned an unexpected rental response.");
        }
        if (!controller.signal.aborted) setRecords(body.tenancies);
      } catch (caught) {
        if (!controller.signal.aborted) {
          setRecords([]);
          setError(caught instanceof Error ? caught.message : "Unable to load rental information.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    loadRental();
    return () => controller.abort();
  }, [isRenter, revision]);

  const { current, history } = useMemo(() => {
    return {
      current: records.find((row) => row.status === "active") || null,
      history: records.filter((row) => row.status === "ended"),
    };
  }, [records]);

  const upcomingMoveIn = Boolean(
    current?.move_in_date && current.move_in_date > todayInPhilippines()
  );

  return (
    <section className="mr-page" aria-label="My Rental">
      <style>{styles}</style>
      <div className="mr-head">
        <div>
          <h1>My Rental</h1>
          <p className="mr-subtitle">Your assigned room, agreed rental terms, and rental history.</p>
        </div>
        <div className="mr-head-actions">
          {typeof onBack === "function" && (
            <button className="mr-btn" type="button" onClick={onBack}>
              <ArrowLeft size={16} /> Home
            </button>
          )}
          {isRenter && (
            <button className="mr-btn" type="button" disabled={loading}
              onClick={() => setRevision((value) => value + 1)}>
              <RefreshCw size={16} /> Refresh
            </button>
          )}
        </div>
      </div>

      {!isRenter ? (
        <div className="mr-state" role="alert">
          <ShieldCheck size={32} />
          <h2>Renter access required</h2>
          <p>This page is for authenticated renter accounts only.</p>
        </div>
      ) : loading ? (
        <div className="mr-state" role="status">
          <RefreshCw size={32} />
          <h2>Loading your rental</h2>
          <p>Retrieving your tenancy records from Dormora.</p>
        </div>
      ) : error ? (
        <div className="mr-state" role="alert">
          <Building2 size={32} />
          <h2>Unable to load your rental</h2>
          <p>{error}</p>
          <button className="mr-btn primary" type="button"
            onClick={() => setRevision((value) => value + 1)}>
            <RefreshCw size={16} /> Try Again
          </button>
        </div>
      ) : (
        <>
          <section className="mr-section" aria-labelledby="mr-current-title">
            <h2 id="mr-current-title" className="mr-section-title">
              <DoorOpen size={20} /> Current Rental
            </h2>
            {!current ? (
              <div className="mr-state">
                <Building2 size={32} />
                <h2>No active rental yet</h2>
                <p>You do not have a room assigned right now. Once a property owner
                  formally assigns a room, its details will appear here.</p>
              </div>
            ) : (
              <>
                <div className="mr-hero">
                  <div className="mr-hero-left">
                    <div className="mr-hero-icon"><Building2 size={25} /></div>
                    <div>
                      <h2>{current.property_name || `Property #${current.property_id}`}</h2>
                      <div className="mr-location">
                        <MapPin size={15} />
                        <span>{current.property_address || "Address not recorded"}</span>
                      </div>
                    </div>
                  </div>
                  <Status item={current} future={upcomingMoveIn} />
                </div>

                <div className="mr-grid">
                  <div className="mr-stat">
                    <div className="mr-stat-head"><DoorOpen size={18} /> Assigned Room</div>
                    <div className="mr-stat-value">{current.room_label || "—"}</div>
                    <div className="mr-stat-hint">Allocated to your tenancy</div>
                  </div>
                  <div className="mr-stat">
                    <div className="mr-stat-head"><Wallet size={18} /> Agreed Monthly Rent</div>
                    <div className="mr-stat-value">{peso(current.monthly_rent)}</div>
                    <div className="mr-stat-hint">Agreed amount, not a payment record</div>
                  </div>
                  <div className="mr-stat">
                    <div className="mr-stat-head"><CalendarDays size={18} /> Rent Due Day</div>
                    <div className="mr-stat-value">
                      {current.rent_due_day ? `Day ${current.rent_due_day}` : "—"}
                    </div>
                    <div className="mr-stat-hint">Day of each month; billing is coming later</div>
                  </div>
                </div>

                <div className="mr-card">
                  <h3>Rental Details</h3>
                  <div className="mr-details">
                    <Detail label="Move-in Date" value={displayDate(current.move_in_date)} />
                    <Detail label="Rental Status" value={upcomingMoveIn ? "Active — move-in scheduled" : "Active"} />
                    <Detail label="Tenancy Reference" value={`#${current.id}`} />
                    <Detail label="Accepted Inquiry Reference" value={`#${current.inquiry_id}`} />
                  </div>
                </div>
                <div className="mr-notice">
                  <ShieldCheck size={18} />
                  <span>
                    {upcomingMoveIn
                      ? "Your tenancy is active in Dormora, and the room is already allocated. Your move-in date is still upcoming. "
                      : "Your room assignment is recorded as an active tenancy. "}
                    Monthly billing, payment status, and receipts will appear after the Rent Management feature is connected.
                    This page does not collect or confirm payments.
                  </span>
                </div>
              </>
            )}
          </section>

          <section className="mr-section" aria-labelledby="mr-history-title">
            <h2 id="mr-history-title" className="mr-section-title">
              <History size={20} /> Previous Rentals
            </h2>
            {history.length === 0 ? (
              <div className="mr-card">
                <p className="mr-muted">No previous rentals recorded.</p>
              </div>
            ) : (
              <div className="mr-history">
                {history.map((item) => (
                  <article className="mr-history-item" key={item.id}>
                    <div className="mr-history-head">
                      <div>
                        <h3>{item.property_name || `Property #${item.property_id}`}</h3>
                        <div className="mr-history-meta">
                          {item.room_label} · Tenancy #{item.id}
                        </div>
                      </div>
                      <Status item={item} />
                    </div>
                    <div className="mr-history-fields">
                      <Detail label="Agreed Monthly Rent" value={peso(item.monthly_rent)} />
                      <Detail label="Move-in Date" value={displayDate(item.move_in_date)} />
                      <Detail label="Move-out Date" value={displayDate(item.move_out_date)} />
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </section>
  );
}
