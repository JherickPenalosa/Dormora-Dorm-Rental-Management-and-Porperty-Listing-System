
/**
 * DORMORA — SYSTEM FUNCTIONALITY, FILE 4
 * REPLACE: frontend/src/components/home/RoleHome.jsx
 *
 * Shared Home and Property Owner My Properties navigation.
 * Preserves sidebar, responsive layout, and light/dark theme.
 * No changes to authentication or backend services.
 */

import { useState } from "react";
import {
  Bell,
  Building2,
  CalendarDays,
  ChevronRight,
  CreditCard,
  DoorOpen,
  History,
  House,
  LogOut,
  Menu,
  Moon,
  Search,
  Settings,
  Sun,
  Users,
  Wallet,
  X,
} from "lucide-react";

import MyProperties from "../owner/MyProperties";

const PAGES = {
  renter: [
    ["home", "Home", House],
    ["discover", "Discover Dorms", Search],
    ["my-rental", "My Rental", DoorOpen],
    ["rent-payments", "Rent Payments", Wallet],
    ["payment-history", "Payment History", History],
  ],
  property_owner: [
    ["home", "Home", House],
    ["my-properties", "My Properties", Building2],
    ["tenants", "Tenants", Users],
    ["rent-records", "Rent Records", CreditCard],
  ],
};

const HOME = {
  renter: {
    role: "Renter",
    intro: "Find a dorm and keep your rental information organized.",
    stats: [
      ["Current Dorm", "Not assigned", Building2],
      ["Monthly Rent", "—", Wallet],
      ["Next Due Date", "—", CalendarDays],
      ["Payment Status", "No records", CreditCard],
    ],
    panel: "My Rental",
    empty: "Your rental information will appear here when you have a room.",
    actions: [
      ["discover", "Browse Dorms", Search],
      ["payment-history", "Payment History", History],
    ],
  },
  property_owner: {
    role: "Property Owner",
    intro: "Your properties, rooms and rent records in one place.",
    stats: [
      ["Total Listings", "—", Building2],
      ["Available Rooms", "—", DoorOpen],
      ["Occupied Rooms", "—", Users],
      ["Rent Records", "—", CreditCard],
    ],
    panel: "My Properties",
    empty: "Your properties will appear here after listings are connected.",
    actions: [
      ["my-properties", "Manage Properties", Building2],
      ["rent-records", "Rent Records", CreditCard],
    ],
  },
};

