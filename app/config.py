import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "0.0.0.0")
WORKERS = int(os.environ.get("WORKERS", 1))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE, "data", "dpsynth.db"))
STATIC = os.path.join(BASE, "static")

# Billing and Tax Configuration (India GST & Global)
CURRENCY = "INR"
GST = 0.18  # 18% GST (SAC code 998313: IT and Data Software Services)
GST_RATE = GST

COMPANY_INFO = {
    "name": "DPSynth Privacy Technologies Ltd.",
    "brand": "DPSynth",
    "gstin": os.environ.get("COMPANY_GSTIN", "36AABCD9876E1Z2"),
    "pan": "AABCD9876E",
    "sac_code": "998313",
    "address": "Level 4, Cyber Gateway, HITEC City, Hyderabad, TG 500081, India",
    "support_email": "support@dpsynth.io",
    "website": "https://dpsynth.io"
}

# Payment Gateways (Razorpay & Stripe & Sandbox)
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_DPSynthSandboxKey")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
APP_SECRET = os.environ.get("APP_SECRET", "dpsynth_secret_hmac_salt_2026")

# Promo Coupons
COUPONS = {
    "WELCOME20": {"discount_pct": 20, "description": "20% off for first-time adopters"},
    "STARTUP50": {"discount_pct": 50, "description": "50% off for eligible early startups"},
    "PRIVACY10": {"discount_pct": 10, "description": "10% off on all pro & enterprise plans"}
}

# Plan Tiers
PLANS = {
    "free": {
        "id": "free",
        "name": "Free Starter",
        "price": 0,
        "annual_price": 0,
        "max_in": 1000,
        "max_out": 2500,
        "min_eps": 0.5,
        "report": False,
        "cert": False,
        "api_access": False,
        "badge": "Community",
        "mechanisms": ["Laplace (Marginals)"],
        "features": [
            "Up to 1,000 input rows",
            "2,500 synthetic output rows",
            "Privacy budget ε down to 0.5",
            "Standard CSV preview & export",
            "In-browser total variation distance metric"
        ]
    },
    "pro": {
        "id": "pro",
        "name": "Pro Researcher",
        "price": 499,
        "annual_price": 4790,  # ~20% discount
        "max_in": 50000,
        "max_out": 100000,
        "min_eps": 0.05,
        "report": True,
        "cert": False,
        "api_access": True,
        "badge": "Most Popular",
        "mechanisms": ["Laplace (Joint-Histogram + Marginals)"],
        "features": [
            "Up to 50,000 input rows",
            "100,000 synthetic rows output",
            "High-precision ε down to 0.05",
            "Full Utility & Privacy Loss Report",
            "Per-column TVD & Correlation Heatmap",
            "REST API Access & Personal API Key",
            "Instant unmetered CSV & JSON downloads"
        ]
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise Compliance",
        "price": 4999,
        "annual_price": 47990,  # ~20% discount
        "max_in": 1000000,
        "max_out": 5000000,
        "min_eps": 0.001,
        "report": True,
        "cert": True,
        "api_access": True,
        "badge": "Audit Ready",
        "mechanisms": ["Laplace & Gaussian (ε, δ)-DP", "Joint-Bayesian Distribution"],
        "features": [
            "Up to 1,000,000+ input rows",
            "5,000,000 synthetic rows output",
            "Ultra-pure ε down to 0.001",
            "Gaussian & Laplace (ε, δ)-DP mechanisms",
            "Cryptographic Audit Certificate (SHA-256)",
            "Unlimited Multi-key REST API Access",
            "B2B Tax Invoice with GSTIN input tax credit",
            "Dedicated Priority Support & SLAs"
        ]
    }
}
