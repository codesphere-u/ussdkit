# ussdkit

**Stateful USSD & GSM session emulator, 3GPP TS 23.038 GSM-7/UCS-2 byte-budget guard, automated menu-tree crawler, and telco chaos testing suite.**

Zero runtime dependencies. Pure Python 3.11+. Built for fintech, mobile-money, agritech, health, and civic-tech engineers shipping `*123#` services across Africa, South Asia, and global GSM networks.

## Why `ussdkit` Exists

Millions of people rely on USSD (`*165#`, `*185#`, `*384#`) on feature phones and 2G/3G links where apps cannot reach. Yet USSD teams still test production menus manually on handsets or fragile curl scripts, leading to silent production failures:

- **The UCS-2 Truncation Cliff:** A single curly apostrophe (`’`), em-dash (`—`), or emoji switches a telco gateway from **GSM-7 (182/160 septets)** to **UCS-2 (80/70 UTF-16 units)**, silently chopping off menu options.
- **Non-Idempotent Telco Retries:** 2G/3G aggregators frequently retry identical webhook callbacks—causing duplicate mobile-money debits if handlers are not idempotent per `(sessionId, text)`.
- **Dead-End Screens & 180-Second Drop-offs:** Missing `CON`/`END` prefixes, overly deep menus, and unhandled malformed replies crash live sessions.

## Features

- **Exact 3GPP TS 23.038 Encoding Guard:** Accounts for GSM-7 basic chars (1 septet), extension table chars (`€`, `[`, `]`, `{`, `}`, `^`, `~`, `\`, `|` = 2 septets), and UCS-2 surrogate pairs, with automatic GSM-7 sanitization suggestions.
- **Multi-Gateway Codecs:** Africa's Talking, Hubtel, Infobip, and Generic JSON/text protocols.
- **In-Process & Live HTTP Emulation:** Test Python callables directly in `pytest` or hit staging webhooks over HTTP/HTTPS with `*384*1*2#` fast-path dialing and deterministic 180s telco session timeout simulation.
- **Automated BFS Menu-Tree Crawler:** Discovers reachable menus and flags overflows (`USSD-001`), hidden UCS-2 triggers (`USSD-002`), protocol violations (`USSD-003`), empty screens (`USSD-004`), excessive depth (`USSD-005`), cycles (`USSD-006`), and ambiguous dead-ends (`USSD-007`).
- **Telco Chaos Runner:** Verifies duplicate-callback replay idempotency (`CHAOS-001`), session timeout enforcement (`CHAOS-002`), and 7 adversarial subscriber input payloads.
- **CI-Ready Outputs:** Markdown, JSON, and **SARIF v2.1.0** for GitHub Code Scanning.

## Installation

```bash
pip install ussdkit
# or with uv
uv pip install -e ".[dev]"
```

## Quick Start (CLI)

```bash
# 1. Inspect a USSD screen for GSM-7 / UCS-2 truncation hazards
ussdkit check-text "Welcome to Farmer’s Wallet! 1. Balance 2. Send Money 3. Buy Airtime 4. Loans 5. Help" --strict-160

# 2. Replay a scripted session against the built-in mobile-money demo handler
ussdkit dial demo --inputs "2,0772000111,5000,1"

# 3. Crawl every reachable screen and emit a Markdown or SARIF audit report
ussdkit crawl demo --format markdown
ussdkit crawl demo --format sarif > ussd-audit.sarif

# 4. Run telco chaos & replay idempotency tests against a local or staging webhook
ussdkit chaos http://localhost:8000/ussd --gateway africastalking
```

## Quick Start (Python / `pytest`)

```python
from ussdkit import CallableTransport, UssdChaosRunner, UssdRequest, UssdTreeCrawler

def my_ussd_handler(req: UssdRequest) -> str:
    if not req.text:
        return "CON Wallet\n1. Balance\n0. Exit"
    if req.text == "1":
        return "END Balance: UGX 120,000"
    return "END Goodbye."

transport = CallableTransport(my_ussd_handler)
assert UssdTreeCrawler(transport).crawl().passed
assert UssdChaosRunner(transport).run_all(happy_path=("1",)).passed
```

## Development & Testing

```bash
uv sync --extra dev
uv run pytest -v
uv run ruff check src tests examples
uv run mypy src
```

## License

MIT License — see [LICENSE](LICENSE).
