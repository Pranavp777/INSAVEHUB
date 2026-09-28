# InSave Hub — Instagram Content Utility & Social Media Control Center

## Project Overview

InSave Hub is a production-ready Instagram Social Media Management and Content Utility platform built with Python, Django, and a custom **Glass Orbit** Glassmorphism UI/UX architecture. The interface is designed as a precision digital control center featuring multi-layer translucent surfaces, subtle specular refraction borders, deep obsidian charcoal backgrounds, ambient lighting particles, and server-anchored state management.

The application is engineered for both traditional WSGI/PostgreSQL environments and **Cloudflare Python Workers** edge deployment with Cloudflare D1, Cloudflare R2, and Cloudflare Workers Assets integration.

---

## Features

- **Glass Orbit Interface**: Original Glassmorphism design language with layered blur, thin illuminated borders, interactive orbital tool console, scroll-reveal transitions, and `prefers-reduced-motion` accessibility compliance.
- **Public Instagram Utility Modules**:
  - Instagram Reel Downloader (`reel-downloader`)
  - Instagram Video Downloader (`video-downloader`)
  - Instagram Image Downloader (`image-downloader`)
  - Public Post Downloader (`public-post-downloader`)
  - Profile Media Utility (`profile-media-utility`)
  - Content Information Extractor (`content-info-extractor`)
- **Asynchronous Download Console**: Fetch API-powered URL inspection with live format, resolution, shortcode, and file size telemetry without page reloads.
- **Server-Validated Download & 24-Hour Free Access System**:
  - Initial download executes immediately.
  - Subsequent download activates a mandatory 30-second advertisement/interstitial screen (`"Your next download will be available after the advertisement."`).
  - Countdown timestamps (`started_at`, `eligible_at`) are stored and verified server-side so refreshing the browser or modifying client-side scripts cannot bypass the timer.
  - Completing the 30-second countdown unlocks the pending download and activates a **24-hour Free Access Session** (`FreeAccessSession`) with a live server-synchronized countdown (`Free access expires in HH:MM:SS`).
  - When the 24-hour window expires, the account or session automatically returns to the normal access cycle.
- **Authentication & Google OAuth 2.0**:
  - Full account registration, login, logout, password reset, email verification, and account confirmation flows.
  - Google OAuth 2.0 authorization code flow with cryptographic CSRF `state` verification, session expiration checks, duplicate-email resolution, and zero external password storage.
- **Optional Donation System (Razorpay Ready)**:
  - Admin-configurable preset donation tiers, custom amounts, anonymous supporter option, and donation ledger.
  - Razorpay Orders API integration and cryptographic HMAC-SHA256 payment signature verification (`RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`).
- **Custom Admin Analytics & Django Admin**:
  - Dedicated staff telemetry dashboard (`/dashboard/admin-analytics/`) tracking total/active users, total/successful/failed downloads, ad completions, active 24-hour sessions, donation totals, popular tools, and live configuration controls.
- **Defense-in-Depth Security**:
  - Configurable rate limiting on URL analysis, downloads, authentication, password resets, OAuth callbacks, and donation orders.
  - Privacy-preserving salted SHA-256 IP hashing (`AuditLog`, `DownloadAttempt`, `AdSession`, `FreeAccessSession`).
  - Strict Content-Security-Policy, CSRF protection, HttpOnly/SameSite cookies, and custom glass error screens (`400`, `403`, `404`, `429`, `500`).

---

## Technology Stack

- **Backend**: Python 3.10+, Django 5.1, Django REST Framework, WhiteNoise, `dj-database-url`, `django-storages` (S3/R2), `requests`, `httpx`
- **Frontend**: Semantic HTML5, Modular CSS3 (`tokens.css`, `glass-orbit.css`, `components.css`, `responsive.css`), Vanilla JavaScript (Fetch API, `IntersectionObserver`, Canvas 2D API)
- **Database Compatibility**: PostgreSQL, Cloudflare D1, SQLite3
- **Edge Runtime**: Cloudflare Python Workers (`src/entry.py` WSGI integration, `wrangler.jsonc`, `pyproject.toml`)

---

## Requirements

