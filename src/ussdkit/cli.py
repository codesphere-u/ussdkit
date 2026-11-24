"""Command-line interface for ussdkit."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Callable, Sequence

from ussdkit.chaos import UssdChaosRunner
from ussdkit.crawler import UssdTreeCrawler
from ussdkit.emulator import CallableTransport, HttpTransport, UssdSession, UssdTransport
from ussdkit.encoding import analyze_payload_encoding
from ussdkit.models import GatewayFormat, UssdRequest
from ussdkit.reporting import (
    chaos_report_to_json,
    crawl_report_to_json,
    crawl_report_to_markdown,
    findings_to_sarif,
)


def demo_mobile_money_handler(req: UssdRequest) -> str:
    """Built-in realistic East African Mobile Money USSD handler for quick demos and tests."""
    parts = [p for p in req.text.split("*") if p] if req.text else []
    if not parts:
        return (
            "CON Mobile Wallet *384#\n"
            "1. Check Balance\n"
            "2. Send Money\n"
            "3. Buy Airtime\n"
            "0. Exit"
        )
    if parts[0] == "0":
        return "END Thank you for using Mobile Wallet."
    if parts[0] == "1":
        return "END Available Balance: UGX 245,500. Mini-statement sent via SMS."
    if parts[0] == "2":
        if len(parts) == 1:
            return "CON Enter recipient phone number (e.g. 0772123456):"
        if len(parts) == 2:
            if not parts[1].isdigit() or len(parts[1]) < 9:
                return "END Invalid phone number format. Please dial again."
            return f"CON Enter amount in UGX to send to {parts[1]}:"
        if len(parts) == 3:
            if not parts[2].isdigit() or int(parts[2]) <= 0:
                return "END Invalid amount entered."
            return f"CON Confirm sending UGX {parts[2]} to {parts[1]}?\n1. Confirm\n2. Cancel"
        if parts[3] == "1":
            return f"END Sent UGX {parts[2]} to {parts[1]}. Ref: TX-{req.session_id[-6:].upper()}"
        return "END Transfer cancelled."
    if parts[0] == "3":
        if len(parts) == 1:
            return "CON Buy Airtime:\n1. Self\n2. Other Number"
        if parts[1] == "1":
            return "END Airtime top-up for self initiated. Dial *131# to verify."
        if parts[1] == "2":
            return "END Enter recipient on next menu in v2. Thank you."
        return "END Invalid airtime choice."
    return "END Invalid menu selection. Please dial *384# again."


def _load_transport(
    target: str,
    *,
    gateway: GatewayFormat,
    strict_160: bool,
) -> UssdTransport:
    if target == "demo":
        return CallableTransport(demo_mobile_money_handler, gateway=gateway, strict_160=strict_160)
    if target.startswith(("http://", "https://")):
        return HttpTransport(target, gateway=gateway, strict_160=strict_160)
    if ":" in target:
        mod_name, attr_name = target.split(":", 1)
        module = importlib.import_module(mod_name)
        handler: Callable[[UssdRequest], str] = getattr(module, attr_name)
        return CallableTransport(handler, gateway=gateway, strict_160=strict_160)
    raise ValueError(
        f"Unsupported target '{target}'. Use 'demo', an http(s):// URL, or 'module:callable'."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ussdkit",
        description="Stateful USSD emulator, GSM-7/UCS-2 budget guard, menu crawler, and telco chaos tester.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check-text", help="Analyze a USSD/SMS string under GSM-7/UCS-2 rules")
    p_check.add_argument("text", help="USSD screen or SMS text to inspect")
    p_check.add_argument("--strict-160", action="store_true", help="Enforce strict 160/70 limit")
    p_check.add_argument("--json", action="store_true", help="Emit JSON output")

    p_dial = sub.add_parser("dial", help="Run a scripted USSD session against a handler or URL")
    p_dial.add_argument("target", help="'demo', http(s):// webhook URL, or 'module:callable'")
    p_dial.add_argument("--inputs", default="", help="Comma-separated replies, e.g. '2,0772000111,5000,1'")
    p_dial.add_argument("--service-code", default="*384#")
    p_dial.add_argument("--phone", default="+256772000111")
    p_dial.add_argument(
        "--gateway",
        default="africastalking",
        choices=[g.value for g in GatewayFormat],
    )
    p_dial.add_argument("--strict-160", action="store_true")

    p_crawl = sub.add_parser("crawl", help="Explore all reachable USSD menus and audit encoding/UX")
    p_crawl.add_argument("target", help="'demo', http(s):// webhook URL, or 'module:callable'")
    p_crawl.add_argument("--service-code", default="*384#")
    p_crawl.add_argument("--max-depth", type=int, default=5)
    p_crawl.add_argument("--max-nodes", type=int, default=80)
    p_crawl.add_argument(
        "--gateway",
        default="africastalking",
        choices=[g.value for g in GatewayFormat],
    )
    p_crawl.add_argument("--strict-160", action="store_true")
    p_crawl.add_argument("--format", choices=["markdown", "json", "sarif"], default="markdown")

    p_chaos = sub.add_parser("chaos", help="Run telco fault-injection and malformed-input chaos suite")
    p_chaos.add_argument("target", help="'demo', http(s):// webhook URL, or 'module:callable'")
    p_chaos.add_argument("--service-code", default="*384#")
    p_chaos.add_argument(
        "--gateway",
        default="africastalking",
        choices=[g.value for g in GatewayFormat],
    )
    p_chaos.add_argument("--strict-160", action="store_true")
    p_chaos.add_argument("--format", choices=["json", "sarif"], default="json")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check-text":
        rep = analyze_payload_encoding(args.text, strict_160=args.strict_160)
        if args.json:
            print(
                json.dumps(
                    {
                        "encoding": rep.encoding,
                        "char_count": rep.char_count,
                        "unit_count": rep.unit_count,
                        "max_units": rep.max_units,
                        "overflow_units": rep.overflow_units,
                        "within_budget": rep.within_budget,
                        "extended_chars": list(rep.extended_chars),
                        "non_gsm7_chars": list(rep.non_gsm7_chars),
                        "suggested_gsm7_text": rep.suggested_gsm7_text,
                    },
                    indent=2,
                )
            )
        else:
            status = "OK" if rep.within_budget else "OVERFLOW"
            print(
                f"[{status}] {rep.encoding}: {rep.unit_count}/{rep.max_units} units "
                f"(chars={rep.char_count}, overflow={rep.overflow_units})"
            )
            if rep.non_gsm7_chars:
                print(f"Non-GSM-7 triggers: {list(rep.non_gsm7_chars)}")
        return 0 if rep.within_budget else 2

    gateway = GatewayFormat(args.gateway)
    transport = _load_transport(args.target, gateway=gateway, strict_160=args.strict_160)

    if args.command == "dial":
        session = UssdSession(
            transport,
            service_code=args.service_code,
            phone_number=args.phone,
        )
        inputs = [x.strip() for x in args.inputs.split(",") if x.strip()] if args.inputs else []
        responses = session.run_script(inputs)
        for idx, resp in enumerate(responses):
            enc = resp.encoding_report
            budget = f"{enc.encoding} {enc.unit_count}/{enc.max_units}" if enc else ""
            print(f"--- Turn {idx} [{resp.directive.value}] ({budget}) ---")
            print(resp.message)
        return 0 if all(not r.protocol_errors for r in responses) else 2

    if args.command == "crawl":
        crawler = UssdTreeCrawler(
            transport,
            service_code=args.service_code,
            max_depth=args.max_depth,
            max_nodes=args.max_nodes,
        )
        report = crawler.crawl()
        if args.format == "json":
            print(crawl_report_to_json(report))
        elif args.format == "sarif":
            print(json.dumps(findings_to_sarif(report.findings), indent=2))
        else:
            print(crawl_report_to_markdown(report))
        return 0 if report.passed else 2

    if args.command == "chaos":
        runner = UssdChaosRunner(transport, service_code=args.service_code)
        chaos_report = runner.run_all()
        if args.format == "sarif":
            print(json.dumps(findings_to_sarif(chaos_report.findings), indent=2))
        else:
            print(chaos_report_to_json(chaos_report))
        return 0 if chaos_report.passed else 2

    return 1


if __name__ == "__main__":
    sys.exit(main())
