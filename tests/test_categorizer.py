"""Unit tests for categorize_merchant tool covering caching and LLM fallback."""

import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.tools.categorizer import categorize_merchant


class TestMerchantCategorizer(unittest.TestCase):
    """Test suite for merchant categorization and caching."""

    def setUp(self):
        # Create a temporary cache file for isolated testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_cache_file = Path(self.temp_dir.name) / "merchant_categories.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_caching_and_cache_hits_for_merchants(self):
        """Categorize 'Foodpanda' and 'K-Electric', verifying second calls are cache hits."""

        def mock_llm_response(prompt: str) -> str:
            if "Foodpanda" in prompt:
                return "Food & Dining"
            elif "K-Electric" in prompt:
                return "Utilities"
            return "Other"

        with patch("src.tools.categorizer.MERCHANT_CACHE_FILE", self.test_cache_file), \
             patch("src.tools.categorizer._call_llm", side_effect=mock_llm_response) as mock_llm, \
             self.assertLogs("src.tools.categorizer", level=logging.INFO) as log_capture:

            # 1. First call for Foodpanda -> Cache miss, calls LLM
            cat_1 = categorize_merchant("Foodpanda")
            self.assertEqual(cat_1, "Food & Dining")
            self.assertEqual(mock_llm.call_count, 1)

            # 2. Second call for Foodpanda (case-insensitive test) -> Cache hit, does NOT call LLM
            cat_2 = categorize_merchant("foodpanda")
            self.assertEqual(cat_2, "Food & Dining")
            self.assertEqual(mock_llm.call_count, 1, "LLM must NOT be called on cache hit for Foodpanda")

            # 3. First call for K-Electric -> Cache miss, calls LLM
            cat_3 = categorize_merchant("K-Electric")
            self.assertEqual(cat_3, "Utilities")
            self.assertEqual(mock_llm.call_count, 2)

            # 4. Second call for K-Electric -> Cache hit, does NOT call LLM
            cat_4 = categorize_merchant("K-Electric")
            self.assertEqual(cat_4, "Utilities")
            self.assertEqual(mock_llm.call_count, 2, "LLM must NOT be called on cache hit for K-Electric")

            # Verify logs prove cache hits
            log_output = "\n".join(log_capture.output)
            self.assertIn("Cache hit for merchant 'foodpanda': Food & Dining", log_output)
            self.assertIn("Cache hit for merchant 'K-Electric': Utilities", log_output)

            # Verify persisted cache content
            with open(self.test_cache_file, "r", encoding="utf-8") as f:
                saved_cache = json.load(f)
            self.assertEqual(saved_cache.get("Foodpanda"), "Food & Dining")
            self.assertEqual(saved_cache.get("K-Electric"), "Utilities")


if __name__ == "__main__":
    unittest.main()
