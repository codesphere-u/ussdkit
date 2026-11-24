"""Core data models for USSD sessions, gateway messages, crawl findings, and chaos tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ussdkit.encoding import PayloadEncodingReport


class GatewayFormat(StrEnum):
    """Supported telecom aggregator USSD webhook formats."""

    AFRICASTALKING = "africastalking"
    HUBTEL = "hubtel"
    INFOBIP = "infobip"
    GENERIC = "generic"


class ResponseDirective(StrEnum):
    """Session continuation directive returned by a USSD application."""

    CON = "CON"  # Keep session open and await next subscriber input
    END = "END"  # Terminate session and display final message


class Severity(StrEnum):
    """Issue severity for static/dynamic USSD verification findings."""

    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"


@dataclass(frozen=True)
class UssdRequest:
    """Normalized USSD webhook request passed into an application or gateway adapter."""

    session_id: str
    phone_number: str
    service_code: str
    text: str  # Full `*`-delimited subscriber input chain (e.g. "1*2*5000")
    latest_input: str  # Only the most recent menu selection (e.g. "5000")
    network_code: str = "64110"  # Default: MTN Uganda MCC+MNC
    turn_index: int = 0
    elapsed_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UssdResponse:
    """Normalized USSD response returned by an application or gateway adapter."""

    directive: ResponseDirective
    message: str
    raw_body: str
    status_code: int = 200
    latency_ms: float = 0.0
    encoding_report: PayloadEncodingReport | None = None
    protocol_errors: tuple[str, ...] = ()

    @property
    def is_terminal(self) -> bool:
        return self.directive == ResponseDirective.END


@dataclass(frozen=True)
class SessionTurn:
    """Single request-response exchange inside an emulated USSD session."""

    turn_index: int
    user_input: str
    request: UssdRequest
    response: UssdResponse


@dataclass(frozen=True)
class UssdFinding:
    """Actionable reliability, encoding, or UX defect detected during crawl or chaos testing."""

    rule_id: str
    severity: Severity
    title: str
    message: str
    path: tuple[str, ...]
    screen_excerpt: str = ""
    remediation: str = ""


@dataclass(frozen=True)
class CrawlNode:
    """Visited USSD menu screen in the discovered state graph."""

    path: tuple[str, ...]
    directive: ResponseDirective
    message: str
    detected_options: tuple[str, ...]
    encoding: str
    unit_count: int
    max_units: int
    depth: int


@dataclass(frozen=True)
class CrawlReport:
    """Summary of automated BFS session-tree exploration."""

    service_code: str
    nodes_visited: int
    terminal_screens: int
    max_depth_reached: int
    truncated_by_budget: bool
    nodes: tuple[CrawlNode, ...]
    findings: tuple[UssdFinding, ...]

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    @property
    def passed(self) -> bool:
        return self.error_count == 0


@dataclass(frozen=True)
class ChaosCaseResult:
    """Outcome of one telco fault-injection or adversarial input chaos case."""

    case_id: str
    category: str
    description: str
    passed: bool
    detail: str
    path: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChaosReport:
    """Consolidated report from telco chaos & robustness testing."""

    service_code: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    results: tuple[ChaosCaseResult, ...]
    findings: tuple[UssdFinding, ...]

    @property
    def passed(self) -> bool:
        return self.failed_cases == 0
