
/*
 * Dormora Frontend File 115 — extracted authenticated Change Password form.
 * CREATE: frontend/src/components/account/PasswordChangeForm.jsx
 *
 * Preserves the existing File 114 password rules, field layout, error handling,
 * CSRF-protected request, and session-revocation callbacks without redesign.
 * The parent supplies the existing postWithCsrf helper as a prop, so this
 * component never duplicates or weakens the established CSRF handshake.
 *
 * STAGED REFACTOR: Do not modify App.jsx until File 116 connects this file.
 */

import { useState } from "react";
import { Eye, EyeOff, KeyRound } from "lucide-react";

const ACTION_BUTTON_STYLE = {
  padding: "12px 18px",
  borderRadius: 10,
  border: "1px solid var(--border)",
  background: "var(--soft)",
  color: "var(--text)",
  cursor: "pointer",
};

// FILE 106: This form is rendered ONLY inside a verified, unexpired account
// workspace. It never accepts a user ID and never stores submitted credentials.
const CHANGE_PASSWORD_INPUT_STYLE = {
  width: "100%",
  boxSizing: "border-box",
  padding: "12px 14px",
  border: "1px solid var(--border)",
  borderRadius: 10,
  background: "var(--background)",
  color: "var(--text)",
  font: "inherit",
};

function validNewPassword(value) {
  return (
    typeof value === "string" &&
    value.length >= 10 &&
    value.length <= 64 &&
    /[a-z]/.test(value) &&
    /[A-Z]/.test(value) &&
    /[0-9]/.test(value) &&
    /[^A-Za-z0-9]/.test(value) &&
    !/[\x00-\x1F\x7F]/.test(value)
  );
}

function newPasswordStrength(value) {
  if (!value) return "Not entered";
  if (!validNewPassword(value)) return "Weak";
  return value.length >= 14 ? "Strong" : "Medium";
}

