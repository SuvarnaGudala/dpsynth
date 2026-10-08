"""DPSynth HTTP Request Handlers & API Endpoints.
Routes:
- Dataset synthesis with Differential Privacy gating & cryptographic audit
- Payment quotes, order creation, signature verification, and tax invoicing
- User subscription lookups and API key authentication
- Static file serving and health check probes
"""
import json
import csv
import io
import time
import os
import mimetypes
from .config import (
    PLANS, GST, STATIC, COUPONS, COMPANY_INFO, RAZORPAY_KEY_ID
)
from .db import (
    enqueue, history, save_job_record, get_job_by_id,
    get_user_by_email, get_user_by_api_key, get_system_stats
)
from .generator import generate_detailed
from .payments import (
    calculate_quote, create_checkout_order,
    verify_and_activate_payment, generate_tax_invoice_html
)

J = "application/json"

def _j(code, obj):
    return code, json.dumps(obj).encode("utf-8"), J

def static_handler(path):
    """Serves static frontend assets safely from the STATIC directory."""
    clean_path = path.lstrip("/")
    if clean_path.startswith("static/"):
        clean_path = clean_path[len("static/"):]
    if not clean_path or clean_path == "/":
        clean_path = "index.html"
    
    p = os.path.normpath(os.path.join(STATIC, clean_path))
    if not p.startswith(STATIC) or not os.path.isfile(p):
        return _j(404, {"error": "Asset not found"})
    
    content_type, _ = mimetypes.guess_type(p)
    content_type = content_type or "text/plain"
    if "html" in content_type or "javascript" in content_type or "css" in content_type:
        content_type += "; charset=utf-8"
        
    return 200, open(p, "rb").read(), content_type

def handle_subscribe_legacy(d):
    """Backward-compatible subscription endpoint with instant plan provisioning."""
    plan_name = d.get("plan", "pro")
    email = d.get("email")
    if not email or plan_name not in PLANS:
        return _j(400, {"error": "Please provide a valid email and select a plan"})
    
    p = PLANS[plan_name]
    gst = round(p["price"] * GST, 2)
    total = p["price"] + gst
    
    # Create and immediately complete order in database
    order = create_checkout_order(
        email=email,
        plan_id=plan_name,
        billing_cycle="monthly",
        customer_info={"gateway": "sandbox", "name": d.get("name", "")}
    )
    
    success, msg, data = verify_and_activate_payment(
        order_id=order["order_id"],
        payment_id=f"pay_instant_{int(time.time())}",
        gateway="sandbox"
    )
    
    return _j(200, {
        "status": "active",
        "plan": plan_name,
        "email": email,
        "total_inr": total,
        "gst_inr": gst,
        "api_key": data.get("api_key") if data else None,
        "invoice_number": order["invoice_number"],
        "message": "Subscription activated successfully"
    })

def handle_create_order(d):
    """Creates a new payment order for Razorpay or Sandbox checkout."""
    email = d.get("email")
    plan = d.get("plan")
    billing_cycle = d.get("billing_cycle", "monthly")
    promo_code = d.get("promo_code")

    if not email or not plan:
        return _j(400, {"error": "Email and plan are required"})
    if plan not in PLANS or plan == "free":
        return _j(400, {"error": "Select a valid paid tier (pro or enterprise)"})

    try:
        order = create_checkout_order(
            email=email,
            plan_id=plan,
            billing_cycle=billing_cycle,
            promo_code=promo_code,
            customer_info={
                "name": d.get("customer_name", ""),
                "company": d.get("customer_company", ""),
                "gstin": d.get("customer_gstin", ""),
                "gateway": d.get("gateway", "razorpay")
            }
        )
        return _j(200, order)
    except Exception as e:
        return _j(400, {"error": str(e)})

def handle_verify_payment(d):
    """Verifies payment signature and activates plan."""
    order_id = d.get("order_id")
    payment_id = d.get("payment_id")
    signature = d.get("signature")
    gateway = d.get("gateway", "razorpay")

    if not order_id:
        return _j(400, {"error": "order_id is required"})

    success, msg, data = verify_and_activate_payment(
        order_id=order_id,
        payment_id=payment_id,
        signature=signature,
        gateway=gateway
    )

    if not success:
        return _j(400, {"error": msg})

    return _j(200, {
        "ok": True,
        "message": msg,
        "plan": data.get("plan"),
        "api_key": data.get("api_key"),
        "invoice_number": data.get("invoice_number"),
        "invoice_url": f"/api/payments/invoice/{data.get('invoice_number')}"
    })

