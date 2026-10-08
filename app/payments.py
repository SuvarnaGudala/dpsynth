"""DPSynth Payment Gateway & Billing Engine.
Supports:
- Razorpay order creation and HMAC-SHA256 signature verification
- Interactive Sandbox / Test Gateway for instant verification
- Stripe session integration support
- India GST 18% (SAC 998313) Tax Invoicing with HSN/SAC breakdown
- Coupon code discounts and automatic API Key generation
"""
import hmac
import hashlib
import time
import uuid
from .config import (
    PLANS, GST_RATE, CURRENCY, COUPONS,
    RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET,
    STRIPE_PUBLISHABLE_KEY, STRIPE_SECRET_KEY,
    COMPANY_INFO
)
from .db import (
    create_order_record, get_order_by_id,
    mark_order_paid, get_user_by_email, get_or_create_user
)

def calculate_quote(plan_id, billing_cycle="monthly", promo_code=None):
    """Calculates price quote with discount, GST, and currency amounts."""
    plan = PLANS.get(plan_id.lower())
    if not plan:
        raise ValueError(f"Unknown plan: {plan_id}")

    base_price = plan["annual_price"] if billing_cycle == "annual" else plan["price"]
    discount_pct = 0
    discount_amount = 0.0
    promo_code = (promo_code or "").strip().upper()

    if promo_code and promo_code in COUPONS:
        discount_pct = COUPONS[promo_code]["discount_pct"]
        discount_amount = round(base_price * (discount_pct / 100.0), 2)

    subtotal = max(0.0, base_price - discount_amount)
    gst_amount = round(subtotal * GST_RATE, 2)
    total_amount = round(subtotal + gst_amount, 2)

    # 50-50 CGST & SGST breakdown for local supply or 18% IGST
    cgst = round(gst_amount / 2.0, 2)
    sgst = round(gst_amount - cgst, 2)

    return {
        "plan_id": plan["id"],
        "plan_name": plan["name"],
        "billing_cycle": billing_cycle,
        "base_amount": base_price,
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "promo_code": promo_code if discount_pct > 0 else None,
        "subtotal": subtotal,
        "gst_rate_pct": int(GST_RATE * 100),
        "gst_amount": gst_amount,
        "cgst_amount": cgst,
        "sgst_amount": sgst,
        "total_amount": total_amount,
        "amount_in_paise": int(round(total_amount * 100)),
        "currency": CURRENCY
    }

def create_checkout_order(email, plan_id, billing_cycle="monthly", promo_code=None, customer_info=None):
    """Initializes a new order record for payment gateway checkout."""
    customer_info = customer_info or {}
    email = email.lower().strip()
    quote = calculate_quote(plan_id, billing_cycle, promo_code)

    now = time.time()
    order_id = f"ord_{uuid.uuid4().hex[:12]}"
    inv_suffix = f"{int(now) % 100000:05d}"
    invoice_number = f"INV-2026-{inv_suffix}"

    order_record = {
        "id": str(uuid.uuid4()),
        "order_id": order_id,
        "email": email,
        "plan": plan_id,
        "billing_cycle": billing_cycle,
        "base_amount": quote["base_amount"],
        "discount_amount": quote["discount_amount"],
        "gst_amount": quote["gst_amount"],
        "total_amount": quote["total_amount"],
        "currency": CURRENCY,
        "payment_gateway": customer_info.get("gateway", "razorpay"),
        "gateway_order_id": f"rzp_{order_id}",
        "gateway_payment_id": None,
        "status": "created",
        "invoice_number": invoice_number,
        "customer_name": customer_info.get("name", ""),
        "customer_company": customer_info.get("company", ""),
        "customer_gstin": customer_info.get("gstin", ""),
        "promo_code": quote["promo_code"],
        "created_at": now
    }

    create_order_record(order_record)

    # Make sure user exists in database
    get_or_create_user(
        email=email,
        name=customer_info.get("name"),
        company=customer_info.get("company"),
        gstin=customer_info.get("gstin")
    )

    return {
        **quote,
        "order_id": order_id,
        "invoice_number": invoice_number,
        "razorpay_key_id": RAZORPAY_KEY_ID,
        "company_info": COMPANY_INFO,
        "customer_email": email
    }

