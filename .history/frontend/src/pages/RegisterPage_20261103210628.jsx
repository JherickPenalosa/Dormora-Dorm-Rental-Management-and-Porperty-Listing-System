                <div className="register-field">
                  <label htmlFor="register-confirm">Re-enter Password <span className="register-required">*</span></label>
                  <div className="register-password-wrap">
                    <input id="register-confirm" name="confirmPassword" type={showConfirmPassword ? "text" : "password"} placeholder="Confirm password" autoComplete="new-password" />
                    <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)} aria-label={showConfirmPassword ? "Hide confirmation password" : "Show confirmation password"}>
                      {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
                <div className="register-field register-full-width">
                  <div className="register-strength-meter" aria-label="Password strength meter preview">
                    <span /> <span /> <span />
                  </div>
                  <small>Password strength: Not assessed yet. The live Weak / Medium / Strong meter will use the finalized password rules.</small>
                </div>
              </div>
            </section>

            {/* 6. Three seed-assigned security questions */}
            <section className="register-section" aria-labelledby="register-questions-title">
              <div className="register-section-heading">
                <span className="register-step-number">06</span>
                <div>
                  <h2 id="register-questions-title">Account recovery questions</h2>
                  <p>Three required questions will be assigned using your IT 107 seed.</p>
                </div>
              </div>
              <div className="register-question-list">
                {[1, 2, 3].map((number) => (
                  <div className="register-field" key={number}>
                    <label htmlFor={`register-answer-${number}`}>
                      Question {number} <span className="register-required">*</span>
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
                Answers must be verified and stored as hashes on the server, never as readable text.
              </p>
            </section>

            {/* 7. Consent and future verification */}
            <section className="register-section" aria-labelledby="register-consent-title">
              <div className="register-section-heading">
                <span className="register-step-number">07</span>
                <div>
                  <h2 id="register-consent-title">Privacy and verification</h2>
                  <p>Review the privacy notice before creating a real account.</p>
                </div>
              </div>

              <label className="register-consent">
                <input
                  type="checkbox"
                  checked={privacyAccepted}
                  onChange={(event) => setPrivacyAccepted(event.target.checked)}
                />
                <span>
                  I have read the Privacy Notice and agree to the collection and
                  processing of my personal data in accordance with the Data
                  Privacy Act of 2012 (RA 10173). <strong>*</strong>
                </span>
              </label>
              <p className="register-inline-note">
                The separate Privacy Notice page is not built yet. Checking this box in
                the preview does not record consent.
              </p>

              <div className="register-verification-note" role="note">
                <LockKeyhole size={21} />
                <div>
                  <strong>CAPTCHA and 6-digit email OTP</strong>
                  <p>Both will be enabled only after their server-side checks are implemented.</p>
                </div>
              </div>

              <button className="register-submit-button" type="submit" disabled>
                Create Account <ArrowRight size={18} />
              </button>
              <p className="register-preview-message">
                Frontend preview only. No registration is submitted or saved.
              </p>
              <p className="register-login-prompt">
                Already have an account? <Link to="/login">Log In</Link>
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