- Python `3.10` or newer
- `pip` or `uv` Python package manager
- Node.js `18+` and `npx wrangler` (for Cloudflare Workers local development and edge deployment)

---

## Local Installation

```powershell
# 1. Clone or navigate to the project workspace
cd "d:\INSAVE HUB"

# 2. (Optional) Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install project dependencies
python -m pip install -e .

# 4. Copy the environment variable template
Copy-Item .env.example .env
```

*(Note: If you are setting up a brand-new Django project from scratch in an empty folder, the standard command is `django-admin startproject config .`, which has already been structured and configured in this repository.)*

---

## Environment Variables

Configure `.env` for local development (never commit `.env` to version control):

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `DJANGO_ENV` | Runtime environment (`development` or `production`) | `development` |
| `DJANGO_DEBUG` | Enable debug mode in development only | `True` |
| `DJANGO_SECRET_KEY` | Cryptographic signing key (required in production) | 50+ random characters |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hostnames | `localhost,127.0.0.1,.workers.dev` |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins with scheme | `http://localhost:8000` |
| `CANONICAL_BASE_URL` | Base URL for SEO canonical links and OAuth redirects | `http://localhost:8000` |
| `DATABASE_URL` | PostgreSQL connection URL (falls back to SQLite if blank) | `postgres://user:pass@host:5432/dbname` |
| `USE_CLOUDFLARE_D1` | Enable Cloudflare D1 binding bridge | `False` |
| `USE_CLOUDFLARE_R2` | Enable Cloudflare R2 object storage for media | `False` |
| `GOOGLE_OAUTH_CLIENT_ID` | Google Cloud OAuth 2.0 Client ID | From Google Cloud Console |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google Cloud OAuth 2.0 Client Secret | From Google Cloud Console |
| `GOOGLE_OAUTH_REDIRECT_URI` | Authorized redirect URI for Google OAuth | `http://localhost:8000/auth/google/callback/` |
| `RAZORPAY_KEY_ID` | Razorpay API Key ID for donations | `rzp_test_...` or `rzp_live_...` |
| `RAZORPAY_KEY_SECRET` | Razorpay API Key Secret for HMAC verification | Secret string |
| `AD_COUNTDOWN_SECONDS` | Server-enforced advertisement countdown duration | `30` |
| `FREE_ACCESS_HOURS` | Duration of free-access window after ad completion | `24` |

---

## Google OAuth Configuration

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create or select a project.
2. Navigate to **APIs & Services > Credentials** and create an **OAuth 2.0 Client ID** (Web application).
3. Add your authorized redirect URIs:
   - Local development: `http://localhost:8000/auth/google/callback/`
   - Production: `https://your-domain.example.com/auth/google/callback/`
4. Set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, and `GOOGLE_OAUTH_REDIRECT_URI` in your `.env` file (or via `npx wrangler secret put` for Cloudflare).

---

## Database Configuration

### Local Development (SQLite)
Leave `DATABASE_URL` empty in `.env` to use `db.sqlite3` automatically.

### Production PostgreSQL (Cloudflare Hyperdrive / Managed Postgres)
Set `DATABASE_URL=postgres://user:password@host:5432/insave_hub` in `.env` or Worker secrets.

### Cloudflare D1 Configuration
1. Create a Cloudflare D1 database:
   ```powershell
   npx wrangler d1 create insave-hub-db
   ```
2. Copy the returned `database_id` into `wrangler.jsonc` under `d1_databases[0].database_id`.
3. Export the Django schema and seed data to a D1-compatible SQL file and apply it:
   ```powershell
   python manage.py export_d1_schema --output d1_schema.sql
   npx wrangler d1 execute insave-hub-db --local --file=d1_schema.sql
   npx wrangler d1 execute insave-hub-db --remote --file=d1_schema.sql
   ```

---

## Donation / Payment Configuration (Razorpay)

1. Log in to the Razorpay Dashboard and generate API Keys (**Settings > API Keys**).
2. Add `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` to your `.env` or Cloudflare Worker secrets.
3. Preset donation amounts, currency (`INR`), and minimum/maximum bounds can be modified at any time via the Django Admin under **Core & Platform Configuration > Site Configuration**.

