
/*
  Dormora - File 8
  Reusable navigation bar component.

  The parent page controls the theme and mobile menu.
*/

import { House, Menu, Moon, Sun, X } from "lucide-react";

function Navbar({
  darkMode,
  menuOpen,
  onToggleTheme,
  onToggleMenu,
  onCloseMenu,
}) {
  return (
    <>
      {/* IT 107: System name above the header */}
      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>

      {/* Main navigation bar */}
      <header className="site-header">
        <div className="page-container header-content">

          {/* Dormora Logo */}
          <a className="brand" href="#home" onClick={onCloseMenu}>
            <House size={29} strokeWidth={2.5} />
            <span>Dormora</span>
          </a>

          {/* Desktop and Mobile Navigation Links */}
          <nav
            className={menuOpen ? "main-nav menu-open" : "main-nav"}
            aria-label="Main navigation"
          >
            <a href="#home" onClick={onCloseMenu}>Home</a>

            <a href="#featured-rentals" onClick={onCloseMenu}>
              Discover
            </a>

            <a href="#features" onClick={onCloseMenu}>
              Features
            </a>

            <a href="#how-it-works" onClick={onCloseMenu}>
              How It Works
            </a>

            <a href="#about" onClick={onCloseMenu}>
              About
            </a>
          </nav>

          {/* Header Buttons */}
          <div className="header-actions">

            {/* Light and Dark Mode Toggle */}
            <button
              className="theme-button"
              type="button"
              onClick={onToggleTheme}
              aria-label={
                darkMode
                  ? "Switch to light mode"
                  : "Switch to dark mode"
              }
              title={darkMode ? "Light mode" : "Dark mode"}
            >
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>

            {/* Authentication buttons */}
            {/* These will be enabled when the pages are ready. */}
            <button
              className="header-login"
              type="button"
              disabled
              title="Log-in page is not built yet"
            >
              Log In
            </button>

            <button
              className="header-register"
              type="button"
              disabled
              title="Registration requires proposal approval"
            >
              Register
            </button>

          </div>

          {/* Mobile Navigation Button */}
          <button
            className="mobile-menu-button"
            type="button"
            onClick={onToggleMenu}
            aria-label={
              menuOpen ? "Close navigation" : "Open navigation"
            }
            aria-expanded={menuOpen}
          >
            {menuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>

        </div>
      </header>
    </>
  );
}

export default Navbar;
