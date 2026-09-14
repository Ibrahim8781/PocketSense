"""Email parser tool for PocketSense."""

import email
import email.utils
import re
from datetime import datetime
from typing import Any, Dict, Optional

from strands import tool

CURRENCY_REGEX = r"(?:Rs\.?|PKR|₨\.?)"


def _parse_date_header(text: str) -> Optional[str]:
    """Extract and parse date from email headers into ISO format."""
    msg = email.message_from_string(text)
    date_hdr = msg.get("Date")
    if not date_hdr:
        match = re.search(r"^Date:\s*(.+)$", text, re.MULTILINE | re.IGNORECASE)
        if match:
            date_hdr = match.group(1).strip()

    if not date_hdr:
        return None

    try:
        dt = email.utils.parsedate_to_datetime(date_hdr)
        return dt.isoformat()
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%b-%Y %H:%M:%S"):
            try:
                return datetime.strptime(date_hdr.strip(), fmt).isoformat()
            except ValueError:
                pass
        return date_hdr.strip()


def _normalize_amount(val_str: str) -> float:
    """Normalize numeric string with optional commas and decimals into float."""
    clean = val_str.replace(",", "").strip()
    return float(clean)


@tool
def parse_email(text: str) -> Dict[str, Any]:
    """
    Parse a raw bank alert email into structured transaction data.

    Args:
        text: Raw text of the email including headers and body.

    Returns:
        dict:
            type: 'card_txn' or 'transfer'
            amount: float (normalized)
            merchant_or_recipient: string
            is_masked: bool (True if recipient contains asterisks)
            date: string (parsed ISO date or header date string)
            raw_text: string (original raw email text)
    """
    date_val = _parse_date_header(text)

    # 1. Fund transfers: "You sent [currency] [amount] to [recipient]"
    transfer_pattern = (
        r"(?:sent|transferred)\s+"
        + CURRENCY_REGEX
        + r"?\s*([\d,]+(?:\.\d+)?)\s*"
        + CURRENCY_REGEX
        + r"?\s+to\s+([^\n\r]+?)(?:\s+via|\s+using|\s+from|\s+on\s+\d|\.\s|\.$|\n|$)"
    )
    transfer_match = re.search(transfer_pattern, text, re.IGNORECASE)

    # 2. Card transactions: "You spent [currency] [amount] at [merchant]"
    card_pattern = (
        r"(?:spent|paid|purchased?)\s+"
        + CURRENCY_REGEX
        + r"?\s*([\d,]+(?:\.\d+)?)\s*"
        + CURRENCY_REGEX
        + r"?\s+at\s+([^\n\r]+?)(?:\s+on\s+your|\s+using|\s+via|\s+on\s+\d|\.\s|\.$|\n|$)"
    )
    card_match = re.search(card_pattern, text, re.IGNORECASE)

    # 3. Refund/reversal patterns
    refund_pattern = (
        r"(?:refund|reversal)\s+(?:of\s+)?"
        + CURRENCY_REGEX
        + r"?\s*([\d,]+(?:\.\d+)?)\s*"
        + CURRENCY_REGEX
        + r"?\s+from\s+([^\n\r]+?)(?:\s+has\s+been|\s+on\s+your|\s+using|\s+via|\s+on\s+\d|\.\s|\.$|\n|$)"
    )
    refund_match = re.search(refund_pattern, text, re.IGNORECASE)

    if transfer_match:
        txn_type = "transfer"
        raw_amt = transfer_match.group(1)
        target = transfer_match.group(2).strip().rstrip(".")
    elif card_match:
        txn_type = "card_txn"
        raw_amt = card_match.group(1)
        target = card_match.group(2).strip().rstrip(".")
    elif refund_match:
        txn_type = "card_txn"
        raw_amt = refund_match.group(1)
        target = refund_match.group(2).strip().rstrip(".")
    else:
        if re.search(r"\b(?:transfer|sent)\b", text, re.IGNORECASE):
            txn_type = "transfer"
        else:
            txn_type = "card_txn"

        amt_match = re.search(CURRENCY_REGEX + r"\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
        if not amt_match:
            amt_match = re.search(r"([\d,]+(?:\.\d+)?)\s*" + CURRENCY_REGEX, text, re.IGNORECASE)

        raw_amt = amt_match.group(1) if amt_match else "0"
        target = "Unknown"

    amount = _normalize_amount(raw_amt)
    is_masked = bool("*" in target)

    return {
        "type": txn_type,
        "amount": amount,
        "merchant_or_recipient": target,
        "is_masked": is_masked,
        "date": date_val,
        "raw_text": text,
    }
