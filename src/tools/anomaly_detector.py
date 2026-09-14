"""Anomaly detector tool for PocketSense."""

import calendar
import email.utils
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from strands import tool

logger = logging.getLogger(__name__)

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "memory"
TRANSACTIONS_FILE = MEMORY_DIR / "transactions.json"

REPEAT_VISIT_KEYWORDS = {
    "coffee",
    "coffees",
    "cafe",
    "café",
    "espresso",
    "tea",
    "bakery",
    "donuts",
    "doughnuts",
}


def _parse_dt(val: Any) -> Optional[datetime]:
    """Parse various datetime string formats into UTC-naive datetime."""
    if isinstance(val, datetime):
        dt = val
    elif not val:
        return None
    else:
        val_str = str(val).strip()
        dt = None
        try:
            dt = email.utils.parsedate_to_datetime(val_str)
        except Exception:
            pass
        if not dt:
            try:
                dt = datetime.fromisoformat(val_str)
            except Exception:
                pass
        if not dt:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%b-%Y %H:%M:%S"):
                try:
                    dt = datetime.strptime(val_str, fmt)
                    break
                except ValueError:
                    pass

    if dt is not None and dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _is_refund(tx: Dict[str, Any]) -> bool:
    """Check if transaction is a refund or reversal."""
    if tx.get("is_refund") is True:
        return True
    tx_type = str(tx.get("type", "")).lower()
    if tx_type in ("refund", "reversal"):
        return True
    amt = tx.get("amount", 0.0)
    if isinstance(amt, (int, float)) and amt < 0:
        return True
    return False


def _get_effective_amount(tx: Dict[str, Any]) -> float:
    """Get signed amount where refunds are negative."""
    amt = float(tx.get("amount", 0.0))
    if _is_refund(tx):
        return -abs(amt)
    return abs(amt)


def _is_repeat_visit_merchant(merchant: str, category: str = "") -> bool:
    """Check if merchant is a type where multiple same-day visits are normal (e.g. coffee shops)."""
    m_lower = merchant.lower()
    c_lower = category.lower()
    for kw in REPEAT_VISIT_KEYWORDS:
        if kw in m_lower or kw in c_lower:
            return True
    return False