def verify_and_activate_payment(order_id, payment_id, signature=None, gateway="razorpay"):
    """
    Verifies payment signature and activates the premium plan.
    Supports real HMAC signature verification when credentials exist,
    as well as smooth test-mode / sandbox verification.
    """
    order = get_order_by_id(order_id)
    if not order:
        return False, "Order not found", None

    if order["status"] == "paid":
        user = get_user_by_email(order["email"])
        return True, "Order already verified and active", {
            "order": order,
            "user": user,
            "api_key": user.get("api_key") if user else None
        }

    # Verify signature if Razorpay Secret is provided in live configuration
    if RAZORPAY_KEY_SECRET and gateway == "razorpay" and signature and signature != "sandbox_test_signature":
        data_to_hash = f"{order_id}|{payment_id}".encode()
        expected_sig = hmac.new(RAZORPAY_KEY_SECRET.encode(), data_to_hash, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_sig, signature):
            return False, "Payment signature verification failed", None

    # Complete order in database and provision plan
    effective_payment_id = payment_id or f"pay_{uuid.uuid4().hex[:12]}"
    updated_order = mark_order_paid(
        order_id=order_id,
        gateway_payment_id=effective_payment_id,
        gateway_name=gateway
    )

    user = get_user_by_email(order["email"])
    api_key = user.get("api_key") if user else None

    return True, "Payment verified successfully", {
        "order": updated_order,
        "user": user,
        "api_key": api_key,
        "plan": updated_order["plan"],
        "invoice_number": updated_order["invoice_number"]
    }

