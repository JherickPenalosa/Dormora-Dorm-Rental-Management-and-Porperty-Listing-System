                    <label htmlFor="owner-rent">Expected Monthly Rent (₱) <em>(Optional)</em></label>
                    <input id="owner-rent" name="expectedRent" type="number" min="0" step="100" placeholder="e.g. 4500" />
                  </div>
                  <div className="register-field">
                    <label htmlFor="owner-available">Expected Availability Date <em>(Optional)</em></label>
                    <input id="owner-available" name="expectedAvailableDate" type="date" />
                  </div>
                </div>
              ) : (
                <div className="register-fields-grid" key="renter-fields">
                  <div className="register-field">
                    <label htmlFor="renter-room-type">Preferred Rental Type <em>(Optional)</em></label>
                    <select id="renter-room-type" name="preferredRentalType" defaultValue="">
                      <option value="">Select preference</option>
                      <option value="shared">Shared room</option>
                      <option value="private">Private room</option>
                      <option value="either">Either</option>
                    </select>
                  </div>
                  <div className="register-field">
                    <label htmlFor="renter-area">Preferred Rental Area <em>(Optional)</em></label>
                    <input id="renter-area" name="preferredRentalArea" type="text" placeholder="City or barangay" />
                  </div>
                  <div className="register-field">
                    <label htmlFor="renter-budget">Maximum Monthly Budget (₱) <em>(Optional)</em></label>
                    <input id="renter-budget" name="monthlyBudget" type="number" min="0" step="100" placeholder="e.g. 5000" />
                  </div>
                  <div className="register-field">
                    <label htmlFor="renter-move-in">Target Move-in Date <em>(Optional)</em></label>
                    <input id="renter-move-in" name="targetMoveInDate" type="date" />
                  </div>
                </div>
              )}
            </section>

            {/* 5. Account credentials */}
            <section className="register-section" aria-labelledby="register-account-title">
              <div className="register-section-heading">
                <span className="register-step-number">05</span>
                <div>
                  <h2 id="register-account-title">Account credentials</h2>
                  <p>Your email will receive verification codes and security alerts.</p>
                </div>
              </div>

              <div className="register-fields-grid">
                <div className="register-field register-full-width">
                  <label htmlFor="register-email">Email Address <span className="register-required">*</span></label>
                  <input id="register-email" name="email" type="email" placeholder="you@example.com" autoComplete="email" />
                </div>
                <div className="register-field register-full-width">
                  <label htmlFor="register-username">Username <span className="register-required">*</span></label>
                  <input id="register-username" name="username" type="text" placeholder="Choose a username" autoComplete="username" spellCheck={false} />
                  <small>Length and availability checks will follow the assigned student seed and FastAPI validation.</small>
                </div>
                <div className="register-field">
                  <label htmlFor="register-password">Password <span className="register-required">*</span></label>
                  <div className="register-password-wrap">
                    <input id="register-password" name="password" type={showPassword ? "text" : "password"} placeholder="Create a password" autoComplete="new-password" />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"}>
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
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