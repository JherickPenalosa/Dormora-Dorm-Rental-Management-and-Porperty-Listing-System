/*
  Dormora — Frontend File 58
  Destination: frontend/src/pages/PrivacyNoticePage.jsx (NEW FILE)

  Standalone, responsive DRAFT Privacy Notice page.
  - Uses Dormora's existing light/dark theme, header and footer.
  - Does not submit forms, collect data, activate registration, or change consent.
  - Do not publish this notice as final until the controller/contact,
    retention schedule, data sharing and approved proposal are reviewed.
  - File 59 will add /privacy to App.jsx.
*/

import { Link } from "react-router-dom";
import {
  ArrowLeft,
  BookOpen,
  House,
  LockKeyhole,
  Mail,
  Moon,
  ShieldCheck,
  Sun,
} from "lucide-react";
import "../App.css";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "information", label: "Information we collect" },
  { id: "purposes", label: "Why we use information" },
  { id: "sharing", label: "Disclosure and services" },
  { id: "protection", label: "How information is protected" },
  { id: "retention", label: "Retention and deletion" },
  { id: "rights", label: "Your privacy rights" },
  { id: "contact", label: "Privacy contact" },
];

export default function PrivacyNoticePage({ darkMode = false, onToggleTheme }) {
  return (
    <div className={`dormora ${darkMode ? "dark-mode" : "light-mode"} privacy-page`}>
      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>

      <header className="site-header">
        <div className="page-container header-content privacy-nav">
          <Link className="brand" to="/" aria-label="Dormora home">
            <House size={29} strokeWidth={2.5} />
            <span>Dormora</span>
          </Link>
          <nav className="privacy-nav-actions" aria-label="Privacy page navigation">
            <Link to="/">Home</Link>
            <Link to="/register" className="login-register-nav">Register</Link>
            <button
              className="theme-button"
              type="button"
              onClick={onToggleTheme}
              disabled={!onToggleTheme}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
            >
              {darkMode ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </nav>
        </div>
      </header>

      <main className="privacy-main" id="main-content">
        <div className="page-container privacy-wrap">
          <div className="privacy-hero">
            <div className="privacy-eyebrow"><ShieldCheck size={16} /> Transparency and security</div>
            <h1>Privacy Notice</h1>
            <p>
              Learn how Dormora plans to handle personal information when you create
              a renter or property-owner account and use rental management features.
            </p>
            <div className="privacy-metadata">
              <span><BookOpen size={15} /> Data Privacy Act of 2012 (RA 10173)</span>
              <span>Draft prepared November 5, 2026</span>
            </div>
          </div>

          <div className="privacy-draft" role="note">
            <LockKeyhole size={20} aria-hidden="true" />
            <div>
              <strong>Development draft — not yet ready for public consent</strong>
              <p>
                The identity and contact details of the responsible data controller,
                the precise retention schedule, and final data-sharing arrangements
                must be confirmed before public registration is enabled.
              </p>
            </div>
          </div>

          <div className="privacy-layout">
            <aside className="privacy-sidebar" aria-label="Privacy Notice contents">
              <div className="privacy-toc">
                <h2>On this page</h2>
                {SECTIONS.map((section) => (
                  <a href={`#${section.id}`} key={section.id}>
                    {section.label}
                  </a>
                ))}
              </div>
            </aside>

            <article className="privacy-document" aria-label="Dormora Privacy Notice draft">
              <section id="overview" className="privacy-section">
                <h2>01. Overview</h2>
                <p>
                  Dormora is a web-based rental management and property listing
                  project for renters and property owners aged 18 or older. This
                  notice explains the personal information needed to register,
                  verify an account, protect access, and provide the planned
                  rental-management services.
                </p>
                <p>
                  Before submitting a real registration form, users must be able to
                  read this notice and make a separate, affirmative privacy-consent
                  choice. Consent is not recorded merely by viewing this page.
                </p>
              </section>

              <section id="information" className="privacy-section">
                <h2>02. Information we collect</h2>
                <p>Depending on the features you use, Dormora's planned data includes:</p>
                <ul>
                  <li><strong>Identity:</strong> ID number, first/middle/family name, name extension, birthdate and age eligibility.</li>
                  <li><strong>Contact and address:</strong> email, purok/street, barangay, city/municipality, province, country and ZIP code.</li>
                  <li><strong>Account and security:</strong> username, protected password and recovery-answer hashes, email-verification records, consent timestamp, account status, IP address, browser information and security event logs.</li>
                  <li><strong>Renter preferences:</strong> preferred rental type, area, maximum monthly budget and target move-in date, if provided.</li>
                  <li><strong>Property-owner details:</strong> property type, area, expected monthly rent and availability date, if provided.</li>
                  <li><strong>Service records:</strong> property listings, applications, agreements and rental-management records when those features become available.</li>
                </ul>
                <p>
                  Dormora does not include online payment processing in its current
                  project scope. The exact field requirements will be reconciled
                  with the approved project proposal before registration is enabled.
                </p>
              </section>

              <section id="purposes" className="privacy-section">
                <h2>03. Why we use information</h2>
                <ul>
                  <li>Create and verify accounts, confirm age eligibility and distinguish renter from property-owner access.</li>
                  <li>Help renters organize rental-related information and help owners manage their authorized property listings.</li>
                  <li>Send email verification codes, account-recovery messages and relevant security notifications.</li>
                  <li>Prevent abuse, investigate suspicious requests and maintain security audit records.</li>
                  <li>Record when consent was given and respond to account or privacy requests.</li>
                </ul>
                <p>
                  Registration consent must be explicit and is unchecked by default.
                  Some processing may later rely on another applicable legal basis;
                  that basis must be identified before deployment where relevant.
                </p>
              </section>

              <section id="sharing" className="privacy-section">
                <h2>04. Disclosure and external services</h2>
                <p>
                  Authorized application roles may access information needed for
                  their permitted features. If an owner publishes a property
                  listing, information intentionally included in that listing may
                  be visible to prospective renters; private account credentials
                  and recovery answers are not intended for listing display.
                </p>
                <p>
                  Dormora's development setup includes Google reCAPTCHA v2 for
                  automated-request protection and Gmail SMTP for registration
                  emails. Those services process data needed to provide their
                  respective functions under their own terms. PostgreSQL stores
                  application records. Any hosting provider, additional recipients,
                  and cross-border transfers must be reviewed before deployment.
                </p>
                <p>
                  This draft does not authorize the sale of personal data or
                  unrelated marketing use. Any proposed new purpose or recipient
                  must be reviewed and disclosed first.
                </p>
              </section>

              <section id="protection" className="privacy-section">
                <h2>05. How information is protected</h2>
                <p>
                  The backend is being developed with server-side validation,
                  password and recovery-answer hashing, protected OTP records,
                  CSRF protection, CAPTCHA, access restrictions, request limits and
                  security logging. Verification codes are intended to expire and
                  be single-use. The project must also use HTTPS and appropriate
                  operational safeguards before public deployment.
                </p>
                <p>
                  These are development controls, not a claim that every security
                  requirement has passed production testing. No internet-connected
                  service can guarantee absolute security.
                </p>
              </section>

              <section id="retention" className="privacy-section">
                <h2>06. Retention and deletion</h2>
                <p>
                  Account, rental and security records should be retained only
                  for documented, legitimate purposes and applicable obligations.
                  Short-lived OTPs expire under the current three-minute policy,
                  but database record cleanup is a separate process that still
                  requires verification.
                </p>
                <div className="privacy-pending">
                  <strong>Retention schedule — confirmation required</strong>
                  <p>
                    Before launch, specify the actual retention periods for active
                    accounts, unverified registrations, security logs, rental
                    records and backups, together with deletion procedures.
                    No specific retention duration is represented as finalized here.
                  </p>
                </div>
              </section>

              <section id="rights" className="privacy-section">
                <h2>07. Your privacy rights</h2>
                <p>
                  Subject to applicable conditions under RA 10173, data subjects
                  may request information about processing, access and correction,
                  object to certain processing, and request blocking or erasure.
                  Other applicable rights include data portability, damages and
                  filing a complaint with the National Privacy Commission.
                </p>
                <p>
                  The procedure for submitting and validating requests must be
                  published together with the finalized privacy contact.
                  For official guidance, see the{" "}
                  <a href="https://privacy.gov.ph/data-subject-rights/" target="_blank" rel="noopener noreferrer">
                    National Privacy Commission's data-subject rights page
                  </a>.
                </p>
              </section>

              <section id="contact" className="privacy-section">
                <h2>08. Privacy contact</h2>
                <p>
                  The responsible personal information controller and a working
                  privacy contact channel must be identified before Dormora accepts
                  real registrations.
                </p>
                <div className="privacy-contact">
                  <Mail size={21} aria-hidden="true" />
                  <div>
                    <strong>Contact details pending confirmation</strong>
                    <span>Controller/representative: to be designated</span>
                    <span>Privacy email/contact channel: to be provided</span>
                  </div>
                </div>
                <p>
                  Users may consult the{" "}
                  <a href="https://privacy.gov.ph/" target="_blank" rel="noopener noreferrer">
                    National Privacy Commission website
                  </a>{" "}
                  for official information about privacy rights and complaints.
                </p>
              </section>

              <div className="privacy-bottom-actions">
                <Link to="/register" className="privacy-back">
                  <ArrowLeft size={17} /> Back to registration
                </Link>
                <span>Reading this draft does not constitute consent.</span>
              </div>
            </article>
          </div>
        </div>
      </main>

      <footer className="site-footer">
        <div className="page-container login-footer-content">
          <span>© 2026 Dormora. All rights reserved.</span>
          <Link to="/">Back to Home</Link>
        </div>
      </footer>

      {/* File 58 uses scoped CSS so we preserve the existing App.css unchanged. */}
      <style>{`
        .privacy-page { min-height: 100vh; display: flex; flex-direction: column; }
        .privacy-nav-actions { display: flex; align-items: center; gap: 16px; }
        .privacy-nav-actions > a:not(.login-register-nav) { font-size: 13px; font-weight: 700; }
        .privacy-nav-actions > a:hover { color: var(--primary); }
        .privacy-main { flex: 1; padding: 44px 0 74px; }
        .privacy-wrap { max-width: 1130px; }
        .privacy-hero { max-width: 830px; margin: 0 0 24px; }
        .privacy-eyebrow { display: inline-flex; align-items: center; gap: 8px; padding: 7px 12px; border: 1px solid var(--border); border-radius: 50px; background: var(--card); color: var(--primary); font-size: 12px; font-weight: 750; }
        .privacy-hero h1 { margin: 17px 0 12px; font-size: clamp(32px, 4vw, 46px); font-weight: 800; line-height: 1.12; letter-spacing: -1.1px; }
        .privacy-hero > p { max-width: 740px; color: var(--muted); font-size: 14px; line-height: 1.8; }
        .privacy-metadata { display: flex; flex-wrap: wrap; gap: 8px 23px; color: var(--muted); font-size: 12px; }
        .privacy-metadata span { display: inline-flex; align-items: center; gap: 6px; }
        .privacy-draft { display: flex; align-items: flex-start; gap: 13px; padding: 17px 19px; border: 1px solid var(--border); border-left: 4px solid var(--primary); border-radius: 13px; background: var(--soft); margin: 28px 0 25px; }
        .privacy-draft > svg { flex-shrink: 0; margin-top: 2px; color: var(--primary); }
        .privacy-draft strong { font-size: 13px; }
        .privacy-draft p { margin: 5px 0 0; color: var(--muted); line-height: 1.7; font-size: 12px; }
        .privacy-layout { display: grid; grid-template-columns: 235px minmax(0, 1fr); align-items: start; gap: 23px; }
        .privacy-sidebar { position: sticky; top: 100px; }
        .privacy-toc, .privacy-document { background: var(--card); border: 1px solid var(--border); border-radius: 17px; }
        .privacy-toc { display: flex; flex-direction: column; gap: 3px; padding: 19px 13px; }
        .privacy-toc h2 { font-size: 12px; margin: 0 10px 12px; color: var(--muted); letter-spacing: .3px; text-transform: uppercase; }
        .privacy-toc a { padding: 10px; border-radius: 8px; color: var(--muted); font-size: 12px; font-weight: 600; }
        .privacy-toc a:hover, .privacy-toc a:focus-visible { background: var(--soft); color: var(--primary); }
        .privacy-document { padding: clamp(19px, 3.3vw, 40px); }
        .privacy-section { padding: 0 0 25px; margin: 0 0 26px; border-bottom: 1px solid var(--border); scroll-margin-top: 110px; }
        .privacy-section h2 { margin: 0 0 13px; font-size: 19px; letter-spacing: -.3px; }
        .privacy-section p, .privacy-section li { color: var(--muted); font-size: 13px; line-height: 1.85; }
        .privacy-section p { margin: 0 0 12px; }
        .privacy-section ul { margin: 7px 0 15px; padding-left: 21px; }
        .privacy-section li { padding-left: 3px; margin-bottom: 8px; }
        .privacy-section li strong { color: var(--text); }
        .privacy-section a { color: var(--primary); text-decoration: underline; text-underline-offset: 3px; }
        .privacy-pending { padding: 14px 17px; background: var(--soft); border: 1px solid var(--border); border-radius: 12px; }
        .privacy-pending strong { font-size: 12px; }
        .privacy-pending p { margin: 5px 0 0; font-size: 12px; }
        .privacy-contact { display: flex; gap: 12px; padding: 16px; background: var(--soft); border: 1px solid var(--border); border-radius: 12px; }
        .privacy-contact > svg { color: var(--primary); flex-shrink: 0; }
        .privacy-contact > div { display: grid; gap: 4px; }
        .privacy-contact strong { font-size: 13px; }
        .privacy-contact span { color: var(--muted); font-size: 12px; }
        .privacy-bottom-actions { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 15px; }
        .privacy-back { display: inline-flex; align-items: center; gap: 8px; padding: 11px 15px; border: 1px solid var(--primary); border-radius: 9px; color: var(--primary) !important; font-size: 13px; font-weight: 750; }
        .privacy-back:hover { background: var(--soft); }
        .privacy-bottom-actions > span { color: var(--muted); font-size: 11px; }
        @media (max-width: 790px) { .privacy-layout { grid-template-columns: 1fr; } .privacy-sidebar { position: static; } .privacy-toc { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); } .privacy-toc h2 { grid-column: 1 / -1; } }
        @media (max-width: 520px) { .privacy-main { padding-top: 27px; } .privacy-nav { display: flex; flex-wrap: wrap; } .privacy-nav-actions { gap: 9px; } .privacy-nav-actions > a:not(.login-register-nav) { display: none; } .privacy-toc { grid-template-columns: 1fr; } .privacy-section h2 { font-size: 17px; } .privacy-draft { padding: 13px; } }
      `}</style>
    </div>
  );
}
