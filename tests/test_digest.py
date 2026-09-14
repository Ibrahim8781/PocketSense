"""Unit tests for build_digest and send_digest tools."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.tools.digest import build_digest, send_digest


class TestDigestTools(unittest.TestCase):
    """Test suite for weekly digest HTML rendering and delivery."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.artifact_path = Path(self.temp_dir.name) / "last_digest.html"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_digest_html_structure(self):
        """Verify that build_digest produces complete HTML with table, anomalies, and naming section."""
        transactions = [
            {"amount": 6450.0, "category": "Food & Dining", "merchant_or_recipient": "Naheed Supermarket"},
            {"amount": 4200.0, "category": "Transport", "merchant_or_recipient": "Shell Fuel Station"},
            {"amount": 1500.0, "is_refund": True, "category": "Food & Dining", "merchant_or_recipient": "Naheed Supermarket"},
        ]
        anomalies = [
            {
                "type": "duplicate_charge",
                "severity": "high",
                "description": "Possible duplicate charge: Rs. 750.00 at Careem within 6 minutes.",
            }
        ]
        pending_transfers = {
            "A*** K***": {"status": "needs_input", "count": 3}
        }

        html = build_digest(transactions, anomalies, pending_transfers)

        # 1. Total Net Spend: 6450 + 4200 - 1500 = 9,150
        self.assertIn("Rs. 9,150.00", html)

        # 2. Category table
        self.assertIn("Food & Dining", html)
        self.assertIn("Transport", html)

        # 3. Anomaly flags
        self.assertIn("Duplicate Charge", html)
        self.assertIn("HIGH", html)
        self.assertIn("Possible duplicate charge: Rs. 750.00 at Careem", html)

        # 4. 'Please name these' section
        self.assertIn("Action Required: Name These Transfers", html)
        self.assertIn("A*** K***", html)
        self.assertIn("python answer_transfer.py", html)

    def test_send_digest_always_saves_local_artifact_even_on_smtp_error(self):
        """send_digest must save to local HTML artifact even if SMTP raises an error."""
        test_html = "<html><body>Test Digest Content</body></html>"

        # Mock SMTP to simulate authentication or network failure
        with patch("smtplib.SMTP", side_effect=Exception("SMTP Connection Refused")):
            result = send_digest(test_html, subject="Test Anomaly Report", artifact_path=self.artifact_path)

            # Function gracefully returns False on SMTP failure
            self.assertFalse(result)

            # But the local HTML artifact MUST exist on disk
            self.assertTrue(self.artifact_path.exists())
            with open(self.artifact_path, "r", encoding="utf-8") as f:
                saved_content = f.read()
            self.assertEqual(saved_content, test_html)

    def test_send_digest_success_flow(self):
        """send_digest calls SMTP starttls, login, and send_message when configured."""
        test_html = "<html><body>Successful Report</body></html>"
        mock_server = MagicMock()

        with patch("os.getenv", side_effect=lambda k, d=None: "dummy@gmail.com" if "GMAIL" in k else d), \
             patch("smtplib.SMTP", return_value=mock_server):
            mock_server.__enter__.return_value = mock_server

            result = send_digest(test_html, subject="Successful Report", artifact_path=self.artifact_path)

            self.assertTrue(result)
            self.assertTrue(self.artifact_path.exists())
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once()
            mock_server.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
