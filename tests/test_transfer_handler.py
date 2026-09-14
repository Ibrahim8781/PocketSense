"""Unit tests for transfer_handler and answer_transfer CLI helper."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.tools.transfer_handler import confirm_transfer, handle_transfer


class TestTransferHandler(unittest.TestCase):
    """Test suite for transfer handling, masked recipient counters, and CLI confirmation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.transfers_file = Path(self.temp_dir.name) / "known_transfers.json"
        self.txns_file = Path(self.temp_dir.name) / "transactions.json"
        self.actual_known_transfers = Path(__file__).resolve().parent.parent / "memory" / "known_transfers.json"
        self._backup_actual = None
        if self.actual_known_transfers.exists():
            with open(self.actual_known_transfers, "r", encoding="utf-8") as f:
                self._backup_actual = f.read()

    def tearDown(self):
        self.temp_dir.cleanup()
        if self._backup_actual is not None:
            with open(self.actual_known_transfers, "w", encoding="utf-8") as f:
                f.write(self._backup_actual)

    def test_unmasked_recipient_delegates_to_categorize_merchant(self):
        """Unmasked recipient should delegate to categorize_merchant."""
        with patch("src.tools.transfer_handler.categorize_merchant", return_value="Food & Dining") as mock_cat:
            cat = handle_transfer("Ali Khan", 2500.0, transfers_file=self.transfers_file)
            self.assertEqual(cat, "Food & Dining")
            mock_cat.assert_called_once_with("Ali Khan")

    def test_masked_recipient_count_progression_and_needs_input(self):
        """Masked recipient increments pending count, turns into 'needs_input' at >= 3."""
        recipient = "A*** K***"

        # 1st time
        res1 = handle_transfer(recipient, 12000.0, transfers_file=self.transfers_file)
        self.assertEqual(res1, "Transfers (uncategorized)")
        with open(self.transfers_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data[recipient]["status"], "pending")
        self.assertEqual(data[recipient]["count"], 1)

        # 2nd time
        res2 = handle_transfer(recipient, 15000.0, transfers_file=self.transfers_file)
        self.assertEqual(res2, "Transfers (uncategorized)")
        with open(self.transfers_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data[recipient]["status"], "pending")
        self.assertEqual(data[recipient]["count"], 2)

        # 3rd time -> triggers 'needs_input'
        res3 = handle_transfer(recipient, 12000.0, transfers_file=self.transfers_file)
        self.assertEqual(res3, "Transfers (uncategorized)")
        with open(self.transfers_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data[recipient]["status"], "needs_input")
        self.assertEqual(data[recipient]["count"], 3)

    def test_confirm_transfer_updates_past_transactions_and_future_calls(self):
        """Confirming transfer updates known_transfers, past transactions, and future lookups."""
        recipient = "A*** K***"

        # Create some past transactions in transactions.json
        past_txns = [
            {"id": 1, "merchant_or_recipient": "A*** K***", "category": "Transfers (uncategorized)", "amount": 12000.0},
            {"id": 2, "merchant_or_recipient": "NAHEED", "category": "Food & Dining", "amount": 6450.0},
            {"id": 3, "merchant_or_recipient": "A*** K***", "category": "Transfers (uncategorized)", "amount": 15000.0},
        ]
        with open(self.txns_file, "w", encoding="utf-8") as f:
            json.dump(past_txns, f)

        # Setup initial pending status in known_transfers
        with open(self.transfers_file, "w", encoding="utf-8") as f:
            json.dump({recipient: {"status": "needs_input", "count": 3}}, f)

        # Confirm transfer with label 'Roommate rent'
        updated = confirm_transfer(recipient, "Roommate rent", transfers_file=self.transfers_file, txns_file=self.txns_file)
        self.assertEqual(updated, 2)

        # Check known_transfers is now confirmed
        with open(self.transfers_file, "r", encoding="utf-8") as f:
            transfers = json.load(f)
        self.assertEqual(transfers[recipient]["status"], "confirmed")
        self.assertEqual(transfers[recipient]["label"], "Roommate rent")

        # Check past transactions updated
        with open(self.txns_file, "r", encoding="utf-8") as f:
            updated_txns = json.load(f)
        self.assertEqual(updated_txns[0]["category"], "Roommate rent")
        self.assertEqual(updated_txns[1]["category"], "Food & Dining")
        self.assertEqual(updated_txns[2]["category"], "Roommate rent")

        # Check future call returns the remembered label
        future_res = handle_transfer(recipient, 18500.0, transfers_file=self.transfers_file)
        self.assertEqual(future_res, "Roommate rent")

    def test_cli_answer_transfer(self):
        """Test answer_transfer.py CLI invocation directly."""
        cli_script = Path(__file__).resolve().parent.parent / "answer_transfer.py"
        res = subprocess.run(
            [sys.executable, str(cli_script), "A*** K***", "Roommate rent"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Successfully confirmed 'A*** K***' -> 'Roommate rent'", res.stdout)


if __name__ == "__main__":
    unittest.main()
