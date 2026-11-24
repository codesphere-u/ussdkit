"""Example: Testing a custom USSD Mobile Money menu with ussdkit."""

from __future__ import annotations

from ussdkit import (
    CallableTransport,
    UssdChaosRunner,
    UssdRequest,
    UssdSession,
    UssdTreeCrawler,
    crawl_report_to_markdown,
)


def cooperative_ussd(req: UssdRequest) -> str:
    parts = [p for p in req.text.split("*") if p] if req.text else []
    if not parts:
        return "CON Coffee Coop *384#\n1. Harvest Receipts\n2. Loan Balance\n0. Exit"
    if parts[0] == "1":
        return "END Last delivery: 140kg Arabica parchment (Verified)."
    if parts[0] == "2":
        return "END Active input loan balance: UGX 85,000 due 30 Nov."
    if parts[0] == "0":
        return "END Goodbye."
    return "END Invalid option. Dial *384# to retry."


if __name__ == "__main__":
    transport = CallableTransport(cooperative_ussd)
    session = UssdSession(transport, service_code="*384#")
    for idx, resp in enumerate(session.run_script(["1"])):
        print(f"Turn {idx} [{resp.directive.value}]: {resp.message}")

    crawl = UssdTreeCrawler(transport).crawl()
    print(crawl_report_to_markdown(crawl))

    chaos = UssdChaosRunner(transport).run_all(happy_path=("1",))
    print(f"Chaos suite: {chaos.passed_cases}/{chaos.total_cases} passed")
