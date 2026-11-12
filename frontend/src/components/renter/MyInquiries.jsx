/**
 * DORMORA — SYSTEM FUNCTIONALITY FILE 33
 *
 * REPLACE: frontend/src/components/renter/MyInquiries.jsx
 *
 * Authenticated renter inquiry history, pending withdrawal, and private replies.
 * Preserves File 26 history, filters, and withdrawal functionality.
 *
 * Requires File 21 API:
 * GET  /api/rental-inquiries/mine
 * POST /api/rental-inquiries/{id}/withdraw
 * GET  /api/csrf
 * GET  /api/rental-inquiries/{id}/messages
 * POST /api/rental-inquiries/{id}/messages
 *
 * An inquiry is not a reservation, tenancy, or payment.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Inbox,
  MapPin,
  MessageSquareText,
  MessagesSquare,
  Send,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Wallet,
  X,
  XCircle,
} from "lucide-react";

const API_BASE = "http://localhost:8000";
const INQUIRIES_PATH = "/api/rental-inquiries";
const STATUSES = ["pending", "accepted", "rejected", "withdrawn"];

const styles = `
.mi-page{width:100%;min-width:0;color:var(--text);font-family:inherit}
.mi-page *{box-sizing:border-box}
.mi-header{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:22px}
.mi-header h1{font-size:clamp(24px,3vw,31px);font-weight:800;margin:0 0 7px}
.mi-header p{font-size:13px;color:var(--muted);margin:0;line-height:1.7}
.mi-header-actions{display:flex;gap:9px;flex-wrap:wrap}
.mi-button{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:41px;padding:10px 14px;background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:10px;font:inherit;font-size:13px;font-weight:750;cursor:pointer}
.mi-button.primary{background:var(--primary);border-color:var(--primary);color:var(--background)}
.mi-button:disabled{opacity:.5;cursor:not-allowed}
.mi-button:hover:not(:disabled){filter:brightness(.96)}
.mi-page button:focus-visible,.mi-page input:focus-visible,.mi-page select:focus-visible,.mi-page textarea:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.mi-intro{background:var(--card);border:1px solid var(--border);border-radius:15px;padding:20px;margin-bottom:19px}
.mi-intro-top{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.mi-intro-icon{display:grid;place-items:center;width:41px;height:41px;border-radius:12px;background:var(--soft);color:var(--primary)}
.mi-intro h2{margin:0;font-size:17px}
.mi-intro p{color:var(--muted);font-size:13px;line-height:1.7;margin:0}
.mi-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:19px}
.mi-stat{min-width:0;border:1px solid var(--border);background:var(--card);border-radius:13px;padding:15px}
.mi-stat-label{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)}
.mi-stat-label svg{color:var(--primary)}
.mi-stat strong{display:block;margin-top:10px;font-size:26px;line-height:1.1}
.mi-toolbar{display:flex;gap:11px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
.mi-search{flex:1;min-width:210px;display:flex;align-items:center;gap:9px;padding:0 12px;border:1px solid var(--border);border-radius:11px;background:var(--card);color:var(--muted)}
.mi-search input{flex:1;min-width:0;padding:12px 0;background:transparent;color:var(--text);font:inherit;font-size:13px;border:0;outline:none}
.mi-clear{border:0;background:transparent;color:var(--muted);cursor:pointer;display:grid;place-items:center;padding:4px}
.mi-filter{display:flex;align-items:center;gap:8px;border:1px solid var(--border);border-radius:11px;padding:0 11px;background:var(--card);color:var(--muted);font-size:13px}
.mi-filter select{color:var(--text);background:transparent;border:0;outline:0;font:inherit;font-size:13px;padding:12px 3px;cursor:pointer}
.mi-filter option{background:var(--card);color:var(--text)}
.mi-results{margin:0 0 13px;color:var(--muted);font-size:12px}
.mi-list{display:grid;gap:14px}
.mi-card{background:var(--card);border:1px solid var(--border);border-radius:15px;padding:20px;min-width:0}
.mi-card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.mi-card h3{font-size:18px;line-height:1.4;margin:0 0 7px;overflow-wrap:anywhere}
.mi-address{display:flex;align-items:flex-start;gap:7px;color:var(--muted);font-size:12px;line-height:1.65}
.mi-address svg{flex-shrink:0;margin-top:2px}
.mi-status{display:inline-flex;align-items:center;gap:6px;border-radius:8px;background:var(--soft);color:var(--primary);font-size:11px;font-weight:800;padding:7px 10px;text-transform:capitalize;white-space:nowrap}
.mi-status.rejected,.mi-status.withdrawn{color:var(--muted)}
.mi-meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:15px 0;padding:15px 0;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
.mi-meta-label{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:11px;margin-bottom:6px}
.mi-meta-value{font-size:13px;font-weight:700;overflow-wrap:anywhere}
.mi-message{background:var(--soft);border-radius:10px;padding:14px;margin-top:10px}
.mi-message strong{display:flex;align-items:center;gap:7px;font-size:12px;margin-bottom:7px}
.mi-message p{font-size:13px;line-height:1.7;margin:0;color:var(--text);white-space:pre-wrap;overflow-wrap:anywhere}
.mi-card-bottom{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:15px;flex-wrap:wrap}
.mi-card-bottom p{margin:0;color:var(--muted);font-size:12px;line-height:1.7;flex:1;min-width:210px}
.mi-card-actions{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.mi-confirm{margin-top:14px;background:var(--soft);border:1px solid var(--border);border-radius:11px;padding:15px}
.mi-confirm strong{font-size:14px}
.mi-confirm p{color:var(--muted);font-size:12px;line-height:1.65;margin:7px 0 12px}
.mi-confirm-actions{display:flex;gap:9px;flex-wrap:wrap}
.mi-notice{display:flex;align-items:flex-start;gap:9px;border:1px solid var(--border);background:var(--soft);border-radius:11px;padding:14px;margin-bottom:17px;color:var(--text);font-size:13px;line-height:1.65}
.mi-notice svg{flex-shrink:0;color:var(--primary);margin-top:2px}
.mi-state{background:var(--card);border:1px dashed var(--border);border-radius:15px;min-height:220px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;text-align:center;padding:32px 20px}
.mi-state svg{color:var(--primary)}
.mi-state h3{font-size:17px;margin:0}
.mi-state p{font-size:13px;line-height:1.7;color:var(--muted);max-width:470px;margin:0}
.mi-note{font-size:12px;line-height:1.7;color:var(--muted);margin:20px 0 0}
/* File 33: renter conversation panel (same theme tokens as File 24). */
.mi-thread{margin-top:17px;padding:17px;border-radius:12px;border:1px solid var(--border);background:var(--background);min-width:0}
.mi-thread-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:15px}
.mi-thread-head h3{display:flex;align-items:center;gap:8px;font-size:15px;margin:0}
.mi-thread-head h3 svg{color:var(--primary)}
.mi-thread-note{font-size:12px;line-height:1.6;color:var(--muted);margin:8px 0 14px}
.mi-thread-messages{display:grid;gap:12px;max-height:430px;overflow-y:auto;padding:4px 3px 12px}
.mi-chat-row{display:flex;flex-direction:column;align-items:flex-start;gap:5px;min-width:0}
.mi-chat-row.renter{align-items:flex-end}
.mi-chat-label{font-size:11px;color:var(--muted);display:flex;gap:8px;flex-wrap:wrap}
.mi-chat-bubble{max-width:min(86%,650px);background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:12px;padding:11px 13px;font-size:13px;line-height:1.7;white-space:pre-wrap;overflow-wrap:anywhere}
.mi-chat-row.renter .mi-chat-bubble{background:var(--soft);border-color:var(--border)}
.mi-chat-empty{border:1px dashed var(--border);border-radius:10px;padding:20px;text-align:center;color:var(--muted);font-size:13px}
.mi-reply-form{margin-top:12px;padding-top:15px;border-top:1px solid var(--border);display:grid;gap:9px}
.mi-reply-form label{font-size:12px;font-weight:750}
.mi-reply-form textarea{width:100%;min-height:90px;max-height:220px;resize:vertical;border:1px solid var(--border);border-radius:10px;background:var(--card);color:var(--text);font:inherit;font-size:13px;line-height:1.6;padding:11px 12px}
.mi-reply-form textarea:focus-visible{outline:3px solid var(--primary);outline-offset:2px}
.mi-reply-actions{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.mi-thread-feedback{border-radius:10px;background:var(--soft);border:1px solid var(--border);color:var(--text);font-size:12px;line-height:1.65;padding:12px;margin:10px 0}
.mi-thread-feedback.error{border-style:dashed}
.mi-thread-closed{color:var(--muted);font-size:12px;line-height:1.7;margin:12px 0 0}
@media(max-width:900px){.mi-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:640px){.mi-meta{grid-template-columns:1fr}.mi-card{padding:15px}.mi-toolbar{flex-direction:column;align-items:stretch}.mi-search{width:100%}.mi-filter{width:max-content;max-width:100%}.mi-header-actions{width:100%}}
`;

async function apiJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    mode: "cors",
    credentials: "include",
    cache: "no-store",
    redirect: "error",
    ...options,
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    // Do not show arbitrary HTML or internal exception details.
  }
  return { response, data };
}

function apiError(response, data, fallback) {
  if (response.status === 401) return "Your session has expired. Please log in again.";
  if (response.status === 403) return "Access denied. Check your renter session or CSRF token.";
  if (response.status === 404) return "This inquiry is no longer available.";
  if (response.status === 409) return "This inquiry is no longer pending. Refresh to view its latest status.";
  if (response.status === 429) return "Too many requests. Please try again later.";
  if (typeof data?.detail === "string" && response.status < 500) return data.detail;
  return fallback;
}

function formatDateTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return new Intl.DateTimeFormat("en-PH", {
    timeZone: "Asia/Manila",
    year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit",
  }).format(parsed);
}

function formatMoveIn(value) {
  if (!value) return "Not specified";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return "Not specified";
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() + 1 !== month || date.getUTCDate() !== day) {
    return "Not specified";
  }
  return new Intl.DateTimeFormat("en-PH", {
    timeZone: "UTC", year: "numeric", month: "short", day: "numeric",
  }).format(date);
}

function formatPeso(value) {
  if (value === null || value === undefined || value === "") return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return "—";
  return new Intl.NumberFormat("en-PH", {
    style: "currency", currency: "PHP", maximumFractionDigits: 2,
  }).format(amount);
}

function StatusBadge({ status }) {
  const safeStatus = STATUSES.includes(status) ? status : "unknown";
  const Icon = safeStatus === "accepted" ? CheckCircle2
    : safeStatus === "rejected" ? XCircle
      : safeStatus === "withdrawn" ? X : Clock3;
  return (
    <span className={`mi-status ${safeStatus}`}>
      <Icon size={14} /> {safeStatus}
    </span>
  );
}

function statusExplanation(status) {
  switch (status) {
    case "pending":
      return "Waiting for the property owner to review your inquiry. You can withdraw it while it is pending.";
    case "accepted":
      return "The property owner accepted your inquiry. A room has not yet been assigned and no rent is due from this action.";
    case "rejected":
      return "The property owner declined this inquiry. No room was assigned.";
    case "withdrawn":
      return "You withdrew this inquiry before it was reviewed.";
    default:
      return "Refresh to check the latest inquiry status.";
  }
}

/**
 * File 33: Private renter conversation for a single inquiry.
 * The server checks the account owns this inquiry.
 */
function InquiryConversation({ inquiryId }) {
  const [thread, setThread] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [deliveryUncertain, setDeliveryUncertain] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const postingRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    async function loadThread() {
      setLoading(true);
      setLoadError("");
      try {
        const { response, data } = await apiJson(
          `${INQUIRIES_PATH}/${inquiryId}/messages`,
          { method: "GET", signal: controller.signal },
        );
        if (!response.ok) {
          throw new Error(apiError(response, data, "Could not load this conversation."));
        }
        if (!data?.inquiry || !Array.isArray(data?.messages)) {
          throw new Error("The server returned an invalid conversation.");
        }
        if (!controller.signal.aborted) {
          setThread(data);
          setDeliveryUncertain(false);
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setLoadError(error?.message || "Could not load this conversation.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    loadThread();
    return () => controller.abort();
  }, [inquiryId, reloadKey]);

  function refreshThread() {
    setFeedback(null);
    setReloadKey((value) => value + 1);
  }

  async function sendReply(event) {
    event.preventDefault();
    const cleaned = replyText.trim();
    if (
      postingRef.current || sending || deliveryUncertain ||
      !thread?.inquiry?.can_reply || !cleaned || cleaned.length > 1000
    ) return;

    postingRef.current = true;
    setSending(true);
    setFeedback(null);
    let dispatched = false;
    try {
      const csrf = await apiJson("/api/csrf", { method: "GET" });
      if (
        !csrf.response.ok ||
        typeof csrf.data?.csrf_token !== "string" ||
        !csrf.data.csrf_token
      ) {
        throw new Error(apiError(csrf.response, csrf.data, "Unable to obtain a CSRF token."));
      }

      dispatched = true;
      const { response, data } = await apiJson(
        `${INQUIRIES_PATH}/${inquiryId}/messages`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrf.data.csrf_token,
          },
          body: JSON.stringify({ message_text: cleaned }),
        },
      );
      if (!response.ok) {
        setFeedback({
          type: "error",
          text: response.status === 409
            ? "This inquiry no longer accepts replies. Refresh its conversation."
            : apiError(response, data, "Could not send your reply."),
        });
        if (response.status === 409) setReloadKey((value) => value + 1);
        return;
      }

      setReplyText("");
      setFeedback({ type: "success", text: "Reply saved. The property owner can see it in the conversation." });
      if (data?.message && typeof data.message.message_text === "string") {
        setThread((current) => current ? {
          ...current,
          messages: [...current.messages, data.message],
        } : current);
      } else {
        // A successful POST must never be submitted again simply because
        // its response omitted message details. Refresh via a GET instead.
        setReloadKey((value) => value + 1);
      }
    } catch (error) {
      if (dispatched) {
        setDeliveryUncertain(true);
        setFeedback({
          type: "error",
          text: "The connection failed after sending. The reply may already be saved. Refresh the conversation before trying again; do not resend blindly.",
        });
      } else {
        setFeedback({ type: "error", text: error?.message || "Unable to prepare the secure request." });
      }
    } finally {
      postingRef.current = false;
      setSending(false);
    }
  }

  const canReply = Boolean(thread?.inquiry?.can_reply) && !deliveryUncertain;
  const messages = Array.isArray(thread?.messages) ? thread.messages : [];

  return (
    <section className="mi-thread" id={`mi-thread-${inquiryId}`} aria-label={`Conversation for inquiry ${inquiryId}`}>
      <div className="mi-thread-head">
        <h3><MessagesSquare size={19} /> Conversation</h3>
        <button type="button" className="mi-button"
          onClick={refreshThread} disabled={loading || sending}>
          <RefreshCw size={15} /> Refresh Messages
        </button>
      </div>

      {loading ? (
        <p className="mi-thread-note" role="status">Loading private messages...</p>
      ) : loadError ? (
        <div className="mi-thread-feedback error" role="alert">{loadError}</div>
      ) : (
        <>
          <p className="mi-thread-note">
            Only you and this property's owner can view this conversation.
            {thread?.has_older_replies ? " Showing the latest 200 replies." : ""}
          </p>
          <div className="mi-thread-messages" role="log" aria-label="Inquiry conversation" aria-live="polite">
            {messages.length === 0 ? (
              <div className="mi-chat-empty">No text messages yet. Send a reply to begin.</div>
            ) : messages.map((message, index) => {
              const renter = message.sender_role === "renter";
              return (
                <div className={`mi-chat-row ${renter ? "renter" : ""}`}
                  key={message.kind === "initial_inquiry" ? "initial" : `reply-${message.id ?? index}`}>
                  <span className="mi-chat-label">
                    {renter ? "You · Renter" : "Property Owner"}
                    {message.kind === "initial_inquiry" ? " · Original inquiry" : ""}
                    {message.created_at ? ` · ${formatDateTime(message.created_at)}` : ""}
                  </span>
                  <div className="mi-chat-bubble">{message.message_text}</div>
                </div>
              );
            })}
          </div>

          {thread?.inquiry?.can_reply ? (
            <form className="mi-reply-form" onSubmit={sendReply}>
              <label htmlFor={`mi-reply-${inquiryId}`}>Reply to property owner</label>
              <textarea
                id={`mi-reply-${inquiryId}`}
                value={replyText}
                onChange={(event) => setReplyText(event.target.value)}
                maxLength={1000}
                rows={3}
                placeholder="Type your message to the property owner..."
                disabled={sending || deliveryUncertain}
              />
              <div className="mi-reply-actions">
                <small className="df-muted">{replyText.length}/1000 characters</small>
                <button className="mi-button primary" type="submit"
                  disabled={!canReply || sending || !replyText.trim()}>
                  <Send size={15} /> {sending ? "Sending..." : "Send Reply"}
                </button>
              </div>
            </form>
          ) : (
            <p className="mi-thread-closed">
              This inquiry is closed for new replies. The conversation remains visible.
            </p>
          )}
        </>
      )}

      {feedback && (
        <div className={`mi-thread-feedback ${feedback.type === "error" ? "error" : ""}`}
          role={feedback.type === "error" ? "alert" : "status"}>
          {feedback.text}
        </div>
      )}
      {deliveryUncertain && (
        <p className="mi-thread-note">Refresh Messages to confirm whether your reply was saved before trying again.</p>
      )}
    </section>
  );
}


export default function MyInquiries({ account, onBack }) {
  const isRenter = account?.role === "renter";
  const [inquiries, setInquiries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [refreshKey, setRefreshKey] = useState(0);
  const [confirmingId, setConfirmingId] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [outcomeUncertainId, setOutcomeUncertainId] = useState(null);
  const [openThreadId, setOpenThreadId] = useState(null);

  const refresh = useCallback(() => {
    setConfirmingId(null);
    setOutcomeUncertainId(null);
    setRefreshKey((value) => value + 1);
  }, []);

  useEffect(() => {
    if (!isRenter) {
      setInquiries([]);
      setLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      try {
        const { response, data } = await apiJson(`${INQUIRIES_PATH}/mine`, {
          method: "GET", signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(apiError(response, data, "Could not retrieve your rental inquiries."));
        }
        if (!Array.isArray(data?.inquiries)) {
          throw new Error("The server returned an invalid inquiry list.");
        }
        if (!controller.signal.aborted) {
          setInquiries(data.inquiries);
        }
      } catch (caught) {
        if (!controller.signal.aborted) {
          setInquiries([]);
          setError(caught?.message || "Could not connect to the Dormora backend.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    load();
    return () => controller.abort();
  }, [isRenter, refreshKey]);

  const totals = useMemo(() => ({
    total: inquiries.length,
    pending: inquiries.filter((row) => row.status === "pending").length,
    accepted: inquiries.filter((row) => row.status === "accepted").length,
    rejected: inquiries.filter((row) => row.status === "rejected").length,
  }), [inquiries]);

  const visible = useMemo(() => {
    const term = query.trim().toLowerCase();
    return inquiries.filter((row) => {
      if (statusFilter !== "all" && row.status !== statusFilter) return false;
      if (!term) return true;
      return `${row.property_name || ""} ${row.property_address || ""}`
        .toLowerCase().includes(term);
    });
  }, [inquiries, query, statusFilter]);

  async function withdrawInquiry(inquiryId) {
    if (!isRenter || busyId !== null || loading || outcomeUncertainId !== null) return;
    const selected = inquiries.find((row) => row.id === inquiryId);
    if (!selected || selected.status !== "pending") return;

    setBusyId(inquiryId);
    setNotice(null);
    try {
      const csrf = await apiJson("/api/csrf", { method: "GET" });
      if (!csrf.response.ok || typeof csrf.data?.csrf_token !== "string" || !csrf.data.csrf_token) {
        setNotice({ type: "error", text: apiError(csrf.response, csrf.data, "Could not get a CSRF token.") });
        return;
      }

      // The POST is intentionally not auto-retried: it may have committed.
      let result;
      try {
        result = await apiJson(`${INQUIRIES_PATH}/${inquiryId}/withdraw`, {
          method: "POST",
          headers: { "X-CSRF-Token": csrf.data.csrf_token },
        });
      } catch {
        setOutcomeUncertainId(inquiryId);
        setNotice({
          type: "error",
          text: "Connection interrupted after sending the request. It may have been saved. Refresh your status before taking any further action.",
        });
        return;
      }

      if (!result.response.ok) {
        setNotice({ type: "error", text: apiError(result.response, result.data, "Unable to withdraw inquiry.") });
      } else {
        setNotice({ type: "success", text: `Inquiry #${inquiryId} was withdrawn successfully.` });
      }
      refresh();
    } catch (caught) {
      setNotice({ type: "error", text: caught?.message || "Unable to process inquiry withdrawal." });
    } finally {
      setBusyId(null);
      setConfirmingId(null);
    }
  }

  if (!isRenter) {
    return (
      <section className="mi-page">
        <style>{styles}</style>
        <div className="mi-state" role="alert">
          <ShieldCheck size={34} />
          <h3>Renter Account Required</h3>
          <p>Rental inquiry history is available only to registered renters.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="mi-page">
      <style>{styles}</style>

      <div className="mi-header">
        <div>
          <h1>My Inquiries</h1>
          <p>Track your requests and messages with property owners.</p>
        </div>
        <div className="mi-header-actions">
          {typeof onBack === "function" && (
            <button type="button" className="mi-button" onClick={onBack}>
              <ArrowLeft size={16} /> Home
            </button>
          )}
          <button type="button" className="mi-button" onClick={refresh}
            disabled={loading || busyId !== null}>
            <RefreshCw size={16} /> Refresh
          </button>
        </div>
      </div>

      <div className="mi-intro">
        <div className="mi-intro-top">
          <span className="mi-intro-icon"><Inbox size={23} /></span>
          <h2>Your Rental Inquiry History</h2>
        </div>
        <p>
          Review your inquiries and open a conversation to read the owner's replies or ask follow-up questions.
          An accepted inquiry is not yet a room assignment or rental agreement.
        </p>
      </div>

      <div className="mi-stats" aria-label="Inquiry totals">
        {[
          ["Total Inquiries", totals.total, Inbox],
          ["Pending", totals.pending, Clock3],
          ["Accepted", totals.accepted, CheckCircle2],
          ["Rejected", totals.rejected, XCircle],
        ].map(([label, count, Icon]) => (
          <div className="mi-stat" key={label}>
            <span className="mi-stat-label"><Icon size={17} /> {label}</span>
            <strong>{count}</strong>
          </div>
        ))}
      </div>

      {notice && (
        <div className="mi-notice" role={notice.type === "error" ? "alert" : "status"}>
          <ShieldCheck size={18} /> <span>{notice.text}</span>
        </div>
      )}

      <div className="mi-toolbar">
        <label className="mi-search">
          <Search size={17} />
          <input type="search" aria-label="Search your inquiries"
            placeholder="Search by property name or address" maxLength={100}
            value={query} onChange={(event) => setQuery(event.target.value)} />
          {query && (
            <button type="button" className="mi-clear" aria-label="Clear search"
              onClick={() => setQuery("")}><X size={16} /></button>
          )}
        </label>
        <label className="mi-filter">
          <SlidersHorizontal size={17} />
          Status
          <select aria-label="Filter inquiry status" value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">All statuses</option>
            <option value="pending">Pending</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
            <option value="withdrawn">Withdrawn</option>
          </select>
        </label>
      </div>

      <p className="mi-results">
        {loading ? "Loading inquiries..." : error ? "Inquiries unavailable"
          : `${visible.length} ${visible.length === 1 ? "inquiry" : "inquiries"} shown`}
      </p>

      {loading ? (
        <div className="mi-state" role="status">
          <RefreshCw size={33} /><h3>Loading Your Inquiries</h3>
          <p>Retrieving your inquiry history from Dormora.</p>
        </div>
      ) : error ? (
        <div className="mi-state" role="alert">
          <XCircle size={33} /><h3>Unable to Load Inquiries</h3>
          <p>{error}</p>
          <button type="button" className="mi-button primary" onClick={refresh}>Try Again</button>
        </div>
      ) : visible.length === 0 ? (
        <div className="mi-state">
          <Inbox size={34} />
          <h3>{inquiries.length ? "No Matching Inquiries" : "No Inquiries Yet"}</h3>
          <p>{inquiries.length
            ? "Try another property name or status filter."
            : "When you contact property owners through Discover Dorms, your requests will appear here."}</p>
          {(query || statusFilter !== "all") && (
            <button type="button" className="mi-button" onClick={() => {
              setQuery(""); setStatusFilter("all");
            }}>Clear Filters</button>
          )}
        </div>
      ) : (
        <div className="mi-list">
          {visible.map((item) => {
            const pending = item.status === "pending";
            return (
              <article className="mi-card" key={item.id}>
                <div className="mi-card-head">
                  <div>
                    <h3>{item.property_name || `Property #${item.property_id}`}</h3>
                    <div className="mi-address">
                      <MapPin size={14} />
                      <span>{item.property_address || `Property ID #${item.property_id}`} · Inquiry #{item.id}</span>
                    </div>
                  </div>
                  <StatusBadge status={item.status} />
                </div>

                <div className="mi-meta">
                  <div>
                    <span className="mi-meta-label"><Wallet size={14} /> Monthly rent</span>
                    <span className="mi-meta-value">{formatPeso(item.monthly_rent)}</span>
                  </div>
                  <div>
                    <span className="mi-meta-label"><CalendarDays size={14} /> Preferred move-in</span>
                    <span className="mi-meta-value">{formatMoveIn(item.preferred_move_in_date)}</span>
                  </div>
                  <div>
                    <span className="mi-meta-label"><Clock3 size={14} /> Submitted</span>
                    <span className="mi-meta-value">{formatDateTime(item.created_at)}</span>
                  </div>
                </div>

                <div className="mi-message">
                  <strong><MessageSquareText size={15} /> Your message</strong>
                  <p>{item.message || "No message was included."}</p>
                </div>

                <div className="mi-card-bottom">
                  <p>
                    {statusExplanation(item.status)}
                    {item.reviewed_at ? ` Reviewed ${formatDateTime(item.reviewed_at)}.` : ""}
                  </p>
                  <div className="mi-card-actions">
                    <button type="button" className="mi-button"
                      aria-expanded={openThreadId === item.id}
                      aria-controls={`mi-thread-${item.id}`}
                      onClick={() => setOpenThreadId((current) => current === item.id ? null : item.id)}>
                      <MessagesSquare size={16} />
                      {openThreadId === item.id ? "Hide Conversation" : "View Conversation"}
                    </button>
                    {pending && (
                      <button type="button" className="mi-button"
                        disabled={busyId !== null || outcomeUncertainId !== null}
                        onClick={() => setConfirmingId(item.id)}>
                        <X size={16} /> Withdraw Inquiry
                      </button>
                    )}
                  </div>
                </div>

                {pending && confirmingId === item.id && (
                  <div className="mi-confirm" role="group" aria-label={`Confirm withdrawal of inquiry ${item.id}`}>
                    <strong>Withdraw Inquiry #{item.id}?</strong>
                    <p>
                      This will change the inquiry to withdrawn. The property owner will
                      no longer be able to accept or reject this request.
                    </p>
                    <div className="mi-confirm-actions">
                      <button type="button" className="mi-button"
                        disabled={busyId !== null} onClick={() => setConfirmingId(null)}>Cancel</button>
                      <button type="button" className="mi-button primary"
                        disabled={busyId !== null || outcomeUncertainId !== null}
                        onClick={() => withdrawInquiry(item.id)}>
                        {busyId === item.id ? "Withdrawing..." : "Confirm Withdrawal"}
                      </button>
                    </div>
                  </div>
                )}

                {openThreadId === item.id && (
                  <InquiryConversation key={`${item.id}-${refreshKey}`} inquiryId={item.id} />
                )}
              </article>
            );
          })}
        </div>
      )}

      <p className="mi-note">
        Rental inquiries are messages of interest, not room reservations or payments.
        Room assignment and rent tracking will be added in later functionality files.
      </p>
    </section>
  );
}
