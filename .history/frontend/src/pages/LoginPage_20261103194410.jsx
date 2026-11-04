
/*
  Dormora - File 14
  Login page UI only.

  IMPORTANT: This screen does not authenticate users yet.
  FastAPI authentication, CAPTCHA, OTP, and lockout rules
  will be connected in later development steps.
*/

import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CalendarDays,
  Eye,
  EyeOff,
  House,
  KeyRound,
  LockKeyhole,
  Moon,
  ShieldCheck,
  Sun,
  UserRound,
  Wallet,
} from "lucide-react";
import "../App.css";

function LoginPage() {
  const [darkMode, setDarkMode] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Prevent Enter from submitting the preview form.
  // We must not pretend a user has logged in without the backend.
  function handlePreviewSubmit(event) {
    event.preventDefault();
  }

  return (
    <div className={darkMode ? "dormora dark-mode login-page" : "dormora light-mode login-page"}>
      {/* Keep the approved system title above the navigation. */}
      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>

      {/* The login page has simpler navigation than the landing page. */}
      <header className="site-header">
        <div className="page-container header-content">
          <Link className="brand" to="/">
            <House size={29} strokeWidth={2.5} />
            <span>Dormora</span>
          </Link>

          <nav className="login-header-nav" aria-label="Login page navigation">
            <Link to="/">Home</Link>
            <button
              type="button"
              className="login-register-nav"
              disabled
              title="Registration will be available after proposal approval"
            >
              Register
            </button>
            <button
              type="button"
              className="theme-button"
              onClick={() => setDarkMode(!darkMode)}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              title={darkMode ? "Light mode" : "Dark mode"}
            >
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>
          </nav>
        </div>
      </header>

      <main className="login-main">
        <div className="page-container login-layout">
          {/* Left side: a simple description of Dormora. */}
          <section className="login-intro" aria-labelledby="login-intro-heading">
            <span className="login-eyebrow">
              <ShieldCheck size={17} /> Your Dormora workspace
            </span>
            <h1 id="login-intro-heading">
              Your rental life,
              <span> all in one place.</span>
            </h1>
            <p>
              Log in to return to your rental records, payment history, and
              property management tools when your account is ready.
            </p>

            <div className="login-benefits">
              <div className="login-benefit">
                <div className="login-benefit-icon"><CalendarDays size={21} /></div>
                <div>
                  <h3>Stay on top of rent</h3>
                  <p>Keep due dates and recorded payments organized.</p>
                </div>
              </div>
              <div className="login-benefit">
                <div className="login-benefit-icon"><Wallet size={21} /></div>
                <div>
                  <h3>Review your records</h3>
                  <p>Access your personal rental and deposit information.</p>
                </div>
              </div>
              <div className="login-benefit">
                <div className="login-benefit-icon"><KeyRound size={21} /></div>
                <div>
                  <h3>Secure access is planned</h3>
                  <p>Password, CAPTCHA, and email OTP checks will be added with the backend.</p>
                </div>
              </div>
            </div>
          </section>

          {/* Right side: form layout only, not an active login. */}
          <section className="login-card" aria-labelledby="login-form-heading">
            <div className="login-card-icon"><LockKeyhole size={26} /></div>
            <h2 id="login-form-heading">Welcome back</h2>
            <p className="login-card-subtitle">Enter your account details to continue.</p>

            <form className="login-form" onSubmit={handlePreviewSubmit}>
              <div className="login-field">
                <label htmlFor="login-username">
                  Username <span className="login-required">*</span>
                </label>
                <div className="login-input-wrap">
                  <UserRound size={19} aria-hidden="true" />
                  <input
                    id="login-username"
                    name="username"
                    type="text"
                    placeholder="Enter your username"
                    autoComplete="username"
                    spellCheck={false}
                    required
                  />
                </div>
              </div>

              <div className="login-field">
                <label htmlFor="login-password">
                  Password <span className="login-required">*</span>
                </label>
                <div className="login-input-wrap">
                  <LockKeyhole size={19} aria-hidden="true" />
                  <input
                    id="login-password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="Enter your password"
                    autoComplete="current-password"
                    required
                  />
                  <button
                    className="login-password-toggle"
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    title={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                  >
                    {showPassword ? <EyeOff size={19} /> : <Eye size={19} />}
                  </button>
                </div>
              </div>

              <div className="login-form-options">
                <span>Fields marked * are required.</span>
                <button
                  type="button"
                  className="login-forgot-button"
                  disabled
                  title="Password recovery is not implemented yet"
                >
                  Forgot password?
                </button>
              </div>

              {/* Placeholder only. Real CAPTCHA requires server verification. */}
              <div className="login-captcha-note" role="note">
                <ShieldCheck size={19} />
                <span>CAPTCHA verification will appear here when authentication is connected.</span>
              </div>

              <button type="submit" className="login-submit-button" disabled>
                Log In <ArrowRight size={19} />
              </button>
            </form>

            <p className="login-preview-message">
              Frontend preview only. Login will be enabled after FastAPI,
              CAPTCHA, and 6-digit email OTP verification are implemented.
            </p>
            <div className="login-register-message">
              New to Dormora? Registration will be available after proposal approval.
            </div>
          </section>
        </div>
      </main>

      {/* Minimal footer: the shared Footer links currently target landing-page sections. */}
      <footer className="site-footer">
        <div className="page-container login-footer-content">
          <span>© 2026 Dormora. All rights reserved.</span>
          <Link to="/">Back to Home</Link>
        </div>
      </footer>
    </div>
  );
}

export default LoginPage;
