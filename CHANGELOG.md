# Changelog

## [0.1.0] - 2026-11-24
### Added
- 3GPP TS 23.038 GSM-7 (basic + 2-septet extension) & UCS-2 payload encoding guard with sanitization suggestions.
- Multi-gateway codecs for Africa's Talking, Hubtel, Infobip, and generic JSON/text USSD protocols.
- Stateful `UssdSession` emulator supporting in-process Python handlers and live HTTP webhooks, fast-path dialing, and deterministic 180s session timeout simulation.
- Automated BFS `UssdTreeCrawler` auditing reachable USSD menus across 7 rule categories (`USSD-001`..`USSD-007`).
- `UssdChaosRunner` testing duplicate callback replay idempotency, timeout enforcement, and 7 adversarial input classes.
- Markdown, JSON, and SARIF v2.1.0 CI reporting plus the `ussdkit` CLI.
