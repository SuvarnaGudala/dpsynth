# DPSynth – ε-DP Synthetic Data Generator & Privacy Studio

A production-grade, mathematically grounded synthetic data engine built with pure $(\epsilon, \delta)$-Differential Privacy, statistical correlation preservation, India GST billing, and developer REST APIs.

---

## 🚀 Key Features

- **Differential Privacy Engines**:
  - Pure $\epsilon$-Differential Privacy via Laplace mechanisms (Sensitivity 1)
  - $(\epsilon, \delta)$-Differential Privacy via Gaussian mechanisms for enterprise workloads
  - Joint-Histogram Bayesian correlations preservation and marginal fallback
- **Enterprise-Grade Database Layer**:
  - SQLite with WAL journal mode, 64MB cache, and thread-safe locking
  - Relational schema: `users`, `orders`, `subscriptions`, `jobs`, `api_keys`, `audit_logs`
  - High-throughput batched asynchronous disk writer (~1,500 RPS)
  - Automatic column migrations for existing databases
- **Payment & Invoicing System**:
  - Integrated India GST 18% (SAC Code 998313) tax calculation
  - Razorpay order creation and HMAC-SHA256 signature verification
  - 1-Click Instant Sandbox/Test Payment mode for testing without credentials
  - Promo coupons (`WELCOME20`, `STARTUP50`, `PRIVACY10`)
  - Automated printable/downloadable HTML Tax Invoices with B2B GSTIN input credit
  - Automatic API Key generation (`dps_...`) upon successful payment
- **Modern, Accessible UI Studio**:
  - Dark-mode glassmorphic interface with Plus Jakarta Sans & Outfit typography
  - Interactive logarithmic $\epsilon$ privacy slider and real-time risk gauges
  - Pre-loaded domain templates (Healthcare, Finance, E-Commerce, Census)
  - Live Total Variation Distance (TVD) metrics and radial fidelity rings
  - Cryptographic SHA-256 tamper-proof audit certificates
  - Side-by-side comparative preview tables and column-wise distribution overlap charts
- **Deployment Ready**:
  - High-performance pure asyncio HTTP 1.1 keep-alive server
  - Standard ASGI application (`app.server:app`) compatible with Uvicorn and Gunicorn
  - Multi-stage Docker container with unprivileged user and health check probe
  - 1-Command Docker Compose deployment with persistent database volume

---

## 📁 Project Architecture

```
├── run.py                 # Application entry point (multi-worker on Linux/Mac)
├── app/
│   ├── config.py          # Port, host, plan tiers, coupons, and GST company info
│   ├── db.py              # SQLite schema, migrations, connection pool & async writer
│   ├── generator.py       # Laplace & Gaussian DP synthesizer, TVD, and SHA-256 audit
│   ├── handlers.py        # REST API endpoints, plan gating, and static file router
│   ├── payments.py        # Razorpay/Sandbox checkout, signature check & GST invoices
│   └── server.py          # High-throughput asyncio keep-alive server & ASGI app
├── static/
│   ├── index.html         # Accessible Studio UI, checkout dialog & API playground
│   ├── style.css          # Modern dark-first design system & glassmorphism
│   └── app.js             # Client controller, privacy dials, and payment checkout
├── tests/
│   ├── test_generator.py  # Unit tests for differential privacy math & TVD
│   └── test_api.py        # Integration tests for synthesis, gating, and payments
├── scripts/
│   └── loadtest.py        # High-concurrency async HTTP load tester
├── Dockerfile             # Production container definition with health check
├── docker-compose.yml     # Multi-container service orchestrator
├── requirements.txt       # Production dependencies
└── .env.example           # Environment variables template
```

---

## ⚡ Quick Start

### 1. Run Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Start the server (default: http://localhost:8000)
python run.py

# Multi-worker on Linux/macOS
WORKERS=4 python run.py
```

### 2. Run with Docker
```bash
# Build and run with Docker Compose
docker compose up -d

# Check health status
docker compose ps
curl http://localhost:8000/health
```

### 3. Run Unit & Integration Tests
```bash
python -m unittest discover tests
```

### 4. Run Load Testing
```bash
python scripts/loadtest.py 1000 50
```

---

## 🔒 Differential Privacy Guarantee

DPSynth satisfies $\epsilon$-differential privacy:

$$\Pr[\mathcal{M}(D) \in S] \le e^{\epsilon} \cdot \Pr[\mathcal{M}(D') \in S]$$

for any neighboring datasets $D, D'$ differing by at most one individual.
- **Budget Tuning**: $\epsilon \in [0.05, 10.0]$
- **Mechanisms**: Laplace mechanism (sensitivity 1) and Gaussian $(\epsilon, \delta)$-DP
- **Audit Fingerprint**: Every dataset generation yields a deterministic SHA-256 digest encoding the privacy budget, dataset dimensions, noise mechanism, and timestamp.

---

## 💳 Plan Tiers

| Plan Tier | Price (INR) | Max In Rows | Max Out Rows | Min $\epsilon$ | Report & Cert | API Access |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Free Starter** | ₹0 | 1,000 | 2,500 | 0.50 | In-browser TVD | Web UI |
| **Pro Researcher** | ₹499 / mo | 50,000 | 100,000 | 0.05 | Full Utility Report | 100 req/min |
| **Enterprise** | ₹4,999 / mo | 1,000,000+ | 5,000,000 | 0.001 | SHA-256 Audit Cert | 1,000 req/min |

*Annual billing available with a 20% discount. 18% India GST applies with HSN/SAC code 998313.*

---

## 🌐 Production Deployment Guide

### Google Cloud Run / AWS ECS
```bash
gcloud run deploy dpsynth \
  --source . \
  --port 8000 \
  --set-env-vars RAZORPAY_KEY_ID=your_key,RAZORPAY_KEY_SECRET=your_secret
```

### Render / Railway
Deploy directly from repository root. Use start command:
```bash
python run.py
# or:
uvicorn app.server:app --host 0.0.0.0 --port $PORT --workers 2
```
