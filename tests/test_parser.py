"""Unit tests for parse_email tool covering currency formatting edge cases."""

import unittest
from src.tools.parser import parse_email


class TestEmailParser(unittest.TestCase):
    """Test suite for bank notification email parsing and currency normalization."""

    def test_rs_with_decimals_and_commas(self):
        """Case 1: 'Rs.' with thousand separators (comma) and two decimal places."""
        raw_email = (
            "From: alerts@hbl.com\n"
            "Date: Mon, 10 Aug 2026 14:15:30 +0500\n"
            "Subject: Transaction Alert\n\n"
            "Dear Customer,\n"
            "You spent Rs. 6,450.50 at NAHEED SUPERMARKET on your Debit Card ending in 4102.\n"
        )
        result = parse_email(raw_email)

        self.assertEqual(result["type"], "card_txn")
        self.assertEqual(result["amount"], 6450.50)
        self.assertEqual(result["merchant_or_recipient"], "NAHEED SUPERMARKET")
        self.assertFalse(result["is_masked"])
        self.assertIn("2026-08-10", result["date"])
        self.assertEqual(result["raw_text"], raw_email)

    def test_pkr_currency_formatting(self):
        """Case 2: 'PKR' currency code with comma and decimal formatting."""
        raw_email = (
            "From: alerts@hbl.com\n"
            "Date: Sun, 13 Sep 2026 16:45:00 +0500\n"
            "Subject: Card Transaction\n\n"
            "Dear Customer,\n"
            "You spent PKR 1,250.00 at SUBWAY on your Debit Card ending in 4102.\n"
        )
        result = parse_email(raw_email)

        self.assertEqual(result["type"], "card_txn")
        self.assertEqual(result["amount"], 1250.0)
        self.assertEqual(result["merchant_or_recipient"], "SUBWAY")
        self.assertFalse(result["is_masked"])
        self.assertIn("2026-09-13", result["date"])

    def test_rupee_symbol_without_spaces(self):
        """Case 3: Unicode Rupee sign '₨' without spaces and integer amount."""
        raw_email = (
            "From: alerts@bank.com\n"
            "Date: Tue, 18 Aug 2026 10:00:00 +0500\n"
            "Subject: Card Notification\n\n"
            "You spent ₨5,000 at CARREFOUR on your Debit Card ending in 9901.\n"
        )
        result = parse_email(raw_email)

        self.assertEqual(result["type"], "card_txn")
        self.assertEqual(result["amount"], 5000.0)
        self.assertEqual(result["merchant_or_recipient"], "CARREFOUR")
        self.assertFalse(result["is_masked"])

    def test_plain_rs_without_period_or_commas(self):
        """Case 4: 'Rs' without period, no thousand commas, and integer amount."""
        raw_email = (
            "From: alerts@bank.com\n"
            "Date: Wed, 19 Aug 2026 15:20:00 +0500\n"
            "Subject: Transaction Alert\n\n"
            "You spent Rs 1250 at MCDONALDS on your card.\n"
        )
        result = parse_email(raw_email)

        self.assertEqual(result["type"], "card_txn")
        self.assertEqual(result["amount"], 1250.0)
        self.assertEqual(result["merchant_or_recipient"], "MCDONALDS")
        self.assertFalse(result["is_masked"])

    def test_masked_and_unmasked_fund_transfers(self):
        """Case 5: Masked recipient with asterisks vs unmasked recipient name."""
        masked_email = (
            "From: alerts@hbl.com\n"
            "Date: Fri, 14 Aug 2026 11:10:00 +0500\n"
            "Subject: Funds Transfer\n\n"
            "Dear Customer,\n"
            "You sent Rs. 15,000.00 to A*** K*** (Acc ****4821) via Mobile Banking.\n"
        )
        masked_result = parse_email(masked_email)

        self.assertEqual(masked_result["type"], "transfer")
        self.assertEqual(masked_result["amount"], 15000.0)
        self.assertEqual(masked_result["merchant_or_recipient"], "A*** K*** (Acc ****4821)")
        self.assertTrue(masked_result["is_masked"])

        unmasked_email = (
            "From: alerts@hbl.com\n"
            "Date: Mon, 17 Aug 2026 12:00:00 +0500\n"
            "Subject: Funds Transfer\n\n"
            "Dear Customer,\n"
            "You sent PKR 2500 to John Doe via Raast.\n"
        )
        unmasked_result = parse_email(unmasked_email)

        self.assertEqual(unmasked_result["type"], "transfer")
        self.assertEqual(unmasked_result["amount"], 2500.0)
        self.assertEqual(unmasked_result["merchant_or_recipient"], "John Doe")
        self.assertFalse(unmasked_result["is_masked"])
        self.assertFalse(unmasked_result["is_refund"])

    def test_refund_reversal_sets_is_refund_flag(self):
        """Case 6: Refund/reversal email sets is_refund: True and normalizes merchant & amount."""
        refund_email = (
            "From: alerts@hbl.com\n"
            "To: customer@example.com\n"
            "Subject: Transaction Alert: Refund / Reversal Credited\n"
            "Date: Thu, 10 Sep 2026 11:20:00 +0500\n\n"
            "Dear Customer,\n\n"
            "A reversal / refund of Rs. 3,499.00 from DARAZ.PK has been credited to your account "
            "ending in 4102 on 10-Sep-2026 11:19:40 PKT.\n\n"
            "Available Balance: Rs. 40,580.00.\n\n"
            "Thank you for banking with HBL.\n"
        )
        result = parse_email(refund_email)

        self.assertTrue(result["is_refund"])
        self.assertEqual(result["type"], "card_txn")
        self.assertEqual(result["amount"], 3499.0)
        self.assertEqual(result["merchant_or_recipient"], "DARAZ.PK")
        self.assertFalse(result["is_masked"])
        self.assertIn("2026-09-10", result["date"])


if __name__ == "__main__":
    unittest.main()