def _load_history(file_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load transaction history from JSON file."""
    path = file_path or TRANSACTIONS_FILE
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            data = json.loads(content)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read transaction history from %s: %s", path, e)
        return []


@tool
def detect_anomalies(
    transactions: Optional[List[Dict[str, Any]]] = None,
    history_file: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Detect financial anomalies across 4 checks:
      1. Category spend vs rolling 4-week average (flag if current week >= 2x).
      2. Duplicate charges (same merchant + same amount within 30 min, excluding normal repeat visits).
      3. Unusually large single transaction (flag if >= 3x historical average for merchant/category).
      4. End-of-month projected overspend (flag if projected month spend > 1.2x 2-month baseline).

    Args:
        transactions: List of transaction dicts to analyze. If None, reads from memory/transactions.json.
        history_file: Path override for transaction history file (useful in testing).

    Returns:
        list[dict]: Anomaly items with type, description, and severity.
    """
    history = _load_history(history_file)

    if transactions is None:
        all_txns = list(history)
    else:
        # Combine provided transactions with history if not already present
        all_txns = list(transactions)
        seen_reprs = {json.dumps(t, sort_keys=True, default=str) for t in all_txns}
        for h in history:
            h_repr = json.dumps(h, sort_keys=True, default=str)
            if h_repr not in seen_reprs:
                all_txns.append(h)

    if not all_txns:
        return []

    # Sort all valid transactions by date
    parsed_txns = []
    for tx in all_txns:
        dt = _parse_dt(tx.get("date"))
        if dt:
            parsed_txns.append((dt, tx))

    if not parsed_txns:
        return []

    parsed_txns.sort(key=lambda x: x[0])
    anomalies: List[Dict[str, Any]] = []

    # Reference point: max transaction date
    ref_date = parsed_txns[-1][0]

    # -------------------------------------------------------------
    # Check 1: Category spend vs rolling 4-week average (>= 2x)
    # -------------------------------------------------------------
    week_cutoff = ref_date - timedelta(days=7)
    trailing_4w_cutoff = ref_date - timedelta(days=35)

    curr_week_by_cat = defaultdict(float)
    trailing_by_cat = defaultdict(float)

    for dt, tx in parsed_txns:
        cat = tx.get("category") or "Uncategorized"
        net_amt = _get_effective_amount(tx)

        if week_cutoff < dt <= ref_date:
            curr_week_by_cat[cat] += net_amt
        elif trailing_4w_cutoff < dt <= week_cutoff:
            trailing_by_cat[cat] += net_amt

    for cat, curr_spend in curr_week_by_cat.items():
        trailing_spend = trailing_by_cat[cat]
        rolling_avg = trailing_spend / 4.0
        if rolling_avg > 0 and curr_spend >= 2.0 * rolling_avg:
            anomalies.append({
                "type": "category_overspend",
                "severity": "medium",
                "description": (
                    f"Category '{cat}' spend this week (Rs. {curr_spend:,.2f}) is "
                    f"{curr_spend / rolling_avg:.1f}x the trailing 4-week average (Rs. {rolling_avg:,.2f})."
                ),
            })

    # -------------------------------------------------------------
    # Check 2: Duplicate charges (same merchant + amount <= 30 min)
    # -------------------------------------------------------------
    # Only compare non-refund charges
    non_refund_txns = [(dt, tx) for dt, tx in parsed_txns if not _is_refund(tx)]
    seen_duplicate_pairs = set()

    for i in range(len(non_refund_txns)):
        dt1, tx1 = non_refund_txns[i]
        m1 = (tx1.get("merchant_or_recipient") or tx1.get("merchant") or "").strip().lower()
        amt1 = float(tx1.get("amount", 0.0))
        cat1 = tx1.get("category", "")

        for j in range(i + 1, len(non_refund_txns)):
            dt2, tx2 = non_refund_txns[j]
            time_diff = (dt2 - dt1).total_seconds()

            if time_diff > 1800:
                break  # Sorted by date, past 30 min window

            m2 = (tx2.get("merchant_or_recipient") or tx2.get("merchant") or "").strip().lower()
            amt2 = float(tx2.get("amount", 0.0))

            if m1 == m2 and abs(amt1 - amt2) < 0.01:
                # Check repeat-visit exemption (e.g. coffee shops with different timestamps on same day)
                is_coffee_or_repeat = _is_repeat_visit_merchant(m1, cat1)
                same_day = dt1.date() == dt2.date()
                different_timestamps = time_diff > 0

                if is_coffee_or_repeat and same_day and different_timestamps:
                    continue  # Normal repeat visit, do not flag

                pair_key = (min(id(tx1), id(tx2)), max(id(tx1), id(tx2)))
                if pair_key not in seen_duplicate_pairs:
                    seen_duplicate_pairs.add(pair_key)
                    display_merchant = tx2.get("merchant_or_recipient") or tx2.get("merchant") or m2
                    anomalies.append({
                        "type": "duplicate_charge",
                        "severity": "high",
                        "description": (
                            f"Possible duplicate charge: Rs. {amt1:,.2f} at '{display_merchant}' "
                            f"within {time_diff / 60:.1f} minutes of previous charge."
                        ),
                    })

    # -------------------------------------------------------------
    # Check 3: Unusually large single transaction (>= 3x historical avg)
    # -------------------------------------------------------------
    for dt, tx in non_refund_txns:
        m = (tx.get("merchant_or_recipient") or tx.get("merchant") or "").strip().lower()
        cat = (tx.get("category") or "").strip().lower()
        amt = float(tx.get("amount", 0.0))
        display_m = tx.get("merchant_or_recipient") or tx.get("merchant") or m

        # Compare against historical transactions excluding current transaction
        m_history = [
            float(t.get("amount", 0.0))
            for _, t in non_refund_txns
            if t is not tx
            and (t.get("merchant_or_recipient") or t.get("merchant") or "").strip().lower() == m
        ]
        c_history = [
            float(t.get("amount", 0.0))
            for _, t in non_refund_txns
            if t is not tx
            and (t.get("category") or "").strip().lower() == cat
        ]

        baseline_avg = None
        baseline_name = None

        if len(m_history) >= 2:
            baseline_avg = sum(m_history) / len(m_history)
            baseline_name = f"merchant '{display_m}'"
        elif len(c_history) >= 2:
            baseline_avg = sum(c_history) / len(c_history)
            baseline_name = f"category '{tx.get('category')}'"

        if baseline_avg and baseline_avg > 0 and amt >= 3.0 * baseline_avg:
            anomalies.append({
                "type": "unusually_large_transaction",
                "severity": "high",
                "description": (
                    f"Unusually large transaction: Rs. {amt:,.2f} at '{display_m}' is "
                    f"{amt / baseline_avg:.1f}x the historical average for {baseline_name} (Rs. {baseline_avg:,.2f})."
                ),
            })

    # -------------------------------------------------------------
    # Check 4: End-of-month projected overspend (> 1.2x 2-month baseline)
    # -------------------------------------------------------------
    curr_year = ref_date.year
    curr_month = ref_date.month
    days_in_month = calendar.monthrange(curr_year, curr_month)[1]
    days_elapsed = max(1, ref_date.day)

    # Net spend in current month (netting refunds)
    curr_month_spend = 0.0

    # Historical months: Month -1 and Month -2
    prev_month_1 = (curr_year, curr_month - 1) if curr_month > 1 else (curr_year - 1, 12)
    prev_month_2 = (prev_month_1[0], prev_month_1[1] - 1) if prev_month_1[1] > 1 else (prev_month_1[0] - 1, 12)

    spend_by_month = defaultdict(float)

    for dt, tx in parsed_txns:
        ym = (dt.year, dt.month)
        spend_by_month[ym] += _get_effective_amount(tx)

    curr_month_spend = spend_by_month.get((curr_year, curr_month), 0.0)
    prev_1_spend = spend_by_month.get(prev_month_1, 0.0)
    prev_2_spend = spend_by_month.get(prev_month_2, 0.0)

    historical_months = [s for s in (prev_1_spend, prev_2_spend) if s > 0]
    if historical_months:
        baseline_monthly = sum(historical_months) / len(historical_months)
        projected_spend = (curr_month_spend / days_elapsed) * days_in_month

        if baseline_monthly > 0 and projected_spend > 1.2 * baseline_monthly:
            anomalies.append({
                "type": "projected_overspend",
                "severity": "medium",
                "description": (
                    f"Projected end-of-month spend (Rs. {projected_spend:,.2f}) is "
                    f"{projected_spend / baseline_monthly:.1f}x the historical monthly average (Rs. {baseline_monthly:,.2f})."
                ),
            })

    return anomalies
