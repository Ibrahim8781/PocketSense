"""Reset PocketSense demo memory to initial state for a fresh live demo run."""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MEMORY_DIR = BASE_DIR / "memory"


def reset_demo(clear_merchant_cache: bool = True):
    """Reset JSON memory stores to pristine demo starting state."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Reset transactions.json to empty list
    (MEMORY_DIR / "transactions.json").write_text("[]\n", encoding="utf-8")

    # 2. Reset known_transfers.json to empty dict
    (MEMORY_DIR / "known_transfers.json").write_text("{}\n", encoding="utf-8")

    # 3. Reset merchant_categories.json
    if clear_merchant_cache:
        (MEMORY_DIR / "merchant_categories.json").write_text("{}\n", encoding="utf-8")

    print("\n" + "=" * 60)
    print(" PocketSense Demo State Reset Complete!")
    print("=" * 60)
    print(" - memory/transactions.json     -> []")
    print(" - memory/known_transfers.json  -> {}")
    if clear_merchant_cache:
        print(" - memory/merchant_categories.json -> {} (Ready for live Bedrock calls)")
    print("\nSuggested 3-Step Demo Script for Hackathon Presentation:")
    print("  1. Run the background pipeline:")
    print("       python src/main.py")
    print("  2. Show the 'Ask-Once' workflow in action:")
    print("       python answer_transfer.py \"A*** K*** (Acc ****4821)\" \"Roommate rent\"")
    print("  3. Open the executive digest in your browser:")
    print("       memory/last_digest.html")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    reset_demo()