def handle_validate_coupon(d):
    """Validates coupon code and returns discount amount."""
    code = (d.get("code") or "").strip().upper()
    if code in COUPONS:
        return _j(200, {"valid": True, "code": code, **COUPONS[code]})
    return _j(200, {"valid": False, "error": "Invalid or expired coupon code"})

def handle_generate(d, auth_header=None):
    """
    Main differential privacy data synthesis route.
    Validates CSV, checks plan budget & epsilon constraints,
    executes mathematical synthesizer, and records job metadata.
    """
    # 1. Resolve User Plan
    api_key = d.get("api_key") or (auth_header.removeprefix("Bearer ").strip() if auth_header else None)
    email = d.get("email")
    user = None
    
    if api_key:
        user = get_user_by_api_key(api_key)
    elif email:
        user = get_user_by_email(email)
        
    user_plan = user.get("plan") if user else d.get("plan", "free")
    # Verify expiration if user has a paid plan
    if user and user.get("plan_expires_at") and user["plan_expires_at"] < time.time():
        user_plan = "free"
        
    p = PLANS.get(user_plan, PLANS["free"])

    # 2. Parse & Validate CSV
    raw_csv = d.get("csv", "").strip()
    if not raw_csv:
        return _j(400, {"error": "CSV content is required."})

    try:
        eps = float(d.get("epsilon", 1.0))
        n_out = int(d.get("n_out", 100))
        delta = float(d.get("delta", 1e-5))
        mechanism = d.get("mechanism", "laplace").lower()
        dataset_name = d.get("dataset_name", "dataset.csv")

        reader = list(csv.reader(io.StringIO(raw_csv)))
        if not reader:
            return _j(400, {"error": "Empty CSV file."})
        header = [c.strip() for c in reader[0]]
        rows = [r for r in reader[1:] if len(r) == len(header) and any(c.strip() for c in r)]

        if not header or not rows:
            return _j(400, {"error": "CSV must have a header row and at least 1 valid data row."})
        if eps <= 0 or n_out <= 0:
            return _j(400, {"error": "Epsilon and n_out must be positive values."})
    except Exception as e:
        return _j(400, {"error": f"Invalid request parameters: {str(e)}"})

    # 3. Plan Restrictions Enforcement
    if eps < p["min_eps"]:
        return _j(402, {
            "error": f"Selected ε = {eps} is below the {p['name']} plan limit (min ε = {p['min_eps']}). Upgrade to Pro or Enterprise for ultra-tight privacy."
        })

    if len(rows) > p["max_in"]:
        return _j(402, {
            "error": f"Dataset contains {len(rows):,} rows. {p['name']} plan allows up to {p['max_in']:,} input rows. Upgrade to proceed."
        })

    if n_out > p["max_out"]:
        return _j(402, {
            "error": f"Requested {n_out:,} output rows exceeds {p['name']} limit ({p['max_out']:,} rows). Upgrade for higher capacity."
        })

    if mechanism == "gaussian" and not p.get("cert", False):
        return _j(402, {
            "error": "Gaussian (ε, δ)-Differential Privacy is an Enterprise feature. Please upgrade to unlock."
        })

    # 4. Synthesize Data
    out, tvd, mech_label, metrics = generate_detailed(
        header=header,
        rows=rows,
        eps=eps,
        n_out=n_out,
        mechanism=mechanism,
        delta=delta
    )

    # 5. Format Output CSV for direct download
    csv_string = None
    if n_out <= 50000 or p["report"]:
        out_buf = io.StringIO()
        writer = csv.writer(out_buf)
        writer.writerow(header)
        writer.writerows(out)
        csv_string = out_buf.getvalue()

    # 6. Save Job Record to DB
    job_payload = {
        "ts": time.time(),
        "plan": user_plan,
        "dataset_name": dataset_name,
        "epsilon": eps,
        "delta": delta if mechanism == "gaussian" else 0.0,
        "mechanism": mech_label,
        "n_in": len(rows),
        "n_out": n_out,
        "tvd": round(tvd, 4),
        "fidelity_score": metrics["fidelity_score"],
        "metrics_json": metrics,
        "audit_hash": metrics["audit_hash"],
        "input_data": raw_csv[:2000],  # preview snapshot
        "generated_data": json.dumps([header] + out[:100])
    }
    
    job_id, job_uid = save_job_record(job_payload)

    # 7. Build Response
    res = {
        "job_id": job_id,
        "job_uid": job_uid,
        "header": header,
        "rows": out[:200],  # preview first 200 rows in UI
        "total": len(out),
        "epsilon": eps,
        "mechanism": mech_label,
        "tvd": round(tvd, 4),
        "fidelity_score": metrics["fidelity_score"],
        "utility_loss_pct": metrics["utility_loss_pct"],
        "audit_hash": metrics["audit_hash"],
        "user_plan": user_plan
    }

    if p["report"]:
        res["column_metrics"] = metrics["column_metrics"]
        res["joint_preservation"] = metrics["joint_preservation"]

    if p["cert"]:
        res["certificate"] = (
            f"Differential Privacy Compliance Certificate | ε={eps}, δ={delta if mechanism == 'gaussian' else 0} | "
            f"Mechanism={mech_label} | Cryptographic Audit Digest: {metrics['audit_hash']} | "
            f"Verified under DPSynth Enterprise Engine"
        )

    if csv_string:
        res["csv"] = csv_string

    return _j(200, res)

