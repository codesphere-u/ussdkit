"""Telco chaos and adversarial input robustness tester for USSD applications."""

from __future__ import annotations

from ussdkit.emulator import UssdSession, UssdSessionTimeoutError, UssdTransport
from ussdkit.models import (
    ChaosCaseResult,
    ChaosReport,
    Severity,
    UssdFinding,
)


class _ManualClock:
    """Deterministic monotonic clock for simulating telco session timeouts."""

    def __init__(self, initial: float = 0.0) -> None:
        self.now = initial

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class UssdChaosRunner:
    """Injects real-world mobile-network failures and malformed subscriber inputs."""

    def __init__(
        self,
        transport: UssdTransport,
        *,
        service_code: str = "*384#",
        phone_number: str = "+256772000111",
        timeout_seconds: float = 180.0,
    ) -> None:
        self.transport = transport
        self.service_code = service_code
        self.phone_number = phone_number
        self.timeout_seconds = timeout_seconds

    def run_all(self, *, happy_path: tuple[str, ...] = ()) -> ChaosReport:
        """Execute the full telco chaos suite and return structured results."""
        results: list[ChaosCaseResult] = []
        findings: list[UssdFinding] = []

        # 1. Duplicate callback replay idempotency (common on 2G/3G telco retries)
        results.append(self._test_duplicate_replay(happy_path, findings))

        # 2. Telco 180-second session timeout boundary enforcement
        results.append(self._test_telco_timeout_boundary(findings))

        # 3. Malformed / adversarial subscriber inputs at root menu
        fuzz_inputs = [
            ("CHAOS-FUZZ-EMPTY", "empty_input", "", "Empty subscriber reply"),
            ("CHAOS-FUZZ-OOB", "out_of_range", "999", "Out-of-range numeric selection"),
            ("CHAOS-FUZZ-NEG", "negative_input", "-1", "Negative numeric input"),
            ("CHAOS-FUZZ-DELIM", "delimiter_injection", "1*1*999999", "Embedded '*' delimiter injection"),
            ("CHAOS-FUZZ-UNICODE", "unicode_emoji", "💰🔥", "Non-GSM-7 emoji input"),
            ("CHAOS-FUZZ-LONG", "oversized_input", "9" * 256, "Oversized 256-char subscriber input"),
            ("CHAOS-FUZZ-SQLI", "injection_probe", "1' OR '1'='1", "SQL/template injection characters"),
        ]
        for case_id, category, payload, desc in fuzz_inputs:
            results.append(self._test_fuzz_input(case_id, category, payload, desc, findings))

        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        return ChaosReport(
            service_code=self.service_code,
            total_cases=len(results),
            passed_cases=passed_count,
            failed_cases=failed_count,
            results=tuple(results),
            findings=tuple(findings),
        )

    def _test_duplicate_replay(
        self,
        happy_path: tuple[str, ...],
        findings: list[UssdFinding],
    ) -> ChaosCaseResult:
        session = UssdSession(
            self.transport,
            service_code=self.service_code,
            phone_number=self.phone_number,
        )
        responses = session.run_script(happy_path)
        first = responses[-1]
        replayed = session.replay_last()

        same_directive = first.directive == replayed.directive
        same_message = first.message == replayed.message
        no_errors = not replayed.protocol_errors and replayed.status_code < 400
        ok = same_directive and same_message and no_errors

        if not ok:
            findings.append(
                UssdFinding(
                    rule_id="CHAOS-001",
                    severity=Severity.ERROR,
                    title="Non-Idempotent Duplicate Telco Callback Replay",
                    message=(
                        "Replaying the exact same sessionId + text callback produced a different "
                        "response or error, risking double-charges on mobile network retries."
                    ),
                    path=happy_path,
                    screen_excerpt=replayed.message[:100],
                    remediation="Key session mutations by (sessionId, turn_index/text) for idempotency.",
                )
            )
        return ChaosCaseResult(
            case_id="CHAOS-REPLAY",
            category="idempotency",
            description="Duplicate telco gateway callback replay returns identical response",
            passed=ok,
            detail="Identical deterministic response on replay" if ok else "Response diverged on duplicate callback",
            path=happy_path,
        )

    def _test_telco_timeout_boundary(self, findings: list[UssdFinding]) -> ChaosCaseResult:
        clock = _ManualClock(0.0)
        session = UssdSession(
            self.transport,
            service_code=self.service_code,
            phone_number=self.phone_number,
            timeout_seconds=self.timeout_seconds,
            clock=clock,
        )
        first = session.dial()
        if first.is_terminal:
            return ChaosCaseResult(
                case_id="CHAOS-TIMEOUT",
                category="timeout",
                description="Telco session timeout enforcement",
                passed=True,
                detail="Root screen terminated immediately (no multi-turn timeout risk)",
            )

        clock.advance(self.timeout_seconds + 1.0)
        try:
            session.reply("1")
            ok = False
            detail = "Emulator failed to enforce telco timeout boundary"
        except UssdSessionTimeoutError:
            ok = True
            detail = f"Session properly terminated after exceeding {self.timeout_seconds:.0f}s telco window"

        if not ok:
            findings.append(
                UssdFinding(
                    rule_id="CHAOS-002",
                    severity=Severity.ERROR,
                    title="Session Timeout Not Enforced",
                    message=detail,
                    path=("1",),
                )
            )
        return ChaosCaseResult(
            case_id="CHAOS-TIMEOUT",
            category="timeout",
            description="Telco 180s session expiration boundary",
            passed=ok,
            detail=detail,
            path=("1",),
        )

    def _test_fuzz_input(
        self,
        case_id: str,
        category: str,
        payload: str,
        description: str,
        findings: list[UssdFinding],
    ) -> ChaosCaseResult:
        session = UssdSession(
            self.transport,
            service_code=self.service_code,
            phone_number=self.phone_number,
        )
        try:
            root = session.dial()
            if root.is_terminal:
                return ChaosCaseResult(
                    case_id=case_id,
                    category=category,
                    description=description,
                    passed=True,
                    detail="Skipped: root screen is terminal",
                )
            resp = session.reply(payload)
        except Exception as exc:
            findings.append(
                UssdFinding(
                    rule_id="CHAOS-003",
                    severity=Severity.ERROR,
                    title=f"Unhandled Exception on {description}",
                    message=f"Handler crashed with {type(exc).__name__}: {exc}",
                    path=(payload[:32],),
                    remediation="Validate and sanitize subscriber USSD input before branching or DB queries.",
                )
            )
            return ChaosCaseResult(
                case_id=case_id,
                category=category,
                description=description,
                passed=False,
                detail=f"Unhandled {type(exc).__name__}: {exc}",
                path=(payload[:32],),
            )

        enc = resp.encoding_report
        ok = (
            resp.status_code < 500
            and not resp.protocol_errors
            and bool(resp.message.strip())
            and (enc is not None and enc.within_budget)
        )
        if not ok:
            detail_parts: list[str] = []
            if resp.status_code >= 500:
                detail_parts.append(f"HTTP {resp.status_code}")
            if resp.protocol_errors:
                detail_parts.append("; ".join(resp.protocol_errors))
            if not resp.message.strip():
                detail_parts.append("empty body")
            if enc is not None and not enc.within_budget:
                detail_parts.append(
                    f"screen overflow ({enc.unit_count}/{enc.max_units} {enc.encoding})"
                )
            detail = ", ".join(detail_parts) or "invalid response"
            findings.append(
                UssdFinding(
                    rule_id="CHAOS-004",
                    severity=Severity.ERROR,
                    title=f"Malformed Input Handling Defect ({category})",
                    message=f"Input {payload[:32]!r} caused: {detail}",
                    path=(payload[:32],),
                    screen_excerpt=resp.message[:100],
                    remediation="Return a concise GSM-7 error screen without echoing raw untrusted input.",
                )
            )
        else:
            assert enc is not None
            detail = f"Handled gracefully ({resp.directive.value}, {enc.unit_count}/{enc.max_units} {enc.encoding})"

        return ChaosCaseResult(
            case_id=case_id,
            category=category,
            description=description,
            passed=ok,
            detail=detail,
            path=(payload[:32],),
        )
