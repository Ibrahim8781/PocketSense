# PocketSense 

> **Autonomous Financial Intelligence Agent** built with the **Strands Agents SDK** for the *Agents for Humans* Hackathon (*Everyday Agents* Track).

PocketSense is a silent, privacy-first financial intelligence agent designed to monitor bank transaction alerts, normalize messy multi-currency data, classify spending using Amazon Bedrock, intelligently learn masked fund transfer counterparties, flag statistical spending anomalies, and deliver executive-grade weekly digests.

---

## Table of Contents
- [What PocketSense Does](#what-pocketsense-does)
- [Who It's For](#who-its-for)
- [How It Works (The 4-Stage Pipeline)](#how-it-works-the-4-stage-pipeline)
- [The 4 Limitations (From Original Pitch)](#the-4-limitations-from-original-pitch)
- [Future Work & Iterations](#future-work--iterations)
- [Setup & Run Instructions](#setup--run-instructions)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [License](#license)

---

## What PocketSense Does

Traditional personal finance apps require tedious manual expense tracking or demand full bank credential access via Plaid—services that simply do not work with emerging-market banks.

PocketSense operates as an **autonomous background agent**:
1. **Mock Inbox Ingestion**: Ingests incoming bank alert notification text files without requiring intrusive live Gmail access.
2. **Unified Currency Parsing**: Automatically parses dates, transaction types, and amounts, normalizing disparate notations (`Rs. 1,250.00`, `PKR 1250`, `₨ 5,000`).
3. **LLM-Powered Merchant Categorization**: Classifies merchants into standard spending buckets using **Amazon Bedrock (Claude Sonnet 4.6)** with persistent local memory caching to prevent redundant API calls.
4. **"Ask-Once" Masked Transfer Workflow**: Handles bank-masked transfer recipients (e.g., `A*** K*** (Acc ****4821)`). It leaves them uncategorized until observed $\ge 3$ times, flags them as `needs_input`, prompts the user in the weekly digest, and allows naming via a quick CLI tool (`answer_transfer.py`) that back-propagates across both past records and future transactions.
5. **4-Rule Anomaly Audit Engine**: Detects spending surges, duplicate POS charges (with coffee shop same-day exemptions), unusually large single charges ($3\times$ baseline), and end-of-month run-rate projections ($>1.2\times$ baseline) while properly netting refunds and reversals.
6. **Executive Weekly Digest**: Generates an interactive dark-slate HTML dashboard saved to `memory/last_digest.html` and dispatched via Gmail SMTP.

---

## Who It's For

- **Everyday Consumers in Emerging & Cashless Markets**: Particularly in South Asia (Pakistan, India, Bangladesh) and regions where open banking APIs do not exist and bank alerts arrive via SMS or email.
- **People Who Transfer Frequently to Friends & Family**: Users who split rent, bills, or groceries via bank transfers where bank privacy filters mask recipient identities (`A*** K***`).
- **Privacy-Conscious Individuals**: Anyone unwilling to hand over live bank login credentials or grant third-party SaaS tools unrestricted read/write access to their personal Gmail accounts.

---

## How It Works (The 4-Stage Pipeline)

<p align="center">
  <img src="assets/PocketSense-Architecture.png" alt="PocketSense Architecture Diagram" width="850"/>
</p>

```
[Raw Bank Alerts] ──> [1. Parser] ──> [2. Categorization & Memory] ──> [3. Anomaly Engine] ──> [4. Executive Digest]
  (/mock_inbox)       (parse_email)   (categorizer / transfer_handler)   (detect_anomalies)     (build_digest & SMTP)
```

1. **Stage 1: Ingestion & Parsing (`parse_email`)**
   - Scans `/mock_inbox` for raw bank notification `.txt` files.
   - Parses RFC 2822 date headers, transaction types (`card_txn` vs `transfer`), normalized numeric amounts, and recipient masking status (`*` detection).
2. **Stage 2: Categorization & State (`categorize_merchant` & `handle_transfer`)**
   - **Card Transactions**: Checks `memory/merchant_categories.json` for an exact case-insensitive match. On cache miss, queries Bedrock once, normalizes the response, and writes to cache.
   - **Fund Transfers**: If unmasked, categorizes normally. If masked, checks `memory/known_transfers.json`. Unnamed transfers remain labeled `"Transfers (uncategorized)"` and increment a frequency counter. Reaching $\ge 3$ marks the recipient as `needs_input`.
   - Appends all structured records to `memory/transactions.json`.
3. **Stage 3: Statistical Anomaly Detection (`detect_anomalies`)**
   - **Check 1 (Category Surge)**: Flags category spend in the current 7 days exceeding $2\times$ the rolling 4-week trailing average.
   - **Check 2 (Duplicate Charge)**: Flags identical amounts at the same merchant within 30 minutes; exempts legitimate repeat-visit merchants (e.g. coffee shops with distinct same-day timestamps).
   - **Check 3 (Single Spike)**: Flags transactions exceeding $3\times$ the historical average for that merchant or category.
   - **Check 4 (End-of-Month Overspend)**: Projects monthly run-rate against the average of the last 2 full calendar months, alerting if projected spend exceeds $1.2\times$ baseline. Nets refunds and reversals against category totals.
4. **Stage 4: Executive Digest & Alerts (`build_digest` & `send_digest`)**
   - Renders a responsive, dark-slate HTML dashboard with KPI summary cards, category distribution bars, severity-badged anomaly alerts, and a terminal command prompt for naming pending transfers.
   - Always preserves an offline copy in `memory/last_digest.html` for screen presentations and attempts Gmail SMTP dispatch.

---

## The 4 Limitations (From Original Pitch)

1. **Email-Dependent Ingestion**: The agent relies on bank notification text format rather than real-time direct banking webhooks. Delayed or dropped bank emails directly impact real-time tracking.
2. **Masked Counterparty Data**: Bank privacy masking (`A*** K***` or `Acc ****9102`) prevents instant counterparty identification. PocketSense resolves this via an "ask-once" threshold rather than guessing.
3. **Cold-Start Window**: The rolling 4-week average and 2-month baseline projections require initial transaction history before anomaly detection reaches full statistical reliability.
4. **One-Bank-Format Parser (Demo Scope)**: The current regular expression parser is calibrated for standard Pakistani bank notification structures (e.g., HBL debit card purchases and fund transfers).

---

## Future Work & Iterations

- **Direct SMS Ingestion via Android Gateway**: Integrate with an on-device local SMS relay (e.g. Termux or SMS webhook) to ingest bank SMS alerts in real time without email reliance.
- **LLM-Assisted Universal Parser**: Fall back to Bedrock Claude Sonnet with structured JSON outputs for previously unseen bank alert templates, removing regex rigidity.
- **Two-Way WhatsApp / Telegram Sidecar**: Allow users to answer `needs_input` transfer prompts by replying with a simple text (e.g. *"A*** K*** is Roommate rent"*) rather than running the CLI script.
- **Budget Goal Enforcement**: Proactive mid-week nudges when discretionary spending categories approach user-defined weekly caps.

---

## Setup & Run Instructions

### Prerequisites
- Python 3.10 or higher
- An active AWS Account with Amazon Bedrock access in `us-east-1`
- (Optional) A Gmail account with an App Password for email delivery

### 1. Clone & Setup Virtual Environment
```bash
# Navigate to project directory
cd pocketsense

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables (`.env`)
Create or edit `.env` in the repository root:
```ini
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6

# Optional for live Gmail delivery (digest is always saved to memory/last_digest.html)
GMAIL_ADDRESS=your_email@gmail.com
GMAIL_APP_PASSWORD=your_16_character_app_password
```

> **Note on Bedrock Model ID**: In Amazon Bedrock, Claude models require regional inference profiles (e.g. `us.anthropic.claude-sonnet-4-6` or `us.anthropic.claude-3-5-sonnet-20241022-v2:0`).

### 4. Run PocketSense Pipeline
```bash
python src/main.py
```

### 5. Answering a Masked Transfer
When the weekly digest or console identifies a recurring masked transfer needing input, confirm its category:
```bash
python answer_transfer.py "A*** K*** (Acc ****4821)" "Roommate rent"
```
This updates `memory/known_transfers.json` to `confirmed` and automatically updates all past and future records.

### 6. View the Presentation Artifact
Open `memory/last_digest.html` in any web browser to view the rendered weekly financial dashboard.

---

## Project Structure

```
pocketsense/
│
├── .env                              # Environment variables (AWS & Gmail keys)
├── ARCHITECTURE.md                   # System architecture & Mermaid sequence diagram
├── LICENSE                           # MIT License (2026 Ibrahim)
├── README.md                         # Project documentation
├── answer_transfer.py                # CLI helper to name masked transfer counterparties
│
├── memory/                           # Persistent JSON memory store (No database)
│   ├── known_transfers.json          # Remembers masked transfer labels & counters
│   ├── merchant_categories.json      # Cache of merchant -> spending categories
│   ├── transactions.json             # Complete historical transaction store
│   └── last_digest.html              # Generated HTML weekly dashboard artifact
│
├── mock_inbox/                       # Plain .txt bank notification emails (20 sample files)
│   ├── email_001.txt
│   └── ...
│
├── src/
│   ├── agent.py                      # Strands Agent initialization with BedrockModel
│   ├── main.py                       # End-to-end background orchestration pipeline
│   └── tools/
│       ├── anomaly_detector.py       # 4-rule statistical anomaly engine
│       ├── categorizer.py            # Bedrock LLM classifier with cache
│       ├── digest.py                 # HTML digest builder & Gmail SMTP sender
│       ├── parser.py                 # Currency normalizer & email parser tool
│       └── transfer_handler.py       # Transfer router & "ask once" counter logic
│
└── tests/                            # 20 comprehensive unit tests
    ├── test_anomaly_detector.py      # Tests for all 4 anomaly rules & refund netting
    ├── test_categorizer.py           # Tests for caching, agent routing & fallback
    ├── test_digest.py                # Tests for HTML formatting & SMTP fallback
    ├── test_parser.py                # Tests for currency normalization edge cases
    └── test_transfer_handler.py      # Tests for masked counter thresholds & CLI helper
```

---

## Testing

Run the full automated test suite (20 tests, stdlib `unittest`):
```bash
python -m unittest discover tests
```

---

## License

This project is licensed under the [MIT License](LICENSE) — see the [LICENSE](LICENSE) file for details. Copyright (c) 2026 Ibrahim.
