"""PocketSense main orchestration pipeline.

Executes the silent background agent workflow:
  1. Ingests mock bank alert emails from /mock_inbox.
  2. Parses email bodies with parse_email tool.
  3. Categorizes card purchases via categorize_merchant and transfers via handle_transfer.
  4. Appends structured records to memory/transactions.json.
  5. Runs detect_anomalies across historical transactions.
  6. Builds and dispatches the weekly HTML digest via send_digest.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.anomaly_detector import detect_anomalies
from src.tools.categorizer import categorize_merchant
from src.tools.digest import build_digest, send_digest
from src.tools.parser import parse_email
from src.tools.transfer_handler import handle_transfer

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger("pocketsense")

INBOX_DIR = PROJECT_ROOT / "mock_inbox"
MEMORY_DIR = PROJECT_ROOT / "memory"
TRANSACTIONS_FILE = MEMORY_DIR / "transactions.json"
KNOWN_TRANSFERS_FILE = MEMORY_DIR / "known_transfers.json"
LAST_DIGEST_FILE = MEMORY_DIR / "last_digest.html"


def load_json_file(path: Path, default_val: Any) -> Any:
    """Safely load JSON data from disk."""
    if not path.exists():
        return default_val
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return default_val
            return json.loads(content)
    except (json.JSONDecodeError, OSError):
        return default_val


def save_json_file(data: Any, path: Path) -> None:
    """Save formatted JSON data to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def run_pipeline() -> None:
    """Execute the end-to-end background ingestion and analysis pipeline."""
    print("\n" + "=" * 70)
    print(" PocketSense: Autonomous Financial Intelligence Agent")
    print(" Track: Everyday Agents | Hackathon 2026")
    print("=" * 70)

    # 1. Read files in mock_inbox
    email_files = sorted(INBOX_DIR.glob("*.txt"))
    if not email_files:
        print(f"[-] No email files found in {INBOX_DIR}.")
        print("    Please run mock email generation or add notification .txt files.")
        return

    print(f"\n[1/5] Ingesting {len(email_files)} bank notifications from /mock_inbox...")

    # Load existing transaction history
    existing_txns: List[Dict[str, Any]] = load_json_file(TRANSACTIONS_FILE, [])
    seen_sources = {tx.get("source_file") for tx in existing_txns if tx.get("source_file")}

    new_txns: List[Dict[str, Any]] = []

    for idx, file_path in enumerate(email_files, start=1):
        with open(file_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        # 2. Parse email
        parsed = parse_email(raw_text)
        txn_type = parsed.get("type", "card_txn")
        target = parsed.get("merchant_or_recipient", "Unknown")
        amt = parsed.get("amount", 0.0)

        # 3. Route to categorizer or transfer handler
        if txn_type == "transfer":
            category = handle_transfer(target, amt)
        else:
            category = categorize_merchant(target)

        record = {
            "id": len(existing_txns) + len(new_txns) + 1,
            "date": parsed.get("date"),
            "type": txn_type,
            "amount": amt,
            "merchant_or_recipient": target,
            "category": category,
            "is_masked": parsed.get("is_masked", False),
            "is_refund": parsed.get("is_refund", False),
            "source_file": file_path.name,
        }

        # Avoid duplicating on re-runs
        if file_path.name not in seen_sources:
            new_txns.append(record)

        type_badge = "TRANSFER" if txn_type == "transfer" else ("REFUND  " if parsed.get("is_refund") else "CARD    ")
        masked_flag = " [MASKED]" if parsed.get("is_masked") else ""
        print(
            f"   [{idx:02d}/{len(email_files):02d}] {file_path.name:<13} | {type_badge} | "
            f"Rs. {amt:>10,.2f} | {category:<22} | {target}{masked_flag}"
        )

    # 4. Save updated transactions to memory/transactions.json
    all_txns = existing_txns + new_txns
    save_json_file(all_txns, TRANSACTIONS_FILE)
    print(f"\n[2/5] Transaction database updated in /memory/transactions.json.")
    print(f"      Total records: {len(all_txns)} ({len(new_txns)} newly ingested).")

    # 5. Run anomaly detection over complete transaction history
    print("\n[3/5] Running anomaly audit algorithms across transaction history...")
    anomalies = detect_anomalies(all_txns)
    if anomalies:
        print(f"      [!] Flagged {len(anomalies)} spending anomalies:")
        for a in anomalies:
            sev = a.get("severity", "MEDIUM").upper()
            print(f"          - [{sev}] {a.get('type')}: {a.get('description')}")
    else:
        print("      [+] All transactions conform to baseline spending rules. No anomalies flagged.")

    # Check for pending transfers needing identification
    known_transfers: Dict[str, Any] = load_json_file(KNOWN_TRANSFERS_FILE, {})
    needs_input_items = {
        k: v for k, v in known_transfers.items()
        if isinstance(v, dict) and v.get("status") in ("needs_input", "pending")
    }

    if needs_input_items:
        print(f"\n[4/5] Pending User Identification:")
        for rec, info in needs_input_items.items():
            cnt = info.get("count", 1)
            status = info.get("status", "pending")
            print(f"      - {rec} (seen {cnt} times, status: {status})")
            print(f"        Action: Run `python answer_transfer.py \"{rec}\" \"<Category Name>\"`")
    else:
        print(f"\n[4/5] All transfer recipients are confirmed.")

    # 6. Build and dispatch digest
    print("\n[5/5] Building weekly executive digest...")
    html_digest = build_digest(all_txns, anomalies, known_transfers)

    # Dispatch email / save local artifact
    sent = send_digest(html_digest, subject="PocketSense: Weekly Spending Digest & Anomaly Report")

    print("\n" + "=" * 70)
    print(" PocketSense Pipeline Run Summary")
    print("=" * 70)
    print(f" Total Ingested Transactions : {len(all_txns)}")
    print(f" Anomalies Flagged           : {len(anomalies)}")
    print(f" Transfers Needing Naming    : {len(needs_input_items)}")
    print(f" Offline Presentation HTML   : {LAST_DIGEST_FILE}")
    if sent:
        print(" SMTP Notification           : Delivered successfully to Gmail.")
    else:
        print(" SMTP Notification           : Offline mode / Saved locally to last_digest.html.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    run_pipeline()
