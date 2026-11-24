"""Tests for UssdChaosRunner, reporting serializers (JSON/Markdown/SARIF), and CLI."""

from __future__ import annotations

import json

from ussdkit.chaos import UssdChaosRunner
from ussdkit.cli import demo_mobile_money_handler
from ussdkit.cli import main as cli_main
from ussdkit.crawler import UssdTreeCrawler
from ussdkit.emulator import CallableTransport
from ussdkit.models import UssdRequest
from ussdkit.reporting import (
    chaos_report_to_json,
    crawl_report_to_json,
    crawl_report_to_markdown,
    findings_to_sarif,
)


def test_chaos_runner_passes_resilient_demo_handler() -> None:
    runner = UssdChaosRunner(CallableTransport(demo_mobile_money_handler))
    report = runner.run_all(happy_path=("1",))
    assert report.passed is True
    assert report.failed_cases == 0
    assert report.total_cases == 9
    parsed = json.loads(chaos_report_to_json(report))
    assert parsed["passed"] is True


def test_chaos_runner_catches_non_idempotent_replay_and_crash() -> None:
    counter = {"calls": 0}

    def fragile_handler(req: UssdRequest) -> str:
        if req.text == "":
            return "CON 1. Pay\n2. Crash"
        if req.text == "1":
            counter["calls"] += 1
            return f"END Charged attempt #{counter['calls']}"
        if req.latest_input == "999":
            raise ZeroDivisionError("unhandled invalid choice")
        return "END OK"

    runner = UssdChaosRunner(CallableTransport(fragile_handler))
    report = runner.run_all(happy_path=("1",))
    assert report.passed is False
    rule_ids = {f.rule_id for f in report.findings}
    assert "CHAOS-001" in rule_ids  # non-idempotent replay
    assert "CHAOS-003" in rule_ids  # unhandled crash on fuzz input


def test_sarif_and_markdown_reporting() -> None:
    crawler = UssdTreeCrawler(CallableTransport(demo_mobile_money_handler))
    rep = crawler.crawl()
    md = crawl_report_to_markdown(rep)
    assert "PASS" in md
    j = json.loads(crawl_report_to_json(rep))
    assert j["passed"] is True
    sarif = findings_to_sarif(rep.findings)
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "ussdkit"


def test_cli_subcommands_end_to_end(capsys: object) -> None:
    assert cli_main(["check-text", "1. Balance\n2. Send", "--json"]) == 0
    assert cli_main(["check-text", "A" * 200]) == 2
    assert cli_main(["dial", "demo", "--inputs", "1"]) == 0
    assert cli_main(["crawl", "demo", "--format", "sarif"]) == 0
    assert cli_main(["chaos", "demo", "--format", "json"]) == 0
    _ = capsys
