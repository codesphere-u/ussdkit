# Architecture — `ussdkit`

`ussdkit` is organized as a zero-dependency Python 3.11+ library and CLI composed of six focused modules:

1. **`ussdkit.encoding`** — Implements 3GPP TS 23.038 GSM-7 default and extension alphabet accounting (2-septet escape sequences) alongside UCS-2 (UTF-16BE) code-unit detection and automated GSM-7 sanitization suggestions.
2. **`ussdkit.gateways`** — Translates normalized `UssdRequest` / `UssdResponse` envelopes to and from Africa's Talking (`application/x-www-form-urlencoded` + `CON`/`END`), Hubtel JSON (`Initiation`/`Response`/`Release`), Infobip JSON (`shouldClose`), and generic JSON formats.
3. **`ussdkit.emulator`** — Manages stateful `UssdSession` lifecycles (`*`-chained input history, fast-path shortcode dialing `*384*1*2#`, injectable monotonic clocks for deterministic 180-second telco session-timeout enforcement, and duplicate callback replay).
4. **`ussdkit.crawler`** — Performs breadth-first state-space exploration over reachable menu options, fingerprinting screens to detect navigation cycles, dead-end `CON` prompts, excessive menu depth, protocol violations, and GSM-7/UCS-2 screen overflows.
5. **`ussdkit.chaos`** — Runs telco fault-injection tests including duplicate callback replay idempotency verification, session timeout boundary tests, and 7 adversarial subscriber input classes (empty, out-of-range, negative, `*`-delimiter injection, emoji/Unicode, oversized payloads, SQL/template probes).
6. **`ussdkit.reporting` & `ussdkit.cli`** — Emits human-readable Markdown, machine-readable JSON, and SARIF v2.1.0 documents suitable for GitHub Code Scanning CI gates.
