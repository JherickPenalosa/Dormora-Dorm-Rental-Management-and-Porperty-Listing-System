
/*
  Dormora - File 26
  Reusable navigation bar for the public landing page.

  The system title remains in LandingPage.jsx.
  Theme and mobile-menu state are managed by LandingPage.jsx / App.jsx.
*/

import { Link } from "react-router-dom";
import { House, Menu, Moon, Sun, X } from "lucide-react";

function Navbar({
  darkMode,
  menuOpen,
  onToggleTheme,
  onToggleMenu,
  onCloseMenu,
}) {
  return (
    <header className="site-header">
      <div className="page-container header-content">
        {/* Dormora logo */}
        <a className="brand" href="#home" onClick={onCloseMenu}>
          <House size={29} strokeWidth={2.5} />
          <span>Dormora</span>
        </a>

        {/* Links to sections of the landing page */}
        <nav
          className={menuOpen ? "main-nav menu-open" : "main-nav"}
          aria-label="Main navigation"
        >
          <a href="#home" onClick={onCloseMenu}>Home</a>
          <a href="#featured-rentals" onClick={onCloseMenu}>Discover</a>
          <a href="#features" onClick={onCloseMenu}>Features</a>
          <a href="#how-it-works" onClick={onCloseMenu}>How It Works</a>
          <a href="#about" onClick={onCloseMenu}>About</a>
        </nav>

        {/* Theme toggle and public account page links */}
        <div className="header-actions">
          <button
            className="theme-button"
            type="button"
            onClick={onToggleTheme}
            aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
            title={darkMode ? "Light mode" : "Dark mode"}
          >
            {darkMode ? <Sun size={19} /> : <Moon size={19} />}
          </button>

          <Link
            className="header-login"
            to="/login"
            onClick={onCloseMenu}
          >
            Log In
          </Link>

          {/* Registration page is a UI preview; account creation remains disabled. */}
          <Link
            className="header-register"
            to="/register"
            onClick={onCloseMenu}
            style={{
              color: "#ffffff",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            Register
          </Link>
        </div>

        {/* Collapsible menu on smaller screens */}
        <button
          className="mobile-menu-button"
          type="button"
          onClick={onToggleMenu}
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>
    </header>
  );
}

export default Navbar;
