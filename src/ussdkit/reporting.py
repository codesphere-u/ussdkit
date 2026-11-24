"""JSON, Markdown, and SARIF v2.1.0 report serializers for CI and GitHub Code Scanning."""

from __future__ import annotations

import json
from typing import Any

from ussdkit.models import ChaosReport, CrawlReport, Severity, UssdFinding

_SARIF_LEVELS: dict[Severity, str] = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.NOTE: "note",
}


def findings_to_sarif(
    findings: tuple[UssdFinding, ...] | list[UssdFinding],
    *,
    tool_version: str = "0.1.0",
    artifact_uri: str = "ussd-menu",
) -> dict[str, Any]:
    """Serialize USSD audit findings into a SARIF v2.1.0 document for CI gates."""
    rules_seen: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []

    for finding in findings:
        if finding.rule_id not in rules_seen:
            rules_seen[finding.rule_id] = {
                "id": finding.rule_id,
                "name": finding.title.replace(" ", ""),
                "shortDescription": {"text": finding.title},
                "help": {"text": finding.remediation or finding.title},
            }

        path_label = " -> ".join(finding.path) if finding.path else "<root>"
        results.append(
            {
                "ruleId": finding.rule_id,
                "level": _SARIF_LEVELS[finding.severity],
                "message": {"text": f"[{path_label}] {finding.message}"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": artifact_uri},
                            "region": {"startLine": 1},
                        }
                    }
                ],
                "properties": {
                    "ussdPath": list(finding.path),
                    "screenExcerpt": finding.screen_excerpt,
                },
            }
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ussdkit",
                        "version": tool_version,
                        "informationUri": "https://github.com/codesphere-u/ussdkit",
                        "rules": list(rules_seen.values()),
                    }
                },
                "results": results,
            }
        ],
    }


def crawl_report_to_json(report: CrawlReport) -> str:
    """Serialize a `CrawlReport` to indented JSON."""
    payload = {
        "service_code": report.service_code,
        "passed": report.passed,
        "nodes_visited": report.nodes_visited,
        "terminal_screens": report.terminal_screens,
        "max_depth_reached": report.max_depth_reached,
        "truncated_by_budget": report.truncated_by_budget,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "nodes": [
            {
                "path": list(n.path),
                "directive": n.directive.value,
                "encoding": n.encoding,
                "unit_count": n.unit_count,
                "max_units": n.max_units,
                "depth": n.depth,
                "detected_options": list(n.detected_options),
                "message": n.message,
            }
            for n in report.nodes
        ],
        "findings": [
            {
                "rule_id": f.rule_id,
                "severity": f.severity.value,
                "title": f.title,
                "message": f.message,
                "path": list(f.path),
                "remediation": f.remediation,
            }
            for f in report.findings
        ],
    }
    return json.dumps(payload, indent=2)


def crawl_report_to_markdown(report: CrawlReport) -> str:
    """Render a concise human-readable Markdown summary of a USSD crawl."""
    status = "PASS" if report.passed else "FAIL"
    lines = [
        f"# USSDKit Crawl Report ({report.service_code}) — {status}",
        "",
        f"- **Screens visited:** {report.nodes_visited} ({report.terminal_screens} terminal)",
        f"- **Max depth reached:** {report.max_depth_reached}",
        f"- **Errors:** {report.error_count} | **Warnings:** {report.warning_count}",
        "",
        "## Findings",
    ]
    if not report.findings:
        lines.append("- None. All explored screens are within encoding and protocol budgets.")
    else:
        for f in report.findings:
            path_str = " -> ".join(f.path) if f.path else "<root>"
            lines.append(
                f"- **[{f.severity.value.upper()}] {f.rule_id} ({path_str}):** {f.title} — {f.message}"
            )
    return "\n".join(lines) + "\n"


def chaos_report_to_json(report: ChaosReport) -> str:
    """Serialize a `ChaosReport` to indented JSON."""
    payload = {
        "service_code": report.service_code,
        "passed": report.passed,
        "total_cases": report.total_cases,
        "passed_cases": report.passed_cases,
        "failed_cases": report.failed_cases,
        "results": [
            {
                "case_id": r.case_id,
                "category": r.category,
                "description": r.description,
                "passed": r.passed,
                "detail": r.detail,
                "path": list(r.path),
            }
            for r in report.results
        ],
        "findings": [
            {
                "rule_id": f.rule_id,
                "severity": f.severity.value,
                "title": f.title,
                "message": f.message,
                "path": list(f.path),
                "remediation": f.remediation,
            }
            for f in report.findings
        ],
    }
    return json.dumps(payload, indent=2)
