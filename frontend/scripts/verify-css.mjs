
/* =========================================================
   DORMORA - FILE 42: CSS MIGRATION VERIFICATION
   Destination: frontend/scripts/verify-css.mjs
   Run from the frontend folder: node scripts/verify-css.mjs

   This checks file structure and references only.
   It does not replace npm run build or visual browser testing.
   ========================================================= */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const src = path.join(frontend, "src");

const stylesheets = [
  "styles/theme.css",
  "styles/shared.css",
  "styles/components/navbar.css",
  "styles/components/footer.css",
  "styles/pages/landing.css",
  "styles/pages/login.css",
  "styles/pages/register.css",
  "styles/pages/forgot-password.css",
];

const requiredSelectors = {
  "styles/theme.css": [".dormora {", ".dormora.dark-mode {"],
  "styles/shared.css": [".page-container {", ".system-title-bar {", ".dormora input::-ms-reveal"],
  "styles/components/navbar.css": [".main-nav {", ".main-nav.menu-open {", ".mobile-menu-button {"],
  "styles/components/footer.css": [".site-footer {", ".footer-content {"],
  "styles/pages/landing.css": [".hero-section {", ".feature-grid {", ".rental-grid {"],
  "styles/pages/login.css": [".login-page {", ".login-card {", ".login-password-toggle {"],
  "styles/pages/register.css": [".register-page {", ".register-role-options {", ".register-fields-grid {"],
  "styles/pages/forgot-password.css": [".forgot-page {", ".forgot-steps {", ".forgot-card {"],
};

let passed = 0;
let failed = 0;

function result(ok, description, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}  ${description}${detail ? ` — ${detail}` : ""}`);
  if (ok) passed += 1;
  else failed += 1;
}

function read(relativePath) {
  const fullPath = path.join(src, relativePath);
  return fs.existsSync(fullPath) ? fs.readFileSync(fullPath, "utf8") : null;
}

// Detect unbalanced CSS braces while ignoring comments and quoted strings.
function hasBalancedBraces(css) {
  let depth = 0;
  let state = "normal";

  for (let i = 0; i < css.length; i += 1) {
    const char = css[i];
    const next = css[i + 1];

    if (state === "comment") {
      if (char === "*" && next === "/") {
        state = "normal";
        i += 1;
      }
      continue;
    }

    if (state === "single" || state === "double") {
      if (char === "\\") {
        i += 1;
      } else if ((state === "single" && char === "'") ||
                 (state === "double" && char === '"')) {
        state = "normal";
      }
      continue;
    }

    if (char === "/" && next === "*") {
      state = "comment";
      i += 1;
    } else if (char === "'") {
      state = "single";
    } else if (char === '"') {
      state = "double";
    } else if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth < 0) return false;
    }
  }

  return depth === 0 && state === "normal";
}

console.log("\nDormora CSS Migration Verification — File 42\n");

const appCss = read("App.css");
result(appCss !== null, "CSS entry point exists", "src/App.css");

if (appCss !== null) {
  const imports = [...appCss.matchAll(/@import\s+["']([^"']+)["']\s*;/g)]
    .map((match) => match[1]);
  const expected = stylesheets.map((file) => `./${file}`);
  result(
    JSON.stringify(imports) === JSON.stringify(expected),
    "App.css imports all eight stylesheets in the expected order"
  );
}

for (const stylesheet of stylesheets) {
  const css = read(stylesheet);
  result(css !== null, `Stylesheet exists: ${stylesheet}`);
  if (css === null) continue;

  result(hasBalancedBraces(css), `Balanced CSS braces: ${stylesheet}`);

  const missing = requiredSelectors[stylesheet].filter((selector) => !css.includes(selector));
  result(
    missing.length === 0,
    `Important selectors present: ${stylesheet}`,
    missing.length ? `Missing: ${missing.join(", ")}` : ""
  );
}

// Canva images are resolved relative to landing.css, not App.css.
const landingPath = path.join(src, "styles", "pages", "landing.css");
const landingCss = read("styles/pages/landing.css");
const canvaImages = [
  "../../assets/dormora-hero-background-light.jpg",
  "../../assets/dormora-hero-background-dark.jpg",
];

for (const image of canvaImages) {
  const referenced = landingCss !== null && landingCss.includes(`url("${image}")`);
  const imagePath = path.resolve(path.dirname(landingPath), image);
  result(referenced, `Canva image URL is correct: ${path.basename(image)}`);
  result(fs.existsSync(imagePath), `Canva image file exists: ${path.basename(image)}`);
}

// All four page components use the App.css entry point.
for (const page of ["LandingPage", "LoginPage", "RegisterPage", "ForgotPasswordPage"]) {
  const jsx = read(`pages/${page}.jsx`);
  result(
    jsx !== null && /import\s+["']\.\.\/App\.css["']\s*;/.test(jsx),
    `${page}.jsx imports the CSS entry point`
  );
}

console.log(`\nResults: ${passed} passed, ${failed} failed.\n`);
if (failed > 0) {
  console.log("Fix the failed checks, then run: node scripts/verify-css.mjs\n");
  process.exitCode = 1;
} else {
  console.log("Static checks passed. Next run npm run build and inspect all four pages in the browser.\n");
}