---

## Cloudflare R2 Configuration (Optional)

If you wish to store media files on Cloudflare R2:
1. Create an R2 bucket:
   ```powershell
   npx wrangler r2 bucket create insave-hub-media
   ```
2. Set `USE_CLOUDFLARE_R2=True`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, and `R2_ENDPOINT_URL` in your environment.

---

## Local Development Commands

```powershell
# 1. Create and apply database migrations
python manage.py makemigrations
python manage.py migrate

# 2. Seed default SiteConfiguration and the 6 Instagram utility tools
python manage.py seed_platform

# 3. Create an administrative superuser
python manage.py createsuperuser

# 4. Collect static assets into ./staticfiles
python manage.py collectstatic --noinput

# 5. Start the local Django development server
python manage.py runserver 0.0.0.0:8000
```

---

## Testing Commands

Run the full automated test suite (covering registration, login, Google OAuth 2.0, password reset, URL validation, download authorization, 30-second ad countdown, 24-hour free access pass, expired access, rate limiting, donations, and admin permissions):

```powershell
python manage.py test -v 2
```

---

## Cloudflare Development & Deployment Commands

### Running Cloudflare Development Mode
```powershell
# Ensure static assets and D1 schema are up to date
python manage.py collectstatic --noinput
python manage.py export_d1_schema --output d1_schema.sql
npx wrangler d1 execute insave-hub-db --local --file=d1_schema.sql

# Launch Cloudflare Workers local runtime
npx wrangler dev
```

### Deploying to Cloudflare
```powershell
# 1. Configure production secrets in Cloudflare (never hard-code in wrangler.jsonc)
npx wrangler secret put DJANGO_SECRET_KEY
npx wrangler secret put GOOGLE_OAUTH_CLIENT_ID
npx wrangler secret put GOOGLE_OAUTH_CLIENT_SECRET
npx wrangler secret put RAZORPAY_KEY_ID
npx wrangler secret put RAZORPAY_KEY_SECRET

# 2. Build static assets and apply remote D1 schema if needed
python manage.py collectstatic --noinput
python manage.py export_d1_schema --output d1_schema.sql
npx wrangler d1 execute insave-hub-db --remote --file=d1_schema.sql

# 3. Deploy the Python Worker to Cloudflare Edge
npx wrangler deploy
```

### Updating an Existing Cloudflare Deployment
```powershell
# 1. Apply any new migrations locally and export updated schema if models changed
python manage.py migrate
python manage.py collectstatic --noinput

# 2. Deploy the updated code and static assets
npx wrangler deploy
```

---

## Production Security Checklist

- [ ] `DJANGO_ENV=production` and `DJANGO_DEBUG=False` are set.
- [ ] `DJANGO_SECRET_KEY` is stored as an encrypted Cloudflare Secret (`npx wrangler secret put DJANGO_SECRET_KEY`).
- [ ] `DJANGO_ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` are restricted to your production domains.
- [ ] Google OAuth and Razorpay secrets are configured strictly via environment variables / Worker secrets.
- [ ] HTTPS redirect (`SECURE_SSL_REDIRECT`), HSTS, `SESSION_COOKIE_SECURE`, and `CSRF_COOKIE_SECURE` are active (automatically enabled when `DJANGO_ENV=production`).

---

## Troubleshooting

- **CSRF Verification Failed**: Verify that `CSRF_TRUSTED_ORIGINS` includes your full scheme and hostname (e.g., `https://insave-hub.your-subdomain.workers.dev`).
- **Google OAuth Redirect URI Mismatch**: Ensure `GOOGLE_OAUTH_REDIRECT_URI` matches the exact URI registered in Google Cloud Console, including the trailing slash (`/auth/google/callback/`).
- **Static Files Missing in Worker Dev**: Run `python manage.py collectstatic --noinput` before starting `npx wrangler dev` so the `./staticfiles` directory bound in `wrangler.jsonc` is populated.
- **Rate Limit Triggered During Testing**: Rate limits can be adjusted dynamically in Django Admin (**Site Configuration**) or via `.env` variables (`RATE_LIMIT_ANALYZE_PER_MIN`, etc.).