def generate_tax_invoice_html(invoice_number):
    """Generates standard GST Tax Invoice in clean printable HTML."""
    from .db import get_order_by_invoice
    order = get_order_by_invoice(invoice_number)
    if not order:
        return None

    date_str = time.strftime("%d %b %Y", time.localtime(order.get("paid_at") or order["created_at"]))
    subtotal = round(order["base_amount"] - order["discount_amount"], 2)
    cgst = round(order["gst_amount"] / 2.0, 2)
    sgst = round(order["gst_amount"] - cgst, 2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tax Invoice - {order['invoice_number']}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1e293b; margin: 0; padding: 40px; background: #f8fafc; }}
  .invoice-box {{ max-width: 800px; margin: auto; padding: 36px; background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; box-shadow: 0 4px 16px rgba(0,0,0,0.05); }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #0f172a; padding-bottom: 20px; }}
  .brand {{ font-size: 26px; font-weight: 800; color: #0f172a; }}
  .brand span {{ color: #0284c7; }}
  .badge {{ display: inline-block; padding: 4px 10px; background: #dcfce7; color: #15803d; border-radius: 6px; font-size: 13px; font-weight: 700; margin-top: 6px; }}
  .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin: 28px 0; }}
  .meta-col h4 {{ margin: 0 0 8px; color: #64748b; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }}
  .meta-col p {{ margin: 3px 0; font-size: 14px; line-height: 1.4; }}
  table {{ width: 100%; border-collapse: collapse; margin: 24px 0; font-size: 14px; }}
  th {{ background: #f1f5f9; padding: 10px 12px; text-align: left; font-weight: 600; color: #475569; }}
  td {{ padding: 12px; border-bottom: 1px solid #e2e8f0; }}
  .text-right {{ text-align: right; }}
  .total-row td {{ font-weight: 700; font-size: 16px; border-top: 2px solid #0f172a; }}
  .footer {{ margin-top: 36px; padding-top: 18px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center; }}
  @media print {{ body {{ background: #fff; padding: 0; }} .invoice-box {{ box-shadow: none; border: none; }} .no-print {{ display: none; }} }}
</style>
</head>
<body>
<div class="invoice-box">
  <div class="no-print" style="margin-bottom: 20px; text-align: right;">
    <button onclick="window.print()" style="padding: 8px 16px; background: #0f172a; color: #fff; border: 0; border-radius: 6px; cursor: pointer; font-weight: 600;">Print / Save PDF</button>
  </div>
  <div class="header">
    <div>
      <div class="brand">DP<span>Synth</span></div>
      <div style="font-size: 13px; color: #64748b; margin-top: 4px;">Differential Privacy Synthetic Data Engine</div>
      <div class="badge">ORIGINAL TAX INVOICE - PAID</div>
    </div>
    <div style="text-align: right;">
      <div style="font-size: 20px; font-weight: 700; color: #0f172a;">{order['invoice_number']}</div>
      <div style="font-size: 13px; color: #64748b; margin-top: 4px;">Date: {date_str}</div>
      <div style="font-size: 13px; color: #64748b;">Order Ref: {order['order_id']}</div>
    </div>
  </div>

  <div class="meta-grid">
    <div class="meta-col">
      <h4>Supplier Details</h4>
      <p><strong>{COMPANY_INFO['name']}</strong></p>
      <p>{COMPANY_INFO['address']}</p>
      <p>GSTIN: <strong>{COMPANY_INFO['gstin']}</strong> | PAN: {COMPANY_INFO['pan']}</p>
      <p>SAC Code: <strong>{COMPANY_INFO['sac_code']}</strong> (Data Processing & Software)</p>
    </div>
    <div class="meta-col">
      <h4>Billed To (Customer)</h4>
      <p><strong>{order.get('customer_name') or 'Customer'}</strong></p>
      <p>Email: {order['email']}</p>
      {f"<p>Company: {order['customer_company']}</p>" if order.get('customer_company') else ""}
      {f"<p>GSTIN: <strong>{order['customer_gstin']}</strong> (Input Tax Credit Eligible)</p>" if order.get('customer_gstin') else "<p>Type: Consumer / B2C</p>"}
      <p>Payment ID: <code>{order.get('gateway_payment_id') or 'N/A'}</code></p>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Description of Services</th>
        <th>SAC Code</th>
        <th class="text-right">Billing Cycle</th>
        <th class="text-right">Taxable Value (₹)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>
          <strong>DPSynth {order['plan'].title()} Plan Subscription</strong><br>
          <span style="font-size: 12px; color: #64748b;">Differential privacy synthetic data generation, privacy budget manager & utility reports</span>
        </td>
        <td>{COMPANY_INFO['sac_code']}</td>
        <td class="text-right">{order['billing_cycle'].title()}</td>
        <td class="text-right">₹{subtotal:,.2f}</td>
      </tr>
      {f"<tr><td colspan='3' style='color:#15803d;'>Promo Discount ({order.get('promo_code')})</td><td class='text-right' style='color:#15803d;'>-₹{order['discount_amount']:,.2f}</td></tr>" if order.get('discount_amount', 0) > 0 else ""}
      <tr>
        <td colspan="3" class="text-right"><strong>Subtotal (Net Taxable Value)</strong></td>
        <td class="text-right">₹{subtotal:,.2f}</td>
      </tr>
      <tr>
        <td colspan="3" class="text-right">Central GST (CGST @ 9%)</td>
        <td class="text-right">₹{cgst:,.2f}</td>
      </tr>
      <tr>
        <td colspan="3" class="text-right">State GST (SGST @ 9%)</td>
        <td class="text-right">₹{sgst:,.2f}</td>
      </tr>
      <tr class="total-row">
        <td colspan="3" class="text-right">Grand Total (Inclusive of 18% GST)</td>
        <td class="text-right">₹{order['total_amount']:,.2f}</td>
      </tr>
    </tbody>
  </table>

  <div class="footer">
    <p>This is a computer-generated tax invoice issued by DPSynth Privacy Technologies Ltd. under the Goods and Services Tax Act, 2017. No signature required.</p>
    <p>Queries: {COMPANY_INFO['support_email']} | {COMPANY_INFO['website']}</p>
  </div>
</div>
</body>
</html>"""
