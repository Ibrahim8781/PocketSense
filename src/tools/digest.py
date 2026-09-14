"""Digest generation and email delivery tool for PocketSense."""

import logging
import os
import smtplib
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from strands import tool

logger = logging.getLogger(__name__)

MEMORY_DIR = Path(__file__).resolve().parent.parent.parent / "memory"
LAST_DIGEST_FILE = MEMORY_DIR / "last_digest.html"


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


def _get_signed_amount(tx: Dict[str, Any]) -> float:
    """Get signed amount where refunds are negative."""
    amt = float(tx.get("amount", 0.0))
    if _is_refund(tx):
        return -abs(amt)
    return abs(amt)


@tool
def build_digest(
    transactions: List[Dict[str, Any]],
    anomalies: List[Dict[str, Any]],
    pending_transfers: Union[Dict[str, Any], List[Dict[str, Any]], List[str]],
) -> str:
    """
    Build a modern HTML weekly financial digest.

    Includes:
      - Total net spend summary
      - Category breakdown table with percentages
      - Anomaly alerts list
      - 'Please name these' section for needs_input masked transfers

    Args:
        transactions: List of transaction dictionaries.
        anomalies: List of anomaly dictionaries from detect_anomalies.
        pending_transfers: Dictionary or list of masked transfers requiring input.

    Returns:
        str: Rendered HTML string.
    """
    # 1. Compute spend metrics
    total_spend = 0.0
    category_totals = defaultdict(float)
    category_counts = defaultdict(int)

    for tx in transactions:
        amt = _get_signed_amount(tx)
        cat = tx.get("category") or "Uncategorized"
        total_spend += amt
        category_totals[cat] += amt
        category_counts[cat] += 1

    # Sort categories by total spend descending
    sorted_categories = sorted(
        category_totals.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    # 2. Parse needs_input transfers
    needs_input_items = []
    if isinstance(pending_transfers, dict):
        for recipient, info in pending_transfers.items():
            if isinstance(info, dict):
                status = info.get("status")
                count = info.get("count", 1)
                if status == "needs_input" or status == "pending":
                    needs_input_items.append({"recipient": recipient, "count": count})
            else:
                needs_input_items.append({"recipient": recipient, "count": 1})
    elif isinstance(pending_transfers, list):
        for item in pending_transfers:
            if isinstance(item, dict):
                needs_input_items.append({
                    "recipient": item.get("recipient") or item.get("merchant_or_recipient") or "Unknown",
                    "count": item.get("count", 1),
                })
            else:
                needs_input_items.append({"recipient": str(item), "count": 1})

    # 3. Render HTML Table rows
    table_rows = []
    for cat, spend in sorted_categories:
        pct = (spend / total_spend * 100.0) if total_spend > 0 else 0.0
        pct_width = min(100.0, max(0.0, pct))
        row_html = f"""
        <tr style="border-bottom: 1px solid #334155;">
          <td style="padding: 12px 16px; font-weight: 500; color: #f8fafc;">{cat}</td>
          <td style="padding: 12px 16px; text-align: right; font-weight: 600; color: #38bdf8;">Rs. {spend:,.2f}</td>
          <td style="padding: 12px 16px; text-align: right; color: #94a3b8; font-size: 13px;">{pct:.1f}%</td>
          <td style="padding: 12px 16px; width: 140px;">
            <div style="background: #1e293b; border-radius: 9999px; height: 8px; width: 100%; overflow: hidden; border: 1px solid #334155;">
              <div style="background: linear-gradient(90deg, #38bdf8, #818cf8); height: 100%; width: {pct_width:.1f}%; border-radius: 9999px;"></div>
            </div>
          </td>
        </tr>
        """
        table_rows.append(row_html)

    table_body = "\n".join(table_rows) if table_rows else "<tr><td colspan='4' style='padding: 16px; text-align: center; color: #94a3b8;'>No transactions recorded.</td></tr>"

    # 4. Render Anomalies
    anomaly_cards = []
    for a in anomalies:
        sev = str(a.get("severity", "medium")).upper()
        badge_bg = "#ef4444" if sev == "HIGH" else "#f59e0b"
        border_color = "#f43f5e" if sev == "HIGH" else "#fbbf24"
        card_html = f"""
        <div style="background: #0f172a; border-left: 4px solid {border_color}; border: 1px solid #334155; border-left-width: 4px; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-weight: 600; font-size: 14px; color: #f8fafc;">{a.get('type', 'Anomaly').replace('_', ' ').title()}</span>
            <span style="background: {badge_bg}; color: #ffffff; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 9999px; letter-spacing: 0.5px;">{sev}</span>
          </div>
          <p style="margin: 0; color: #cbd5e1; font-size: 13px; line-height: 1.5;">{a.get('description', '')}</p>
        </div>
        """
        anomaly_cards.append(card_html)

    if not anomaly_cards:
        anomalies_section = """
        <div style="background: #0f172a; border: 1px solid #059669; border-radius: 8px; padding: 14px 18px; color: #34d399; font-size: 13px; font-weight: 500;">
          All transactions are within expected baseline parameters. No anomalies detected!
        </div>
        """
    else:
        anomalies_section = "\n".join(anomaly_cards)

    # 5. Render 'Please name these' Section
    if needs_input_items:
        items_html = []
        for item in needs_input_items:
            rec = item["recipient"]
            cnt = item["count"]
            command_example = f'python answer_transfer.py "{rec}" "<Category Name>"'
            item_card = f"""
            <div style="background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 14px 18px; margin-bottom: 12px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-weight: 600; color: #fbbf24; font-size: 14px;">Masked Transfer: {rec}</span>
                <span style="background: #451a03; color: #fde68a; border: 1px solid #78350f; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 6px;">Seen {cnt}x</span>
              </div>
              <p style="margin: 0 0 8px 0; color: #94a3b8; font-size: 13px;">To categorize this recipient and update past/future transactions, run in terminal:</p>
              <div style="background: #020617; border: 1px solid #1e293b; border-radius: 6px; padding: 8px 12px; font-family: monospace; font-size: 12px; color: #38bdf8;">
                {command_example}
              </div>
            </div>
            """
            items_html.append(item_card)
        needs_input_section = "\n".join(items_html)
    else:
        needs_input_section = """
        <div style="background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 14px 18px; color: #94a3b8; font-size: 13px;">
          All transfer recipients are currently named and identified.
        </div>
        """

    current_date_str = datetime.now().strftime("%B %d, %Y")

    # Complete HTML Document
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>PocketSense Weekly Financial Digest</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 24px; background-color: #0b0f19; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc; line-height: 1.6;">
  <div style="max-width: 680px; margin: 0 auto; background-color: #111827; border-radius: 16px; border: 1px solid #1f2937; overflow: hidden; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);">
    
    <!-- Header -->
    <div style="padding: 28px 32px; background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%); border-bottom: 1px solid #334155;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
        <span style="font-size: 20px; font-weight: 800; letter-spacing: -0.5px; color: #ffffff;">Pocket<span style="color: #38bdf8;">Sense</span></span>
        <span style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 9999px;">WEEKLY DIGEST</span>
      </div>
      <h1 style="margin: 0 0 6px 0; font-size: 24px; font-weight: 700; color: #f8fafc;">Financial Summary & Anomaly Report</h1>
      <p style="margin: 0; color: #94a3b8; font-size: 13px;">Generated on {current_date_str}  Rolling 4-Week Intelligence</p>
    </div>

    <div style="padding: 28px 32px;">

      <!-- Key Metrics Overview -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px;">
        <div style="background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 18px 20px;">
          <div style="font-size: 12px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">Total Net Spend</div>
          <div style="font-size: 26px; font-weight: 800; color: #38bdf8; letter-spacing: -0.5px;">Rs. {total_spend:,.2f}</div>
          <div style="font-size: 12px; color: #64748b; margin-top: 4px;">Across {len(transactions)} transactions</div>
        </div>

        <div style="background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 18px 20px;">
          <div style="font-size: 12px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">Anomalies Flagged</div>
          <div style="font-size: 26px; font-weight: 800; color: {'#f43f5e' if anomalies else '#34d399'}; letter-spacing: -0.5px;">{len(anomalies)}</div>
          <div style="font-size: 12px; color: #64748b; margin-top: 4px;">{len(needs_input_items)} transfers need naming</div>
        </div>
      </div>

      <!-- Category Breakdown -->
      <div style="margin-bottom: 28px;">
        <h2 style="font-size: 16px; font-weight: 700; color: #f8fafc; margin: 0 0 14px 0; letter-spacing: -0.2px;">Category Spending Breakdown</h2>
        <div style="background: #1e293b; border: 1px solid #334155; border-radius: 12px; overflow: hidden;">
          <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 14px;">
            <thead>
              <tr style="background: #0f172a; border-bottom: 1px solid #334155; color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px;">
                <th style="padding: 12px 16px;">Category</th>
                <th style="padding: 12px 16px; text-align: right;">Amount</th>
                <th style="padding: 12px 16px; text-align: right;">Share</th>
                <th style="padding: 12px 16px;">Distribution</th>
              </tr>
            </thead>
            <tbody>
              {table_body}
            </tbody>
          </table>
        </div>
      </div>

      <!-- Anomaly Flags -->
      <div style="margin-bottom: 28px;">
        <h2 style="font-size: 16px; font-weight: 700; color: #f8fafc; margin: 0 0 14px 0; letter-spacing: -0.2px;">Detected Anomalies & Alerts</h2>
        <div style="background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 16px;">
          {anomalies_section}
        </div>
      </div>

      <!-- Please Name These Section -->
      <div style="margin-bottom: 12px;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px;">
          <h2 style="font-size: 16px; font-weight: 700; color: #f8fafc; margin: 0; letter-spacing: -0.2px;">Action Required: Name These Transfers</h2>
        </div>
        <div style="background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 16px;">
          {needs_input_section}
        </div>
      </div>

    </div>

    <!-- Footer -->
    <div style="padding: 20px 32px; background: #0f172a; border-top: 1px solid #1e293b; text-align: center; color: #64748b; font-size: 12px;">
      PocketSense Autonomous Financial Agent  Agents for Humans Hackathon 2026
    </div>

  </div>
</body>
</html>
"""
    return html_content


@tool
def send_digest(
    html_or_text: str,
    subject: str = "PocketSense: Weekly Spending Digest & Anomaly Report",
    artifact_path: Optional[Path] = None,
) -> bool:
    """
    Send the weekly digest email using Gmail SMTP and always save a copy to /memory/last_digest.html.

    Args:
        html_or_text: The HTML or plain text content of the digest.
        subject: The email subject line.
        artifact_path: Path override for local HTML artifact (defaults to memory/last_digest.html).

    Returns:
        bool: True if SMTP email sent successfully, False otherwise (artifact is still saved).
    """
    # 1. ALWAYS save a copy to /memory/last_digest.html first
    save_path = artifact_path or LAST_DIGEST_FILE
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(html_or_text)
        logger.info("Saved local digest artifact to %s", save_path)
    except OSError as e:
        logger.error("Failed saving local digest artifact to %s: %s", save_path, e)

    # 2. Read credentials from .env
    load_dotenv()
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_password:
        logger.warning(
            "GMAIL_ADDRESS or GMAIL_APP_PASSWORD not configured. "
            "Skipped SMTP sending; local artifact saved to %s.",
            save_path,
        )
        return False

    # 3. Attempt Gmail SMTP delivery
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = gmail_address
        msg["To"] = gmail_address  # Self-email for demo

        msg.attach(MIMEText(html_or_text, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.starttls()
            server.login(gmail_address, gmail_password)
            server.send_message(msg)

        logger.info("Successfully sent weekly digest email to %s", gmail_address)
        return True

    except Exception as e:
        logger.warning(
            "Gmail SMTP sending failed (%s: %s). "
            "Local artifact remains available at %s.",
            type(e).__name__,
            e,
            save_path,
        )
        return False
