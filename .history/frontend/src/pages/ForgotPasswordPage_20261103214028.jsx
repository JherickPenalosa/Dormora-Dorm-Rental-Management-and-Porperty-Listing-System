
/*
  Dormora - File 29
  Forgot Password page (frontend-only appearance).

  The four recovery stages are explanatory, not clickable. There is no
  username lookup, CAPTCHA check, security-answer validation, OTP issuance,
  or password reset without the FastAPI backend.
*/

import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  CircleHelp,
  House,
  KeyRound,
  LockKeyhole,
  MailCheck,
  Moon,
  ShieldCheck,
  Sun,
  UserRound,
} from "lucide-react";
import "../App.css";

const recoverySteps = [
  {
    number: "01",
    title: "Identify your account",
    description: "Enter your username and complete CAPTCHA verification.",
    icon: UserRound,
  },
  {
    number: "02",
    title: "Answer a security question",
    description:
      "Select one of your three registered questions, then enter and re-enter the answer.",
    icon: CircleHelp,
  },
  {
    number: "03",
    title: "Verify your email",
    description: "Confirm the one-time code sent to your registered email.",
    icon: MailCheck,
  },
  {
    number: "04",
    title: "Create a new password",
    description: "Change your password only after every recovery check succeeds.",
    icon: KeyRound,
  },
];

function ForgotPasswordPage({ darkMode, onToggleTheme }) {
  const [username, setUsername] = useState("");

  function handlePreviewSubmit(event) {
    // No recovery information is submitted or stored in this preview.
    event.preventDefault();
  }

  return (
    <div
      className={`dormora ${darkMode ? "dark-mode" : "light-mode"} forgot-page`}
    >
      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>

      <header className="site-header">
        <div className="page-container header-content forgot-header-content">
          <Link className="brand" to="/" aria-label="Dormora home">
            <House size={29} strokeWidth={2.5} />
            <span>Dormora</span>
          </Link>

          <nav className="forgot-header-nav" aria-label="Password recovery navigation">
            <Link to="/">Home</Link>
            <Link className="forgot-header-login" to="/login">
              Log In
            </Link>
            <button
              className="theme-button"
              type="button"
              onClick={onToggleTheme}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              title={darkMode ? "Light mode" : "Dark mode"}
            >
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>
          </nav>
        </div>
      </header>

      <main className="forgot-main">
        <div className="page-container forgot-layout">
          <section className="forgot-intro" aria-labelledby="forgot-page-title">
            <span className="forgot-eyebrow">
              <ShieldCheck size={17} aria-hidden="true" />
              Account security
            </span>

            <h1 id="forgot-page-title">
              Forgot your <span>password?</span>
            </h1>

            <p className="forgot-description">
              Dormora uses a step-by-step recovery process to help protect your
              rental records and personal information.
            </p>

            <ol className="forgot-steps" aria-label="Account recovery steps">
              {recoverySteps.map((step, index) => {
                const StepIcon = step.icon;
                return (
                  <li
                    className={`forgot-step ${index === 0 ? "is-current" : ""}`}
                    key={step.number}
                  >
                    <span className="forgot-step-number" aria-hidden="true">
                      {step.number}
                    </span>
                    <span className="forgot-step-icon" aria-hidden="true">
                      <StepIcon size={19} />
                    </span>
                    <span className="forgot-step-copy">
                      <strong>{step.title}</strong>
                      <small>{step.description}</small>
                    </span>
                    {index === 0 && (
                      <span className="forgot-current-label">Preview</span>
                    )}
                  </li>
                );
              })}
            </ol>

            <div className="forgot-info-note" role="note">
              <CheckCircle2 size={20} aria-hidden="true" />
              <span>
                Recovery steps 2–4 are shown for reference only. You cannot
                access them until the backend verifies each preceding step.
              </span>
            </div>
          </section>

          <section className="forgot-card" aria-labelledby="forgot-card-title">
            <div className="forgot-card-icon" aria-hidden="true">
              <LockKeyhole size={26} />
            </div>
            <div className="forgot-card-step">Step 1 of 4 · UI preview</div>
            <h2 id="forgot-card-title">Find your account</h2>
            <p className="forgot-card-subtitle">
              Enter the username associated with your Dormora account.
            </p>

            <form className="forgot-form" onSubmit={handlePreviewSubmit}>
              <div className="forgot-field">
                <label htmlFor="forgot-username">
                  Username <span className="forgot-required">*</span>
                </label>
                <div className="forgot-input-wrap">
                  <UserRound size={19} aria-hidden="true" />
                  <input
                    id="forgot-username"
                    name="username"
                    type="text"
                    placeholder="Enter your username"
                    autoComplete="username"
                    spellCheck={false}
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    required
                  />
                </div>
              </div>

              <div className="forgot-captcha-preview" role="note">
                <ShieldCheck size={21} aria-hidden="true" />
                <div>
                  <strong>CAPTCHA verification</strong>
                  <p>
                    The real CAPTCHA challenge will be added and checked by
                    FastAPI during backend integration.
                  </p>
                </div>
              </div>

              <button className="forgot-submit-button" type="submit" disabled>
                Continue securely
                <ArrowRight size={18} aria-hidden="true" />
              </button>
            </form>

            <p className="forgot-preview-message">
              Frontend preview only. No username is checked, no email is sent,
              and no password can be reset yet.
            </p>

            <div className="forgot-card-footer">
              <Link to="/login">
                <ArrowLeft size={17} aria-hidden="true" />
                Back to Log In
              </Link>
              <Link to="/register">Create an account</Link>
            </div>
          </section>
        </div>
      </main>

      <footer className="site-footer">
        <div className="page-container login-footer-content">
          <span>© 2026 Dormora. All rights reserved.</span>
          <Link to="/">Back to Home</Link>
        </div>
      </footer>
    </div>
  );
}

export default ForgotPasswordPage;