function PasswordChangeForm({ busy, actionInFlight, setBusy, onSuccess, onSessionLost, onUncertain, postWithCsrf }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [revealed, setRevealed] = useState({ current: false, next: false, confirm: false });
  const [feedback, setFeedback] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const isBusy = busy || submitting;
  const meetsPolicy = validNewPassword(newPassword);
  const strength = newPasswordStrength(newPassword);

  function clearPasswords() {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (isBusy || actionInFlight.current) return;
    setFeedback(null);
    if (!currentPassword) {
      setFeedback({ kind: "error", text: "Enter your current password." });
      return;
    }
    if (!meetsPolicy) {
      setFeedback({ kind: "error", text: "Use 10–64 characters with uppercase, lowercase, a number, and a special character." });
      return;
    }
    if (newPassword !== confirmPassword) {
      setFeedback({ kind: "error", text: "Mismatch Password." });
      return;
    }
    if (newPassword === currentPassword) {
      setFeedback({ kind: "error", text: "You cannot reuse a recent password." });
      return;
    }

    actionInFlight.current = true;
    setBusy(true);
    setSubmitting(true);
    try {
      const response = await postWithCsrf("/api/auth/password/change", {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      if (response.status === 401) {
        clearPasswords();
        onSessionLost();
        return;
      }
      if (response.status === 200) {
        // Only File 105's confirmed success means PostgreSQL committed the
        // change and revoked sessions. Never infer success from a generic 200.
        const reply = await response.json();
        clearPasswords();
        if (reply?.authenticated === false && typeof reply.message === "string") {
          onSuccess();
        } else {
          onUncertain();
        }
        return;
      }
      if (response.status === 400) {
        let detail = "Password change was rejected. Check your current password and new password rules.";
        try {
          const reply = await response.json();
          if (
            typeof reply?.detail === "string" &&
            reply.detail.length > 0 &&
            reply.detail.length <= 180
          ) {
            detail = reply.detail; // React escapes this as ordinary text.
          }
        } catch {
          // Don't expose or depend on malformed server error content.
        }
        setFeedback({ kind: "error", text: detail });
      } else if (response.status === 403) {
        setFeedback({ kind: "error", text: "Your request origin or CSRF verification was rejected. Reload on localhost and try again." });
      } else if (response.status === 429) {
        setFeedback({ kind: "error", text: "Too many incorrect current-password attempts. Try again after 15 minutes." });
      } else if (response.status === 404) {
        setFeedback({ kind: "error", text: "Password change is unavailable. Start the File 86 local login runner." });
      } else if (response.status === 422) {
        setFeedback({ kind: "error", text: "Check the password fields and try again." });
      } else if (response.status === 503) {
        setFeedback({ kind: "error", text: "Password change is temporarily unavailable; no success was confirmed." });
      } else {
        setFeedback({ kind: "error", text: "Password change was not confirmed. Check FastAPI before retrying." });
      }
    } catch {
      // The server might have committed before the network response was lost.
      // Fail closed rather than asking the user to resubmit sensitive data.
      clearPasswords();
      onUncertain();
    } finally {
      actionInFlight.current = false;
      setBusy(false);
      setSubmitting(false);
    }
  }

  const fields = [
    {
      key: "current", label: "Current password", value: currentPassword,
      setValue: setCurrentPassword, autoComplete: "current-password",
    },
    {
      key: "next", label: "New password", value: newPassword,
      setValue: setNewPassword, autoComplete: "new-password",
    },
    {
      key: "confirm", label: "Confirm new password", value: confirmPassword,
      setValue: setConfirmPassword, autoComplete: "new-password",
    },
  ];

  return (
    <section aria-labelledby="dormora-change-password-heading" style={{
      border: "1px solid var(--border)", borderRadius: 14,
      marginTop: 20, padding: "clamp(16px, 3vw, 24px)", background: "var(--soft)",
    }}>
      <h2 id="dormora-change-password-heading" style={{ fontSize: 21, marginTop: 0 }}>
        <KeyRound size={19} style={{ verticalAlign: "middle", marginRight: 8 }} />
        Change password
      </h2>
      <p style={{ color: "var(--muted)", fontSize: 13 }}>
        Enter your current password to confirm ownership. Your new password must
        differ from your current and two preceding passwords. After a successful
        change, all sessions are revoked and you must sign in again.
      </p>
      <form onSubmit={handleSubmit} autoComplete="on">
        <div style={{ display: "grid", gap: 16 }}>
          {fields.map((field) => (
            <div key={field.key}>
              <label htmlFor={`dormora-password-${field.key}`} style={{ display: "block", marginBottom: 7, fontWeight: 600 }}>
                {field.label}
              </label>
              <div style={{ display: "flex", alignItems: "stretch", gap: 8 }}>
                <input
                  id={`dormora-password-${field.key}`}
                  type={revealed[field.key] ? "text" : "password"}
                  name={field.key === "current" ? "current-password" : field.key === "next" ? "new-password" : "confirm-password"}
                  autoComplete={field.autoComplete}
                  value={field.value}
                  onChange={(event) => { field.setValue(event.target.value); setFeedback(null); }}
                  minLength={field.key === "current" ? 1 : 10}
                  maxLength={field.key === "current" ? 512 : 64}
                  required
                  disabled={isBusy}
                  style={{ ...CHANGE_PASSWORD_INPUT_STYLE, minWidth: 0, flex: 1 }}
                />
                <button
                  type="button"
                  disabled={isBusy}
                  aria-label={`${revealed[field.key] ? "Hide" : "Show"} ${field.label.toLowerCase()}`}
                  aria-pressed={revealed[field.key]}
                  onClick={() => setRevealed((old) => ({ ...old, [field.key]: !old[field.key] }))}
                  style={{ ...ACTION_BUTTON_STYLE, padding: "0 12px" }}
                >
                  {revealed[field.key] ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>
          ))}
        </div>
        <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 12 }}>
          New password strength: <strong>{strength}</strong>
          {newPassword && !meetsPolicy && " · Requires uppercase, lowercase, a number, a symbol, and 10–64 characters."}
        </p>
        {feedback && (
          <p role="alert" style={{ color: "#cc5555", fontSize: 14 }}>
            {feedback.text}
          </p>
        )}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 18 }}>
          <button
            type="submit"
            disabled={isBusy || !currentPassword || !meetsPolicy || newPassword !== confirmPassword}
            style={{ ...ACTION_BUTTON_STYLE, background: "var(--primary)", color: "var(--background)", fontWeight: 700 }}
          >
            {submitting ? "Changing password…" : "Change password securely"}
          </button>
          <button type="reset" disabled={isBusy} onClick={() => { clearPasswords(); setFeedback(null); setRevealed({ current: false, next: false, confirm: false }); }} style={ACTION_BUTTON_STYLE}>
            Clear fields
          </button>
        </div>
      </form>
    </section>
  );
}

export default PasswordChangeForm;
