"""CLI helper to confirm the spending category label for a masked transfer recipient."""

import sys
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.tools.transfer_handler import confirm_transfer


def main():
    if len(sys.argv) < 3:
        print("Usage: python answer_transfer.py \"<masked_recipient>\" \"<label>\"")
        print("Example: python answer_transfer.py \"A*** K***\" \"Roommate rent\"")
        sys.exit(1)

    recipient = sys.argv[1].strip()
    label = sys.argv[2].strip()

    updated_txns = confirm_transfer(recipient, label)

    print(f"Successfully confirmed '{recipient}' -> '{label}'")
    print(f"Updated {updated_txns} past transactions in memory/transactions.json.")
    print("All future transactions for this recipient will automatically use this label.")


if __name__ == "__main__":
    main()