const styles = `
.df-home {
  min-height: 100vh;
  display: flex;
  background: var(--background);
  color: var(--text);
  font-family: Inter, "Segoe UI", sans-serif;
}

.df-home * { box-sizing: border-box; }
.df-home button { font: inherit; }

.df-side {
  width: 245px;
  flex: 0 0 245px;
  height: 100vh;
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  background: var(--card);
  border-right: 1px solid var(--border);
  padding: 27px 14px 20px;
  z-index: 5;
}

.df-logo {
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 22px;
  font-weight: 850;
  padding: 0 12px 32px;
}

.df-logo svg { color: var(--primary); }

.df-menu {
  display: grid;
  gap: 5px;
}

.df-nav {
  display: flex;
  align-items: center;
  gap: 13px;
  width: 100%;
  padding: 12px 14px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--muted);
  text-align: left;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
}

.df-nav.active {
  background: var(--soft);
  color: var(--primary);
  font-weight: 800;
}

.df-nav:hover:not(:disabled) {
  background: var(--soft);
}

.df-nav:disabled:not(.active) {
  opacity: .55;
  cursor: not-allowed;
}

.df-side-bottom {
  margin-top: auto;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}

.df-body {
  min-width: 0;
  flex: 1;
}

.df-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 78px;
  padding: 15px 30px;
  background: var(--card);
  border-bottom: 1px solid var(--border);
}

.df-top h2 {
  margin: 0;
  font-size: 17px;
}

.df-top small,
.df-muted {
  color: var(--muted);
  font-size: 12px;
}

.df-tools {
  display: flex;
  align-items: center;
  gap: 12px;
}

.df-icon {
  width: 39px;
  height: 39px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card);
  color: var(--text);
  display: grid;
  place-items: center;
  cursor: pointer;
}

.df-icon:disabled {
  opacity: .45;
  cursor: not-allowed;
}

.df-user {
  display: flex;
  align-items: center;
  gap: 9px;
  border-left: 1px solid var(--border);
  padding-left: 14px;
}

.df-avatar {
  display: grid;
  place-items: center;
  width: 37px;
  height: 37px;
  border-radius: 50%;
  background: var(--soft);
  color: var(--primary);
  font-weight: 850;
}

.df-user strong { font-size: 12px; }

.df-content {
  max-width: 1300px;
  margin: auto;
  padding: 28px 30px 45px;
}

.df-hero {
  border: 1px solid var(--border);
  border-radius: 17px;
  background: linear-gradient(110deg, var(--hero), var(--card));
  padding: 27px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.df-hero h1 {
  font-size: clamp(22px, 3vw, 31px);
  margin: 0 0 9px;
}

.df-hero p {
  color: var(--muted);
  font-size: 13px;
  margin: 0;
  line-height: 1.6;
}

.df-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  border: 1px solid var(--border);
  padding: 12px 15px;
  border-radius: 10px;
  cursor: pointer;
  font-weight: 750;
  font-size: 13px;
  background: var(--card);
  color: var(--text);
}

.df-button.primary {
  background: var(--primary);
  color: var(--background);
  border-color: var(--primary);
}

.df-button:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.df-heading {
  font-size: 17px;
  margin: 28px 0 15px;
}

.df-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.df-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 15px;
  padding: 20px;
  min-width: 0;
}

.df-stat-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.df-stat-top svg { color: var(--primary); }

.df-value {
  font-size: 21px;
  font-weight: 850;
  margin: 15px 0 0;
  overflow-wrap: anywhere;
}

.df-panels {
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 15px;
  margin-top: 15px;
}

.df-card h3 {
  margin: 0;
  font-size: 16px;
}

.df-empty {
  display: grid;
  place-content: center;
  text-align: center;
  min-height: 210px;
  padding: 22px;
  margin-top: 16px;
  background: var(--soft);
  border: 1px dashed var(--border);
  border-radius: 12px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}

.df-actions {
  display: grid;
  gap: 10px;
  margin-top: 21px;
}

.df-actions button {
  justify-content: space-between;
  width: 100%;
}

.df-footnote {
  padding-top: 17px;
  margin-top: 20px;
  border-top: 1px solid var(--border);
  line-height: 1.6;
}

.df-mobile-menu,
.df-overlay { display: none; }

.df-home button:focus-visible {
  outline: 3px solid var(--primary);
  outline-offset: 2px;
}

@media (max-width: 1100px) {
  .df-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 800px) {
  .df-side {
    position: fixed;
    left: 0;
    transform: translateX(-100%);
    transition: transform .2s;
  }

  .df-side.open { transform: translateX(0); }

  .df-overlay.open {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 4;
    border: 0;
    background: #0006;
  }

  .df-mobile-menu { display: grid; }

  .df-panels { grid-template-columns: 1fr; }
}

@media (max-width: 550px) {
  .df-top { padding: 13px 16px; }
  .df-content { padding: 18px 16px; }

  .df-hero {
    align-items: stretch;
    flex-direction: column;
  }

  .df-user .df-user-name { display: none; }
  .df-card { padding: 15px; }
  .df-stats { gap: 9px; }
}
`;

