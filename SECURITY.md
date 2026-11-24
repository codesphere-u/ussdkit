# Security Policy

## Reporting a Vulnerability
Please report security vulnerabilities responsibly via email to `codesphereinnovationz@gmail.com` or by opening a private GitHub Security Advisory on `codesphere-u/ussdkit`. Do not disclose unpatched vulnerabilities publicly.

## Security Design Principles
- Zero runtime third-party dependencies.
- `HttpTransport` only connects to explicitly caller-provided `http://` or `https://` endpoints with bounded timeouts.
- Never log subscriber PINs or MSISDNs in CI reports.
