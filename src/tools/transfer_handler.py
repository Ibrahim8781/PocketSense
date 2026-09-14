"""Transfer handler tool for PocketSense."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from strands import tool
from src.tools.categorizer import categorize_merchant

logger = logging.getLogger(__name__)

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "memory"
KNOWN_TRANSFERS_FILE = MEMORY_DIR / "known_transfers.json"
TRANSACTIONS_FILE = MEMORY_DIR / "transactions.json"

UNCATEGORIZED_TRANSFER_LABEL = "Transfers (uncategorized)"


def _load_json(file_path: Path) -> Any:
    """Load JSON from file safely, returning empty dict if missing or empty."""
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read JSON from %s: %s", file_path, e)
        return {}


def _save_json(data: Any, file_path: Path) -> None:
    """Save data to JSON file with indentation."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        logger.error("Could not write JSON to %s: %s", file_path, e)


def confirm_transfer(
    recipient: str,
    label: str,
    transfers_file: Optional[Path] = None,
    txns_file: Optional[Path] = None,
) -> int:
    """
    Confirm label for a masked transfer recipient in known_transfers.json,
    and update all past-recorded transactions matching that recipient in transactions.json.

    Returns:
        int: Count of past transactions updated.
    """
    target_transfers_file = transfers_file or KNOWN_TRANSFERS_FILE
    target_txns_file = txns_file or TRANSACTIONS_FILE

    # 1. Update known_transfers.json
    transfers = _load_json(target_transfers_file)
    if not isinstance(transfers, dict):
        transfers = {}

    recipient_key = recipient.strip()
    entry = transfers.get(recipient_key, {})
    entry["status"] = "confirmed"
    entry["label"] = label.strip()
    if "count" not in entry:
        entry["count"] = 1
    transfers[recipient_key] = entry
    _save_json(transfers, target_transfers_file)

    # 2. Update past transactions in transactions.json
    updated_count = 0
    txns = _load_json(target_txns_file)
    if isinstance(txns, list):
        for tx in txns:
            if not isinstance(tx, dict):
                continue
            tx_recipient = tx.get("merchant_or_recipient") or tx.get("recipient")
            if tx_recipient and tx_recipient.strip() == recipient_key:
                tx["category"] = label.strip()
                updated_count += 1
        if updated_count > 0:
            _save_json(txns, target_txns_file)

    logger.info(
        "Confirmed transfer label '%s' for '%s'. Updated %d past transactions.",
        label,
        recipient_key,
        updated_count,
    )
    return updated_count


@tool
def handle_transfer(
    recipient: str,
    amount: float,
    transfers_file: Optional[Path] = None,
) -> str:
    """
    Categorize fund transfers, handling masked recipients and 'ask once' workflow.

    Args:
        recipient: Target recipient name or account string (e.g. 'A*** K***').
        amount: Transaction amount.
        transfers_file: Optional path override for known_transfers.json (useful in tests).

    Returns:
        str: Category label (e.g. 'Roommate rent', or 'Transfers (uncategorized)').
    """
    recipient_clean = recipient.strip()

    # 1. If not masked, categorize normally via categorize_merchant
    if "*" not in recipient_clean:
        return categorize_merchant(recipient_clean)

    # 2. If masked, check known_transfers.json
    target_transfers_file = transfers_file or KNOWN_TRANSFERS_FILE
    transfers = _load_json(target_transfers_file)
    if not isinstance(transfers, dict):
        transfers = {}

    entry = transfers.get(recipient_clean)

    # If already confirmed with a label, return remembered label
    if entry and entry.get("status") == "confirmed" and entry.get("label"):
        entry["count"] = entry.get("count", 0) + 1
        _save_json(transfers, target_transfers_file)
        return entry["label"]

    # Increment counter or initialize
    if entry:
        count = entry.get("count", 0) + 1
    else:
        count = 1
        entry = {}

    entry["count"] = count
    if count >= 3:
        entry["status"] = "needs_input"
    else:
        entry["status"] = "pending"

    transfers[recipient_clean] = entry
    _save_json(transfers, target_transfers_file)

    return UNCATEGORIZED_TRANSFER_LABEL
