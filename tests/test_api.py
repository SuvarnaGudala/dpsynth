"""Comprehensive Integration Tests for DPSynth API, Differential Privacy Engine, and Payments."""
import unittest
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.handlers import route
from app.db import get_connection

class TestDPSynthIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv_sample = "age,city,salary\n25,Mumbai,50000\n30,Delhi,65000\n35,Bengaluru,80000\n40,Mumbai,95000\n45,Pune,110000"

    def test_health_check(self):
        code, body, ctype = route("GET", "/health", b"")
        self.assertEqual(code, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("service"), "DPSynth")

    def test_plans_endpoint(self):
        code, body, _ = route("GET", "/api/plans", b"")
        self.assertEqual(code, 200)
        plans = json.loads(body.decode("utf-8"))
        self.assertIn("free", plans)
        self.assertIn("pro", plans)
        self.assertIn("enterprise", plans)
        self.assertEqual(plans["pro"]["price"], 499)

    def test_generate_free_plan(self):
        req = {
            "csv": self.csv_sample,
            "epsilon": 1.0,
            "n_out": 20,
            "plan": "free"
        }
        code, body, _ = route("POST", "/api/generate", json.dumps(req).encode())
        self.assertEqual(code, 200)
        res = json.loads(body.decode("utf-8"))
        self.assertEqual(res["total"], 20)
        self.assertTrue(0 <= res["tvd"] <= 1.0)
        self.assertTrue(len(res["audit_hash"]) == 64)  # SHA-256 length

    def test_generate_plan_gating(self):
        # Free plan attempting epsilon below 0.5 should return 402
        req = {
            "csv": self.csv_sample,
            "epsilon": 0.1,  # below 0.5 minimum for free
            "n_out": 20,
            "plan": "free"
        }
        code, body, _ = route("POST", "/api/generate", json.dumps(req).encode())
        self.assertEqual(code, 402)
        err = json.loads(body.decode("utf-8"))
        self.assertIn("below the Free Starter plan limit", err["error"])

    def test_payment_quote_with_coupon(self):
        req = {
            "plan": "pro",
            "billing_cycle": "monthly",
            "promo_code": "WELCOME20"
        }
        code, body, _ = route("POST", "/api/payments/quote", json.dumps(req).encode())
        self.assertEqual(code, 200)
        quote = json.loads(body.decode("utf-8"))
        self.assertEqual(quote["base_amount"], 499)
        self.assertEqual(quote["discount_pct"], 20)
        self.assertAlmostEqual(quote["discount_amount"], 99.8, places=2)
        self.assertAlmostEqual(quote["subtotal"], 399.2, places=2)
        self.assertEqual(quote["gst_rate_pct"], 18)

    def test_payment_order_and_verification_flow(self):
        # 1. Create Order
        order_req = {
            "email": "researcher@company.com",
            "plan": "pro",
            "billing_cycle": "annual",
            "promo_code": "WELCOME20",
            "customer_name": "Dr. R. Sharma",
            "customer_company": "BioResearch Labs",
            "customer_gstin": "36AABCD1234E1Z5",
            "gateway": "sandbox"
        }
        code, body, _ = route("POST", "/api/payments/create-order", json.dumps(order_req).encode())
        self.assertEqual(code, 200)
        order = json.loads(body.decode("utf-8"))
        order_id = order["order_id"]
        inv_no = order["invoice_number"]
        self.assertTrue(order_id.startswith("ord_"))

        # 2. Verify Payment
        verify_req = {
            "order_id": order_id,
            "payment_id": "pay_test_suite_999",
            "signature": "sandbox_test_signature",
            "gateway": "sandbox"
        }
        code, body, _ = route("POST", "/api/payments/verify", json.dumps(verify_req).encode())
        self.assertEqual(code, 200)
        verify_res = json.loads(body.decode("utf-8"))
        self.assertTrue(verify_res["ok"])
        self.assertEqual(verify_res["plan"], "pro")
        api_key = verify_res["api_key"]
        self.assertTrue(api_key.startswith("dps_"))

        # 3. Retrieve Tax Invoice HTML
        code, inv_html, ctype = route("GET", f"/api/payments/invoice/{inv_no}", b"")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        html_str = inv_html.decode("utf-8")
        self.assertIn("Tax Invoice", html_str)
        self.assertIn("36AABCD1234E1Z5", html_str)
        self.assertIn("BioResearch Labs", html_str)

        # 4. Use newly minted API key for high-precision generation (eps 0.1 allowed on Pro)
        pro_gen_req = {
            "csv": self.csv_sample,
            "epsilon": 0.1,  # Allowed for Pro tier!
            "n_out": 50,
            "api_key": api_key
        }
        code, gen_body, _ = route("POST", "/api/generate", json.dumps(pro_gen_req).encode(), {"x-api-key": api_key})
        self.assertEqual(code, 200)
        gen_res = json.loads(gen_body.decode("utf-8"))
        self.assertEqual(gen_res["user_plan"], "pro")
        self.assertEqual(gen_res["total"], 50)
        self.assertIn("column_metrics", gen_res)

if __name__ == "__main__":
    unittest.main()
