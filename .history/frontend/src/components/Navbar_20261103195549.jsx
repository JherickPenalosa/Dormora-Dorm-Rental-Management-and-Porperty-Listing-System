
/*
  Dormora - File 18
  Reusable public navigation bar.

  The system title stays in LandingPage.jsx.
  The parent page controls the theme and mobile navigation state.
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
        {/* Dormora brand */}
        <a className="brand" href="#home" onClick={onCloseMenu}>
          <House size={29} strokeWidth={2.5} />
          <span>Dormora</span>
        </a>

        {/* Navigation within the landing page */}
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

        {/* Theme, login, and future registration */}
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

          {/* File 18: The login page now has a working route. */}
          <Link className="header-login" to="/login" onClick={onCloseMenu}>
            Log In
          </Link>

          {/* Registration stays disabled until its page is approved and built. */}
          <button
            className="header-register"
            type="button"
            disabled
            title="Registration requires proposal approval"
          >
            Register
          </button>
        </div>

        {/* Mobile menu toggle */}
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
