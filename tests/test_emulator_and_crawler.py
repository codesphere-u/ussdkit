"""Tests for UssdSession emulator, HttpTransport, and UssdTreeCrawler."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest

from ussdkit.cli import demo_mobile_money_handler
from ussdkit.crawler import UssdTreeCrawler, extract_menu_options
from ussdkit.emulator import (
    CallableTransport,
    HttpTransport,
    UssdSession,
    UssdSessionTimeoutError,
)
from ussdkit.models import GatewayFormat, ResponseDirective, UssdRequest


def test_session_dial_reply_and_fast_path() -> None:
    transport = CallableTransport(demo_mobile_money_handler)
    session = UssdSession(transport, service_code="*384#")
    r0 = session.dial()
    assert r0.directive == ResponseDirective.CON
    r1 = session.reply("1")
    assert r1.directive == ResponseDirective.END
    assert "UGX 245,500" in r1.message
    assert session.is_closed

    fast = UssdSession(transport, service_code="*384#")
    rf = fast.dial(fast_path="*384*1#")
    assert rf.directive == ResponseDirective.END
    assert "UGX 245,500" in rf.message


def test_session_timeout_raises_after_180s() -> None:
    now = [0.0]
    transport = CallableTransport(demo_mobile_money_handler)
    session = UssdSession(transport, timeout_seconds=180.0, clock=lambda: now[0])
    session.dial()
    now[0] = 181.0
    with pytest.raises(UssdSessionTimeoutError):
        session.reply("1")
    assert session.is_closed


def test_http_transport_roundtrip_against_local_webhook() -> None:
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            form = parse_qs(raw)
            text = form.get("text", [""])[0]
            body = "CON 1. Balance\n0. Exit" if not text else "END Balance: UGX 50,000"
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        transport = HttpTransport(
            f"http://127.0.0.1:{port}/ussd",
            gateway=GatewayFormat.AFRICASTALKING,
        )
        session = UssdSession(transport)
        responses = session.run_script(["1"])
        assert len(responses) == 2
        assert responses[0].directive == ResponseDirective.CON
        assert "50,000" in responses[1].message
    finally:
        server.shutdown()
        server.server_close()


def test_crawler_passes_clean_demo_handler() -> None:
    crawler = UssdTreeCrawler(CallableTransport(demo_mobile_money_handler))
    report = crawler.crawl()
    assert report.passed is True
    assert report.nodes_visited >= 7
    assert report.terminal_screens >= 4
    assert report.error_count == 0


def test_crawler_catches_ucs2_overflow_cycle_and_protocol_error() -> None:
    def buggy_handler(req: UssdRequest) -> str:
        if req.text == "":
            return "CON Main Menu\n1. Overflow UCS2\n2. Loop Back\n3. Bad Prefix"
        if req.text == "1":
            return (
                "END Farmer\u2019s Cooperative Premium Alert: Your seasonal harvest "
                "settlement requires verification at branch office today before 5pm."
            )
        if req.text == "2":
            return "CON Submenu\n1. Back"
        if req.text == "2*1":
            return "CON Main Menu\n1. Overflow UCS2\n2. Loop Back\n3. Bad Prefix"
        if req.text == "3":
            return "Forgot CON or END prefix"
        return "END Unknown"

    crawler = UssdTreeCrawler(CallableTransport(buggy_handler))
    report = crawler.crawl()
    assert report.passed is False
    rule_ids = {f.rule_id for f in report.findings}
    assert "USSD-001" in rule_ids
    assert "USSD-002" in rule_ids
    assert "USSD-003" in rule_ids
    assert "USSD-006" in rule_ids


def test_extract_menu_options_handles_common_delimiters() -> None:
    opts = extract_menu_options("Choose:\n1. Send\n2) Receive\n3: Loans\n0 - Exit\n# - Help")
    assert opts == ("1", "2", "3", "0", "#")
