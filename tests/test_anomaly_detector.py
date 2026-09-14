"""Unit tests for anomaly detector covering the 4 anomaly checks."""

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from src.tools.anomaly_detector import detect_anomalies


class TestAnomalyDetector(unittest.TestCase):
    """Test suite for the 4 financial anomaly detection rules."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.empty_history_file = Path(self.temp_dir.name) / "transactions.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_category_spend_vs_rolling_4_week_average(self):
        """Check 1: Flag if current week's category spend is >= 2x trailing 4-week average."""
        ref_date = datetime(2026, 9, 14, 12, 0, 0)

        # Trailing 4 weeks: 1 transaction per week of Rs. 2,000 -> trailing average = Rs. 2,000/week
        txns = [
            {"date": (ref_date - timedelta(days=31)).isoformat(), "amount": 2000.0, "category": "Food & Dining", "merchant_or_recipient": "Cafe A"},
            {"date": (ref_date - timedelta(days=24)).isoformat(), "amount": 2000.0, "category": "Food & Dining", "merchant_or_recipient": "Cafe B"},
            {"date": (ref_date - timedelta(days=17)).isoformat(), "amount": 2000.0, "category": "Food & Dining", "merchant_or_recipient": "Cafe C"},
            {"date": (ref_date - timedelta(days=10)).isoformat(), "amount": 2000.0, "category": "Food & Dining", "merchant_or_recipient": "Cafe D"},
            # Current week spend: Rs. 5,000 at ref_date (2.5x the trailing 2,000 average)
            {"date": ref_date.isoformat(), "amount": 5000.0, "category": "Food & Dining", "merchant_or_recipient": "Fine Dine"},
        ]

        anomalies = detect_anomalies(txns, history_file=self.empty_history_file)
        cat_anomalies = [a for a in anomalies if a["type"] == "category_overspend"]

        self.assertEqual(len(cat_anomalies), 1)
        self.assertEqual(cat_anomalies[0]["severity"], "medium")
        self.assertIn("Category 'Food & Dining' spend this week", cat_anomalies[0]["description"])
        self.assertIn("2.5x", cat_anomalies[0]["description"])

    def test_duplicate_charge_detection_and_coffee_shop_exemption(self):
        """Check 2: Flag identical charges within 30 min, but exempt coffee shops on same day."""
        base_time = datetime(2026, 9, 10, 14, 0, 0)

        txns = [
            # Duplicate Careem charges 6 minutes apart
            {"date": base_time.isoformat(), "amount": 750.0, "merchant_or_recipient": "Careem", "category": "Transport"},
            {"date": (base_time + timedelta(minutes=6)).isoformat(), "amount": 750.0, "merchant_or_recipient": "Careem", "category": "Transport"},
            # Repeat visit at Espresso Coffee 15 minutes apart on the same day (should NOT be flagged)
            {"date": (base_time + timedelta(hours=2)).isoformat(), "amount": 650.0, "merchant_or_recipient": "Espresso Coffee", "category": "Food & Dining"},
            {"date": (base_time + timedelta(hours=2, minutes=15)).isoformat(), "amount": 650.0, "merchant_or_recipient": "Espresso Coffee", "category": "Food & Dining"},
        ]

        anomalies = detect_anomalies(txns, history_file=self.empty_history_file)
        dup_anomalies = [a for a in anomalies if a["type"] == "duplicate_charge"]

        self.assertEqual(len(dup_anomalies), 1)
        self.assertEqual(dup_anomalies[0]["severity"], "high")
        self.assertIn("Careem", dup_anomalies[0]["description"])
        self.assertNotIn("Espresso Coffee", [a["description"] for a in dup_anomalies])

    def test_unusually_large_single_transaction(self):
        """Check 3: Flag if a single transaction is >= 3x the historical average."""
        ref_date = datetime(2026, 9, 12, 10, 0, 0)

        txns = [
            # History for Shell Fuel Station: avg = (1000 + 1200 + 1100) / 3 = 1100.0
            {"date": (ref_date - timedelta(days=20)).isoformat(), "amount": 1000.0, "merchant_or_recipient": "Shell Fuel Station", "category": "Transport"},
            {"date": (ref_date - timedelta(days=12)).isoformat(), "amount": 1200.0, "merchant_or_recipient": "Shell Fuel Station", "category": "Transport"},
            {"date": (ref_date - timedelta(days=5)).isoformat(), "amount": 1100.0, "merchant_or_recipient": "Shell Fuel Station", "category": "Transport"},
            # New transaction: Rs. 4,500 (> 3x average of 1,100)
            {"date": ref_date.isoformat(), "amount": 4500.0, "merchant_or_recipient": "Shell Fuel Station", "category": "Transport"},
        ]

        anomalies = detect_anomalies(txns, history_file=self.empty_history_file)
        large_anomalies = [a for a in anomalies if a["type"] == "unusually_large_transaction"]

        self.assertEqual(len(large_anomalies), 1)
        self.assertEqual(large_anomalies[0]["severity"], "high")
        self.assertIn("Shell Fuel Station", large_anomalies[0]["description"])
        self.assertIn("4,500.00", large_anomalies[0]["description"])

    def test_end_of_month_projected_overspend_with_refund_netting(self):
        """Check 4: Extrapolate monthly pace against 2-month baseline (> 1.2x), netting refunds."""
        txns = [
            # Month -2 (July 2026): Total spend = Rs. 30,000
            {"date": "2026-07-15T12:00:00", "amount": 30000.0, "merchant_or_recipient": "Vendor A", "category": "Shopping"},
            # Month -1 (August 2026): Total spend = Rs. 30,000
            {"date": "2026-08-15T12:00:00", "amount": 30000.0, "merchant_or_recipient": "Vendor B", "category": "Shopping"},
            # Current Month (September 2026, 30 days):
            # Day 10 positive spend = Rs. 20,000, refund = Rs. 5,000 -> net spend = Rs. 15,000
            {"date": "2026-09-05T12:00:00", "amount": 20000.0, "merchant_or_recipient": "Vendor C", "category": "Shopping"},
            {"date": "2026-09-10T12:00:00", "amount": 5000.0, "is_refund": True, "merchant_or_recipient": "Vendor C", "category": "Shopping"},
        ]
        # Pace on day 10: 15,000 / 10 = 1,500/day
        # Projected for 30 days = 1,500 * 30 = 45,000
        # 45,000 / 30,000 = 1.5x (> 1.2x baseline)

        anomalies = detect_anomalies(txns, history_file=self.empty_history_file)
        proj_anomalies = [a for a in anomalies if a["type"] == "projected_overspend"]

        self.assertEqual(len(proj_anomalies), 1)
        self.assertEqual(proj_anomalies[0]["severity"], "medium")
        self.assertIn("Projected end-of-month spend", proj_anomalies[0]["description"])
        self.assertIn("45,000.00", proj_anomalies[0]["description"])

        # Confirm refund itself is not treated as an anomaly
        for a in anomalies:
            self.assertNotIn("refund", a["type"].lower())


if __name__ == "__main__":
    unittest.main()