def route(method, path, body_bytes, headers=None):
    """Unified HTTP router for both raw asyncio server and WSGI/ASGI bridges."""
    headers = headers or {}
    auth_header = headers.get("authorization") or headers.get("x-api-key")

    # Static & Webhook endpoints
    if method == "GET":
        if path == "/health":
            return _j(200, {"ok": True, "service": "DPSynth", "version": "2.0.0", "status": "operational"})
        if path == "/api/plans":
            return _j(200, PLANS)
        if path == "/api/stats":
            return _j(200, get_system_stats())
        if path == "/api/history":
            return _j(200, history(30))
        if path.startswith("/api/jobs/"):
            job_id = path.split("/api/jobs/")[1].strip()
            job = get_job_by_id(job_id)
            return _j(200, job) if job else _j(404, {"error": "Job not found"})
        if path.startswith("/api/payments/invoice/"):
            inv_no = path.split("/api/payments/invoice/")[1].strip()
            html = generate_tax_invoice_html(inv_no)
            if html:
                return 200, html.encode("utf-8"), "text/html; charset=utf-8"
            return _j(404, {"error": "Invoice not found"})
        if path.startswith("/api/user/status"):
            # Check user status
            q = path.split("?")[1] if "?" in path else ""
            params = dict(item.split("=") for item in q.split("&") if "=" in item)
            user = None
            if "api_key" in params:
                user = get_user_by_api_key(params["api_key"])
            elif "email" in params:
                user = get_user_by_email(params["email"])
            return _j(200, {"found": bool(user), "user": user or {}})
        return static_handler(path)

    # POST JSON APIs
    try:
        body = json.loads(body_bytes.decode("utf-8") if body_bytes else "{}")
    except Exception:
        return _j(400, {"error": "Invalid JSON request payload"})

    if path == "/api/generate":
        return handle_generate(body, auth_header)
    if path == "/api/subscribe":
        return handle_subscribe_legacy(body)
    if path == "/api/payments/quote":
        try:
            q = calculate_quote(body.get("plan", "pro"), body.get("billing_cycle", "monthly"), body.get("promo_code"))
            return _j(200, q)
        except Exception as e:
            return _j(400, {"error": str(e)})
    if path == "/api/payments/create-order":
        return handle_create_order(body)
    if path == "/api/payments/verify":
        return handle_verify_payment(body)
    if path == "/api/payments/coupons/validate":
        return handle_validate_coupon(body)

    return _j(404, {"error": "Route not found"})