export default function RoleHome({
  account,
  darkMode = false,
  onToggleTheme,
  onNavigate,
  onLogout,
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activePage, setActivePage] = useState("home");

  const info = HOME[account?.role];

  const name =
    typeof account?.username === "string" &&
    account.username.trim()
      ? account.username.trim()
      : "User";

  // Render only for server-verified renter/owner roles.
  if (!info) {
    return (
      <div role="status">
        This Home page is for renters and property owners.
      </div>
    );
  }

  const isProperties =
    account.role === "property_owner" &&
    activePage === "my-properties";

  function canNavigate(page) {
    return (
      page === "home" ||
      (page === "my-properties" &&
        account.role === "property_owner") ||
      typeof onNavigate === "function"
    );
  }

  function go(page) {
    if (
      page === "home" ||
      (page === "my-properties" &&
        account.role === "property_owner")
    ) {
      setActivePage(page);
      setMenuOpen(false);
    } else if (typeof onNavigate === "function") {
      setMenuOpen(false);
      onNavigate(page);
    }
  }

  const selectedPage = isProperties
    ? "my-properties"
    : "home";

  return (
    <div
      className={`dormora ${
        darkMode ? "dark-mode" : ""
      } df-home`}
    >
      <style>{styles}</style>

      <button
        type="button"
        className={`df-overlay ${
          menuOpen ? "open" : ""
        }`}
        aria-label="Close navigation"
        onClick={() => setMenuOpen(false)}
      />

      <aside
        className={`df-side ${
          menuOpen ? "open" : ""
        }`}
        aria-label="Dashboard navigation"
      >
        <div className="df-logo">
          <Building2 size={28} />
          Dormora
        </div>

        <nav
          className="df-menu"
          aria-label={`${info.role} pages`}
        >
          {PAGES[account.role].map(
            ([page, label, Icon]) => (
              <button
                key={page}
                type="button"
                className={`df-nav ${
                  page === selectedPage
                    ? "active"
                    : ""
                }`}
                aria-current={
                  page === selectedPage
                    ? "page"
                    : undefined
                }
                disabled={!canNavigate(page)}
                onClick={() => go(page)}
              >
                <Icon size={18} />
                {label}
              </button>
            )
          )}
        </nav>

        <div className="df-side-bottom">
          <button
            type="button"
            className="df-nav"
            disabled={!onNavigate}
            onClick={() => go("settings")}
          >
            <Settings size={18} />
            Settings
          </button>

          <button
            type="button"
            className="df-nav"
            disabled={!onLogout}
            onClick={onLogout}
          >
            <LogOut size={18} />
            Log Out
          </button>
        </div>
      </aside>

      <div className="df-body">
        <header className="df-top">
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <button
              className="df-icon df-mobile-menu"
              type="button"
              aria-label="Toggle navigation"
              aria-expanded={menuOpen}
              onClick={() =>
                setMenuOpen((open) => !open)
              }
            >
              {menuOpen ? (
                <X size={20} />
              ) : (
                <Menu size={20} />
              )}
            </button>

            <div>
              <h2>
                {isProperties
                  ? "My Properties"
                  : "Home"}
              </h2>
              <small>My Dormora workspace</small>
            </div>
          </div>

          <div className="df-tools">
            <button
              className="df-icon"
              type="button"
              disabled
              aria-label="Notifications coming soon"
            >
              <Bell size={18} />
            </button>

            <button
              className="df-icon"
              type="button"
              disabled={!onToggleTheme}
              aria-label={
                darkMode
                  ? "Light mode"
                  : "Dark mode"
              }
              onClick={onToggleTheme}
            >
              {darkMode ? (
                <Sun size={18} />
              ) : (
                <Moon size={18} />
              )}
            </button>

            <div className="df-user">
              <span
                className="df-avatar"
                aria-hidden="true"
              >
                {name[0].toUpperCase()}
              </span>

              <div className="df-user-name">
                <strong>{name}</strong>
                <div className="df-muted">
                  {info.role}
                </div>
              </div>
            </div>
          </div>
        </header>

        <main className="df-content">
          {isProperties ? (
            <MyProperties
              account={account}
              onBack={() => go("home")}
            />
          ) : (
            <>
              <section className="df-hero">
                <div>
                  <h1>Welcome home, {name}!</h1>
                  <p>{info.intro}</p>
                </div>

                <button
                  className="df-button primary"
                  type="button"
                  disabled={
                    !canNavigate(
                      info.actions[0][0]
                    )
                  }
                  onClick={() =>
                    go(info.actions[0][0])
                  }
                >
                  {info.actions[0][1]}
                  <ChevronRight size={17} />
                </button>
              </section>

              <h2 className="df-heading">
                Overview
              </h2>

              <section
                className="df-stats"
                aria-label="Account overview"
              >
                {info.stats.map(
                  ([label, value, Icon]) => (
                    <div
                      className="df-card"
                      key={label}
                    >
                      <div className="df-stat-top">
                        <span className="df-muted">
                          {label}
                        </span>
                        <Icon size={20} />
                      </div>

                      <p className="df-value">
                        {value}
                      </p>
                    </div>
                  )
                )}
              </section>

              <section
                className="df-panels"
                aria-label="Home panels"
              >
                <div className="df-card">
                  <h3>{info.panel}</h3>

                  <p className="df-muted">
                    Your latest rental information
                  </p>

                  <div className="df-empty">
                    {info.empty}
                  </div>
                </div>

                <div className="df-card">
                  <h3>Quick Actions</h3>

                  <p className="df-muted">
                    Go to your main features
                  </p>

                  <div className="df-actions">
                    {info.actions.map(
                      (
                        [page, label, Icon],
                        index
                      ) => (
                        <button
                          key={page}
                          type="button"
                          className={`df-button ${
                            index === 0
                              ? "primary"
                              : ""
                          }`}
                          disabled={
                            !canNavigate(page)
                          }
                          onClick={() =>
                            go(page)
                          }
                        >
                          <span
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 9,
                            }}
                          >
                            <Icon size={18} />
                            {label}
                          </span>

                          <ChevronRight size={16} />
                        </button>
                      )
                    )}
                  </div>

                  <p className="df-muted df-footnote">
                    This page will display real
                    records as the functionality
                    modules are connected.
                  </p>
                </div>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
