
/*
  Dormora - File 28
  Registration page preview with consistent Login navigation.

  No account is created and no data is sent to a server.
  The final security questions, validation limits, and additional
  system fields must match the approved proposal and student seed.
*/

import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Eye,
  EyeOff,
  House,
  LockKeyhole,
  Moon,
  ShieldCheck,
  Sun,
  UserRoundPlus,
} from "lucide-react";
import "../App.css";

// Age is displayed for convenience. FastAPI must calculate and verify it again.
function calculateAge(birthdate) {
  if (!birthdate) return null;

  const birth = new Date(`${birthdate}T00:00:00`);
  if (Number.isNaN(birth.getTime())) return null;

  const today = new Date();
  if (birth > today) return null;

  let age = today.getFullYear() - birth.getFullYear();
  const monthDifference = today.getMonth() - birth.getMonth();

  if (
    monthDifference < 0 ||
    (monthDifference === 0 && today.getDate() < birth.getDate())
  ) {
    age -= 1;
  }

  return age;
}

function RegisterPage({ darkMode, onToggleTheme }) {
  const [accountType, setAccountType] = useState("renter");
  const [birthdate, setBirthdate] = useState("");
  const [extension, setExtension] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [privacyAccepted, setPrivacyAccepted] = useState(false);

  const age = calculateAge(birthdate);
  const isOwner = accountType === "owner";

  // No registration request is sent from this frontend-only preview.
  function handlePreviewSubmit(event) {
    event.preventDefault();
  }

  return (
    <div
      className={
        darkMode
          ? "dormora dark-mode register-page"
          : "dormora light-mode register-page"
      }
    >
      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>

      <header className="site-header">
        <div className="page-container header-content register-header-content">
          <Link className="brand" to="/">
            <House size={29} strokeWidth={2.5} />
            <span>Dormora</span>
          </Link>

          <nav
            className="register-header-nav"
            aria-label="Registration navigation"
          >
            <Link to="/">Home</Link>

            {/* File 28: Consistent Login navigation */}
            <Link
              className="login-register-nav"
              to="/login"
              aria-label="Go to Log In page"
            >
              Log In
            </Link>

            <button
              className="theme-button"
              type="button"
              onClick={onToggleTheme}
              aria-label={
                darkMode ? "Switch to light mode" : "Switch to dark mode"
              }
              title={darkMode ? "Light mode" : "Dark mode"}
            >
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>
          </nav>
        </div>
      </header>

      <main className="register-main">
        <div className="page-container register-layout">
          <div className="register-intro">
            <div className="register-heading">
              <span className="register-eyebrow">
                <UserRoundPlus size={17} /> Join Dormora
              </span>

              <h1>Create your account</h1>

              <p>
                Set up a renter or property-owner profile. This is a design
                preview; registration and verification are not active yet.
              </p>
            </div>

            <div className="register-security-note" role="note">
              <ShieldCheck size={21} />

              <div>
                <strong>Privacy and security first</strong>
                <p>
                  The completed registration process will validate information
                  on the server and require CAPTCHA, email OTP, and privacy consent.
                </p>
              </div>
            </div>
          </div>

          <form className="register-form" onSubmit={handlePreviewSubmit}>

            {/* SECTION 1: ACCOUNT TYPE */}
            <section
              className="register-section"
              aria-labelledby="register-role-title"
            >
              <div className="register-section-heading">
                <span className="register-step-number">01</span>
                <div>
                  <h2 id="register-role-title">Choose your account type</h2>
                  <p>Select how you'll use Dormora.</p>
                </div>
              </div>

              <div className="register-role-options">
                <label
                  className={`register-role-option ${
                    !isOwner ? "is-selected" : ""
                  }`}
                >
                  <input
                    type="radio"
                    name="accountType"
                    value="renter"
                    checked={!isOwner}
                    onChange={() => setAccountType("renter")}
                  />
                  <span>
                    <strong>Renter</strong>
                    <small>Discover rentals and track rent and deposits</small>
                  </span>
                  {!isOwner && (
                    <CheckCircle2 size={19} aria-hidden="true" />
                  )}
                </label>

                <label
                  className={`register-role-option ${
                    isOwner ? "is-selected" : ""
                  }`}
                >
                  <input
                    type="radio"
                    name="accountType"
                    value="owner"
                    checked={isOwner}
                    onChange={() => setAccountType("owner")}
                  />
                  <span>
                    <strong>Property Owner</strong>
                    <small>
                      Create and manage rental listings after approval
                    </small>
                  </span>
                  {isOwner && (
                    <CheckCircle2 size={19} aria-hidden="true" />
                  )}
                </label>
              </div>

              {isOwner && (
                <p className="register-inline-note">
                  Property-owner accounts will require administrator review
                  before listing-management permissions are granted.
                </p>
              )}
            </section>

            {/* SECTION 2: PERSONAL INFORMATION */}
            <section
              className="register-section"
              aria-labelledby="register-personal-title"
            >
              <div className="register-section-heading">
                <span className="register-step-number">02</span>
                <div>
                  <h2 id="register-personal-title">Personal information</h2>
                  <p>
                    Fields marked{" "}
                    <span className="register-required">*</span>{" "}
                    are required.
                  </p>
                </div>
              </div>

              <div className="register-fields-grid">

                <div className="register-field register-full-width">
                  <label htmlFor="register-id">
                    ID Number{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-id"
                    name="idNumber"
                    type="text"
                    inputMode="numeric"
                    placeholder="xxxx-xxxx"
                    maxLength={9}
                    autoComplete="off"
                  />
                  <small>
                    Required instructor format: four digits, a hyphen,
                    four digits.
                  </small>
                </div>

                <div className="register-field">
                  <label htmlFor="register-first-name">
                    First Name{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-first-name"
                    name="firstName"
                    type="text"
                    placeholder="Juan"
                    autoComplete="given-name"
                  />
                </div>

                <div className="register-field">
                  <label htmlFor="register-middle-name">
                    Middle Name <em>(Optional)</em>
                  </label>
                  <input
                    id="register-middle-name"
                    name="middleName"
                    type="text"
                    placeholder="Optional"
                    autoComplete="additional-name"
                  />
                </div>

                <div className="register-field">
                  <label htmlFor="register-family-name">
                    Family Name{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-family-name"
                    name="familyName"
                    type="text"
                    placeholder="Dela Cruz"
                    autoComplete="family-name"
                  />
                </div>

                <div className="register-field">
                  <label htmlFor="register-extension">
                    Name Extension <em>(Optional)</em>
                  </label>
                  <select
                    id="register-extension"
                    name="nameExtension"
                    value={extension}
                    onChange={(event) =>
                      setExtension(event.target.value)
                    }
                  >
                    <option value="">None</option>
                    <option value="Jr.">Jr.</option>
                    <option value="Sr.">Sr.</option>
                    <option value="Other">Other</option>
                  </select>
                </div>

                {extension === "Other" && (
                  <div className="register-field register-full-width">
                    <label htmlFor="register-other-extension">
                      Other Extension{" "}
                      <span className="register-required">*</span>
                    </label>
                    <input
                      id="register-other-extension"
                      name="otherExtension"
                      type="text"
                      placeholder="I, II, III, IV, IX or X"
                    />
                  </div>
                )}

                <div className="register-field">
                  <label htmlFor="register-birthdate">
                    Birthdate{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-birthdate"
                    name="birthdate"
                    type="date"
                    value={birthdate}
                    onChange={(event) =>
                      setBirthdate(event.target.value)
                    }
                  />
                </div>

                <div className="register-field">
                  <label htmlFor="register-age">
                    Age (calculated automatically)
                  </label>
                  <input
                    id="register-age"
                    name="ageDisplay"
                    type="text"
                    value={age === null ? "" : String(age)}
                    placeholder="Calculated from birthdate"
                    readOnly
                  />
                  {age !== null && age < 18 && (
                    <small
                      className="register-field-error"
                      role="alert"
                    >
                      You must be at least 18 years old to register.
                    </small>
                  )}
                </div>

              </div>
            </section>

            {/* SECTION 3: HOME ADDRESS */}
            <section
              className="register-section"
              aria-labelledby="register-address-title"
            >
              <div className="register-section-heading">
                <span className="register-step-number">03</span>
                <div>
                  <h2 id="register-address-title">Home address</h2>
                  <p>
                    Enter your residential address, not the property
                    listing's address.
                  </p>
                </div>
              </div>

              <div className="register-fields-grid">

                <div className="register-field register-full-width">
                  <label htmlFor="register-street">
                    Purok / Street{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-street"
                    name="street"
                    type="text"
                    placeholder="Purok 2"
                    autoComplete="address-line1"
                  />
                </div>

                <div className="register-field">
                  <label htmlFor="register-barangay">
                    Barangay{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-barangay"
                    name="barangay"
                    type="text"
                    placeholder="Your barangay"
                  />
                </div>

                <div className="register-field">
                  <label htmlFor="register-city">
                    Municipality / City{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-city"
                    name="city"
                    type="text"
                    placeholder="Your city"
                    autoComplete="address-level2"
                  />
                </div>

                <div className="register-field">
                  <label htmlFor="register-province">
                    Province{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-province"
                    name="province"
                    type="text"
                    placeholder="Your province"
                    autoComplete="address-level1"
                  />
                </div>

                <div className="register-field">
                  <label htmlFor="register-country">
                    Country{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-country"
                    name="country"
                    type="text"
                    placeholder="Philippines"
                    autoComplete="country-name"
                  />
                </div>

                <div className="register-field">
                  <label htmlFor="register-zip">
                    ZIP Code{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-zip"
                    name="zipCode"
                    type="text"
                    inputMode="numeric"
                    maxLength={4}
                    placeholder="Four digits"
                    autoComplete="postal-code"
                  />
                </div>

              </div>
            </section>

            {/* SECTION 4: DORMORA-SPECIFIC DETAILS */}
            <section
              className="register-section"
              aria-labelledby="register-rental-title"
            >
              <div className="register-section-heading">
                <span className="register-step-number">04</span>
                <div>
                  <h2 id="register-rental-title">
                    {isOwner
                      ? "Property-owner details"
                      : "Rental preferences"}
                  </h2>
                  <p>
                    Proposed Dormora-specific fields for your project.
                    These are optional profile details in this preview
                    and must match your approved proposal.
                  </p>
                </div>
              </div>

              {isOwner ? (
                <div
                  className="register-fields-grid"
                  key="owner-fields"
                >
                  <div className="register-field">
                    <label htmlFor="owner-property-type">
                      Primary Property Type <em>(Optional)</em>
                    </label>
                    <select
                      id="owner-property-type"
                      name="primaryPropertyType"
                      defaultValue=""
                    >
                      <option value="">Select property type</option>
                      <option value="dormitory">Dormitory</option>
                      <option value="boarding-house">Boarding house</option>
                      <option value="apartment">Apartment</option>
                      <option value="room">Room for rent</option>
                    </select>
                  </div>

                  <div className="register-field">
                    <label htmlFor="owner-property-area">
                      Primary Property Area <em>(Optional)</em>
                    </label>
                    <input
                      id="owner-property-area"
                      name="primaryPropertyArea"
                      type="text"
                      placeholder="City or barangay"
                    />
                  </div>

                  <div className="register-field">
                    <label htmlFor="owner-rent">
                      Expected Monthly Rent (₱) <em>(Optional)</em>
                    </label>
                    <input
                      id="owner-rent"
                      name="expectedRent"
                      type="number"
                      min="0"
                      step="100"
                      placeholder="e.g. 4500"
                    />
                  </div>

                  <div className="register-field">
                    <label htmlFor="owner-available">
                      Expected Availability Date <em>(Optional)</em>
                    </label>
                    <input
                      id="owner-available"
                      name="expectedAvailableDate"
                      type="date"
                    />
                  </div>
                </div>
              ) : (
                <div
                  className="register-fields-grid"
                  key="renter-fields"
                >
                  <div className="register-field">
                    <label htmlFor="renter-room-type">
                      Preferred Rental Type <em>(Optional)</em>
                    </label>
                    <select
                      id="renter-room-type"
                      name="preferredRentalType"
                      defaultValue=""
                    >
                      <option value="">Select preference</option>
                      <option value="shared">Shared room</option>
                      <option value="private">Private room</option>
                      <option value="either">Either</option>
                    </select>
                  </div>

                  <div className="register-field">
                    <label htmlFor="renter-area">
                      Preferred Rental Area <em>(Optional)</em>
                    </label>
                    <input
                      id="renter-area"
                      name="preferredRentalArea"
                      type="text"
                      placeholder="City or barangay"
                    />
                  </div>

                  <div className="register-field">
                    <label htmlFor="renter-budget">
                      Maximum Monthly Budget (₱) <em>(Optional)</em>
                    </label>
                    <input
                      id="renter-budget"
                      name="monthlyBudget"
                      type="number"
                      min="0"
                      step="100"
                      placeholder="e.g. 5000"
                    />
                  </div>

                  <div className="register-field">
                    <label htmlFor="renter-move-in">
                      Target Move-in Date <em>(Optional)</em>
                    </label>
                    <input
                      id="renter-move-in"
                      name="targetMoveInDate"
                      type="date"
                    />
                  </div>
                </div>
              )}
            </section>

            {/* SECTION 5: ACCOUNT CREDENTIALS */}
            <section
              className="register-section"
              aria-labelledby="register-account-title"
            >
              <div className="register-section-heading">
                <span className="register-step-number">05</span>
                <div>
                  <h2 id="register-account-title">
                    Account credentials
                  </h2>
                  <p>
                    Your email will receive verification codes and
                    security alerts.
                  </p>
                </div>
              </div>

              <div className="register-fields-grid">

                <div className="register-field register-full-width">
                  <label htmlFor="register-email">
                    Email Address{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-email"
                    name="email"
                    type="email"
                    placeholder="you@example.com"
                    autoComplete="email"
                  />
                </div>

                <div className="register-field register-full-width">
                  <label htmlFor="register-username">
                    Username{" "}
                    <span className="register-required">*</span>
                  </label>
                  <input
                    id="register-username"
                    name="username"
                    type="text"
                    placeholder="Choose a username"
                    autoComplete="username"
                    spellCheck={false}
                  />
                  <small>
                    Length and availability checks will follow the
                    assigned student seed and FastAPI validation.
                  </small>
                </div>

                <div className="register-field">
                  <label htmlFor="register-password">
                    Password{" "}
                    <span className="register-required">*</span>
                  </label>
                  <div className="register-password-wrap">
                    <input
                      id="register-password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      placeholder="Create a password"
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setShowPassword(!showPassword)
                      }
                      aria-label={
                        showPassword
                          ? "Hide password"
                          : "Show password"
                      }
                    >
                      {showPassword ? (
                        <EyeOff size={18} />
                      ) : (
                        <Eye size={18} />
                      )}
                    </button>
                  </div>
                </div>

                <div className="register-field">
                  <label htmlFor="register-confirm">
                    Re-enter Password{" "}
                    <span className="register-required">*</span>
                  </label>
                  <div className="register-password-wrap">
                    <input
                      id="register-confirm"
                      name="confirmPassword"
                      type={
                        showConfirmPassword ? "text" : "password"
                      }
                      placeholder="Confirm password"
                      autoComplete="new-password"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setShowConfirmPassword(!showConfirmPassword)
                      }
                      aria-label={
                        showConfirmPassword
                          ? "Hide confirmation password"
                          : "Show confirmation password"
                      }
                    >
                      {showConfirmPassword ? (
                        <EyeOff size={18} />
                      ) : (
                        <Eye size={18} />
                      )}
                    </button>
                  </div>
                </div>

                <div className="register-field register-full-width">
                  <div
                    className="register-strength-meter"
                    aria-label="Password strength meter preview"
                  >
                    <span />
                    <span />
                    <span />
                  </div>
                  <small>
                    Password strength: Not assessed yet.
                    The live Weak / Medium / Strong meter will use
                    the finalized password rules.
                  </small>
                </div>

              </div>
            </section>

            {/* SECTION 6: ACCOUNT RECOVERY QUESTIONS */}
            <section
              className="register-section"
              aria-labelledby="register-questions-title"
            >
              <div className="register-section-heading">
                <span className="register-step-number">06</span>
                <div>
                  <h2 id="register-questions-title">
                    Account recovery questions
                  </h2>
                  <p>
                    Three required questions will be assigned
                    using your IT 107 seed.
                  </p>
                </div>
              </div>

              <div className="register-question-list">
                {[1, 2, 3].map((number) => (
                  <div className="register-field" key={number}>
                    <label htmlFor={`register-answer-${number}`}>
                      Question {number}{" "}
                      <span className="register-required">*</span>
                    </label>

                    <p className="register-question-prompt">
                      Seed-assigned question {number} will appear here.
                    </p>

                    <input
                      id={`register-answer-${number}`}
                      name={`securityAnswer${number}`}
                      type="text"
                      placeholder="Answer field available after questions are assigned"
                      disabled
                    />
                  </div>
                ))}
              </div>

              <p className="register-inline-note">
                Answers must be verified and stored as hashes on the
                server, never as readable text.
              </p>
            </section>

            {/* SECTION 7: PRIVACY AND VERIFICATION */}
            <section
              className="register-section"
              aria-labelledby="register-consent-title"
            >
              <div className="register-section-heading">
                <span className="register-step-number">07</span>
                <div>
                  <h2 id="register-consent-title">
                    Privacy and verification
                  </h2>
                  <p>
                    Review the privacy notice before creating a real account.
                  </p>
                </div>
              </div>

              <label className="register-consent">
                <input
                  type="checkbox"
                  checked={privacyAccepted}
                  onChange={(event) =>
                    setPrivacyAccepted(event.target.checked)
                  }
                />
                <span>
                  I have read the Privacy Notice and agree to the collection
                  and processing of my personal data in accordance with the
                  Data Privacy Act of 2012 (RA 10173). <strong>*</strong>
                </span>
              </label>

              <p className="register-inline-note">
                The separate Privacy Notice page is not built yet.
                Checking this box in the preview does not record consent.
              </p>

              <div className="register-verification-note" role="note">
                <LockKeyhole size={21} />
                <div>
                  <strong>CAPTCHA and 6-digit email OTP</strong>
                  <p>
                    Both will be enabled only after their server-side
                    checks are implemented.
                  </p>
                </div>
              </div>

              <button
                className="register-submit-button"
                type="submit"
                disabled
              >
                Create Account <ArrowRight size={18} />
              </button>

              <p className="register-preview-message">
                Frontend preview only. No registration is submitted or saved.
              </p>

              <p className="register-login-prompt">
                Already have an account?{" "}
                <Link to="/login">Log In</Link>
              </p>
            </section>
          </form>

          <div className="register-bottom-hint">
            <CalendarDays size={17} />
            <span>All users must be at least 18 years old.</span>
          </div>
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

export default RegisterPage;
