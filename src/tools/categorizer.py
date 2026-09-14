"""Merchant categorizer tool for PocketSense."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

import boto3
from dotenv import load_dotenv
from strands import tool

logger = logging.getLogger(__name__)

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "memory"
MERCHANT_CACHE_FILE = MEMORY_DIR / "merchant_categories.json"

VALID_CATEGORIES = [
    "Food & Dining",
    "Utilities",
    "Transport",
    "Shopping",
    "Entertainment",
    "Health",
    "Rent",
    "Transfers",
    "Other",
]


def _load_cache(file_path: Optional[Path] = None) -> Dict[str, str]:
    """Load merchant categories from JSON cache file."""
    path = file_path or MERCHANT_CACHE_FILE
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            data = json.loads(content)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read merchant categories cache from %s: %s", path, e)
        return {}


def _save_cache(cache: Dict[str, str], file_path: Optional[Path] = None) -> None:
    """Save merchant categories to JSON cache file."""
    path = file_path or MERCHANT_CACHE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.error("Could not write merchant categories cache to %s: %s", path, e)


def _lookup_merchant(cache: Dict[str, str], merchant: str) -> Optional[str]:
    """Look up merchant name in cache (exact match, case-insensitive)."""
    norm_merchant = merchant.strip().lower()
    for cached_name, category in cache.items():
        if cached_name.strip().lower() == norm_merchant:
            return category
    return None


def _call_llm(prompt: str) -> str:
    """Call Bedrock LLM to classify merchant."""
    load_dotenv()
    model_id = os.getenv("BEDROCK_MODEL_ID")
    if not model_id:
        raise ValueError("BEDROCK_MODEL_ID environment variable is not set.")

    region = os.getenv("AWS_REGION", "us-east-1")
    client = boto3.client("bedrock-runtime", region_name=region)

    try:
        response = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"temperature": 0.0, "maxTokens": 50},
        )
        return response["output"]["message"]["content"][0]["text"].strip()
    except Exception as e:
        err_name = type(e).__name__
        err_msg = str(e)
        if (
            "AccessDenied" in err_name
            or "AccessDenied" in err_msg
            or "Marketplace" in err_msg
            or "verification" in err_msg
            or "ValidationException" in err_name
        ):
            print(f"\n[!] Bedrock Model Access Notice: Call to model '{model_id}' failed with {err_name}.")
            print(f"    Details: {err_msg}")
            print("    Model access is not fully granted yet in AWS Bedrock console or account verification is pending.")
            print("    Using default category 'Other' without retrying.\n")
            return "Other"
        raise


def _normalize_category_response(raw_text: str) -> str:
    """Extract one of the valid categories from LLM response text."""
    clean = raw_text.strip().rstrip(".")
    # Exact match first
    for cat in VALID_CATEGORIES:
        if cat.lower() == clean.lower():
            return cat
    # Substring match
    for cat in VALID_CATEGORIES:
        if cat.lower() in clean.lower():
            return cat
    return "Other"


@tool
def categorize_merchant(merchant: str) -> str:
    """
    Categorize a merchant into a spending category.

    Looks up merchant in memory/merchant_categories.json first (case-insensitive).
    If not cached, queries the LLM and caches the resulting category.

    Args:
        merchant: Name of the merchant (e.g. 'Foodpanda', 'K-Electric').

    Returns:
        str: Category name from allowed categories.
    """
    merchant_clean = merchant.strip()
    cache = _load_cache()

    # 1. Check cache first
    cached_category = _lookup_merchant(cache, merchant_clean)
    if cached_category:
        logger.info("Cache hit for merchant '%s': %s", merchant_clean, cached_category)
        return cached_category

    # 2. Cache miss -> query LLM
    logger.info("Cache miss for merchant '%s', querying LLM...", merchant_clean)
    prompt = (
        f"What spending category does {merchant_clean} belong to? "
        "Reply with ONE category word from: Food & Dining, Utilities, Transport, "
        "Shopping, Entertainment, Health, Rent, Transfers, Other."
    )
    raw_response = _call_llm(prompt)
    category = _normalize_category_response(raw_response)

    # 3. Cache result back into merchant_categories.json
    cache[merchant_clean] = category
    _save_cache(cache)
    logger.info("Cached category for '%s': %s", merchant_clean, category)

    return category
