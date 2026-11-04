
import { useState } from "react";
import {
  ArrowRight,
  BedDouble,
  Building2,
  CalendarDays,
  Calculator,
  CheckCircle2,
  Coins,
  House,
  MapPin,
  Menu,
  Moon,
  Search,
  Sun,
  Wallet,
  X,
} from "lucide-react";

import dashboardImage from "../assets/dormora-hero-laptop.png";
import "../App.css";

// Temporary sample listings.
// Real listings will be loaded from FastAPI later.
const sampleRentals = [
  {
    id: 1,
    name: "Riverside Dormitory",
    location: "Near the university",
    price: 4500,
    type: "Shared room",
    imageStyle: "rental-image-one",
  },
  {
    id: 2,
    name: "Maple Residences",
    location: "City center",
    price: 5000,
    type: "Private room",
    imageStyle: "rental-image-two",
  },
  {
    id: 3,
    name: "Central Stay Dorm",
    location: "Near public transport",
    price: 4800,
    type: "Dormitory",
    imageStyle: "rental-image-three",
  },
];

function LandingPage() {
  // These states currently belong to the landing page.
  // We can share the theme across pages later.
  const [darkMode, setDarkMode] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  function closeMenu() {
    setMenuOpen(false);
  }

  return (
    <div className={darkMode ? "dormora dark-mode" : "dormora light-mode"}>

      {/* System title above header - IT 107 requirement */}
      <div className="system-title-bar">
        Dormora: A Secure Web-Based Rental Management and Property Listing System
      </div>

      {/* SECTION 1: NAVIGATION */}
      <header className="site-header">
        <div className="page-container header-content">

          <a className="brand" href="#home" onClick={closeMenu}>
            <House size={29} strokeWidth={2.5} />
            <span>Dormora</span>
          </a>

          <nav
            className={menuOpen ? "main-nav menu-open" : "main-nav"}
            aria-label="Main navigation"
          >
            <a href="#home" onClick={closeMenu}>Home</a>
            <a href="#featured-rentals" onClick={closeMenu}>Discover</a>
            <a href="#features" onClick={closeMenu}>Features</a>
            <a href="#how-it-works" onClick={closeMenu}>How It Works</a>
            <a href="#about" onClick={closeMenu}>About</a>
          </nav>

          <div className="header-actions">
            <button
              className="theme-button"
              type="button"
              onClick={() => setDarkMode(!darkMode)}
              aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
              title={darkMode ? "Light mode" : "Dark mode"}
            >
              {darkMode ? <Sun size={19} /> : <Moon size={19} />}
            </button>

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

          <button
            className="mobile-menu-button"
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={menuOpen}
          >
            {menuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>

        </div>
      </header>

      <main>

        {/* SECTION 2: HERO */}
        <section className="hero-section" id="home">
          <div className="page-container hero-layout">

            <div className="hero-text">
              <span className="eyebrow">
                For renters and property owners aged 18+
              </span>

              <h1>
                Find your space.
                <span> Track your rent.</span>
              </h1>

              <p>
                Discover places to rent, manage your monthly payments, and
                keep your rental records organized in one convenient place.
              </p>

              <div className="hero-buttons">
                <a className="button button-primary" href="#featured-rentals">
                  <Search size={19} />
                  Explore Rentals
                </a>

                <a className="button button-outline" href="#features">
                  See Our Features
                  <ArrowRight size={18} />
                </a>
              </div>

              <div className="hero-highlights">
                <span>
                  <CheckCircle2 size={17} />
                  Personal rent tracking
                </span>
                <span>
                  <CheckCircle2 size={17} />
                  Owner-managed listings
                </span>
              </div>
            </div>

            {/* Temporary laptop image */}
            <div className="hero-preview">
              <img
                src={dashboardImage}
                className="hero-laptop-image"
                alt="Dormora rent dashboard displayed on a laptop"
              />
            </div>

          </div>
        </section>

        {/* SECTION 3: FEATURES */}
        <section className="features-section page-container" id="features">
          <div className="feature-grid">

            <article className="feature-card">
              <div className="feature-icon">
                <House size={25} />
              </div>
              <div>
                <h3>Dorm Discovery</h3>
                <p>
                  Browse available places with owner-submitted photos and details.
                </p>
              </div>
            </article>

            <article className="feature-card">
              <div className="feature-icon">
                <CalendarDays size={25} />
              </div>
              <div>
                <h3>Rent Tracker</h3>
                <p>
                  Track due dates, recorded payments, and remaining balances.
                </p>
              </div>
            </article>

            <article className="feature-card">
              <div className="feature-icon">
                <Coins size={25} />
              </div>
              <div>
                <h3>Deposit Tracker</h3>
                <p>
                  Keep a private record of your deposit and its return status.
                </p>
              </div>
            </article>

            <article className="feature-card">
              <div className="feature-icon">
                <Calculator size={25} />
              </div>
              <div>
                <h3>Move-in Estimator</h3>
                <p>
                  Estimate advance rent, deposits, and initial moving costs.
                </p>
              </div>
            </article>

          </div>
        </section>

        {/* SECTION 4: FEATURED RENTALS */}
        <section
          className="rentals-section page-container"
          id="featured-rentals"
        >
          <div className="section-heading">
            <div>
              <h2>Featured Rentals</h2>
              <p>
                Examples of how available properties will appear in Dormora.
              </p>
            </div>

            <span className="preview-note">
              Sample listings only
            </span>
          </div>

          <div className="rental-grid">
            {sampleRentals.map((rental) => (
              <article className="rental-card" key={rental.id}>

                <div className={`rental-image ${rental.imageStyle}`}>
                  <BedDouble size={43} strokeWidth={1.4} />
                  <span>Photo preview</span>
                </div>

                <div className="rental-details">
                  <span className="rental-type">
                    {rental.type}
                  </span>

                  <h3>{rental.name}</h3>

                  <p>
                    <MapPin size={15} />
                    {rental.location}
                  </p>

                  <strong>
                    ₱{rental.price.toLocaleString("en-PH")}
                    <small> / month</small>
                  </strong>
                </div>

              </article>
            ))}
          </div>
        </section>

        {/* SECTION 5: HOW DORMORA WORKS */}
        <section
          className="how-section page-container"
          id="how-it-works"
        >
          <div className="section-heading">
            <div>
              <h2>How Dormora Works</h2>
              <p>Simple tools for the two types of users.</p>
            </div>
          </div>

          <div className="role-grid">

            <article className="role-card renter-role">
              <div className="role-icon">
                <Wallet size={30} />
              </div>

              <div>
                <h3>For Renters</h3>
                <p>
                  Find available rentals, plan move-in costs, and track
                  your rent and deposit privately.
                </p>
              </div>
            </article>

            <article className="role-card owner-role">
              <div className="role-icon">
                <Building2 size={30} />
              </div>

              <div>
                <h3>For Property Owners</h3>
                <p>
                  Publish rental listings with photos, update prices,
                  and manage availability.
                </p>
              </div>
            </article>

          </div>
        </section>

        {/* SECTION 6: ABOUT BANNER */}
        <section className="about-section page-container" id="about">
          <div className="about-banner">

            <div>
              <h2>Find your next place. Stay organized.</h2>
              <p>
                Designed to make rental discovery and personal rent tracking simpler.
              </p>
            </div>

            <a className="button button-white" href="#home">
              Back to Top
              <ArrowRight size={18} />
            </a>

          </div>
        </section>

      </main>

      {/* SECTION 7: FOOTER */}
      <footer className="site-footer">
        <div className="page-container footer-content">

          <div className="footer-brand">
            <House size={21} />
            <strong>Dormora</strong>
          </div>

          <p>© 2026 Dormora. All rights reserved.</p>

          <div className="footer-links">
            <a href="#home">Home</a>
            <a href="#features">Features</a>
            <a href="#about">About</a>
          </div>

        </div>
      </footer>

    </div>
  );
}

export default LandingPage;
