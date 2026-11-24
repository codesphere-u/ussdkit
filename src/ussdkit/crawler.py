"""Automated BFS USSD menu-tree crawler and static/dynamic UX & encoding auditor."""

from __future__ import annotations

import hashlib
import re
from collections import deque

from ussdkit.emulator import UssdSession, UssdTransport
from ussdkit.models import (
    CrawlNode,
    CrawlReport,
    ResponseDirective,
    Severity,
    UssdFinding,
)

# Matches numbered menu lines such as "1. Send Money", "2) Check Balance", "0: Exit", "99 - Back"
_MENU_OPTION_RE = re.compile(r"(?m)^\s*([0-9]{1,2}|[*#])\s*[.):\-]\s+\S+")


def extract_menu_options(screen_text: str) -> tuple[str, ...]:
    """Extract selectable numeric/control menu keys from a USSD screen."""
    seen: list[str] = []
    for match in _MENU_OPTION_RE.finditer(screen_text):
        key = match.group(1)
        if key not in seen:
            seen.append(key)
    return tuple(seen)


def _fingerprint(directive: ResponseDirective, message: str) -> str:
    normalized = re.sub(r"\s+", " ", message.strip()).lower()
    return hashlib.sha256(f"{directive.value}:{normalized}".encode()).hexdigest()[:16]


class UssdTreeCrawler:
    """Breadth-first state-space explorer for USSD menu applications.

    Audits every reachable menu screen for:
    - USSD-001: Payload exceeds GSM-7/UCS-2 screen unit budget (silent telco truncation)
    - USSD-002: Hidden non-GSM-7 Unicode characters forcing UCS-2 70/80-char cliff
    - USSD-003: Protocol / HTTP / directive errors
    - USSD-004: Empty screen returned
    - USSD-005: Excessive menu depth (subscriber fatigue & 180s timeout risk)
    - USSD-006: Navigation cycle returning to an ancestor screen without an exit option
    - USSD-007: Non-terminal CON screen with no numbered options and no input prompt hint
    """

    def __init__(
        self,
        transport: UssdTransport,
        *,
        service_code: str = "*384#",
        phone_number: str = "+256772000111",
        max_depth: int = 5,
        max_nodes: int = 80,
        recommended_max_depth: int = 4,
        sample_freeform_input: str = "1000",
    ) -> None:
        self.transport = transport
        self.service_code = service_code
        self.phone_number = phone_number
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.recommended_max_depth = recommended_max_depth
        self.sample_freeform_input = sample_freeform_input

    def crawl(self) -> CrawlReport:
        """Explore reachable USSD menu paths starting from the root dial screen."""
        queue: deque[tuple[tuple[str, ...], tuple[str, ...]]] = deque([((), ())])
        visited_paths: set[tuple[str, ...]] = set()
        nodes: list[CrawlNode] = []
        findings: list[UssdFinding] = []
        terminal_count = 0
        max_depth_seen = 0
        truncated = False

        while queue:
            if len(nodes) >= self.max_nodes:
                truncated = True
                break

            path, ancestor_fps = queue.popleft()
            if path in visited_paths:
                continue
            visited_paths.add(path)

            session = UssdSession(
                self.transport,
                service_code=self.service_code,
                phone_number=self.phone_number,
            )
            responses = session.run_script(path)
            if len(responses) != len(path) + 1:
                # Session terminated early before reaching target path
                continue

            resp = responses[-1]
            depth = len(path)
            max_depth_seen = max(max_depth_seen, depth)
            options = extract_menu_options(resp.message)
            enc = resp.encoding_report
            assert enc is not None

            nodes.append(
                CrawlNode(
                    path=path,
                    directive=resp.directive,
                    message=resp.message,
                    detected_options=options,
                    encoding=enc.encoding,
                    unit_count=enc.unit_count,
                    max_units=enc.max_units,
                    depth=depth,
                )
            )
            if resp.is_terminal:
                terminal_count += 1

            excerpt = resp.message.replace("\n", " | ")[:100]

            # Check 1: Protocol errors
            for proto_err in resp.protocol_errors:
                findings.append(
                    UssdFinding(
                        rule_id="USSD-003",
                        severity=Severity.ERROR,
                        title="Gateway Protocol Violation",
                        message=proto_err,
                        path=path,
                        screen_excerpt=excerpt,
                        remediation="Return valid gateway status (HTTP 200) and CON/END directive.",
                    )
                )

            # Check 2: Empty screen body
            if not resp.message.strip():
                findings.append(
                    UssdFinding(
                        rule_id="USSD-004",
                        severity=Severity.ERROR,
                        title="Empty USSD Screen Body",
                        message="Screen returned empty text, causing a blank dialog on subscriber handsets.",
                        path=path,
                        screen_excerpt=excerpt,
                        remediation="Always return concise, non-empty instructional text.",
                    )
                )

            # Check 3: Hidden UCS-2 trigger
            if enc.non_gsm7_chars:
                offenders = ", ".join(repr(c) for c in enc.non_gsm7_chars[:5])
                findings.append(
                    UssdFinding(
                        rule_id="USSD-002",
                        severity=Severity.WARNING if enc.within_budget else Severity.ERROR,
                        title="Non-GSM-7 Characters Trigger UCS-2 Mode",
                        message=(
                            f"Screen contains non-GSM-7 characters ({offenders}), reducing "
                            f"telco character budget to {enc.max_units} UTF-16 units "
                            f"(used {enc.unit_count})."
                        ),
                        path=path,
                        screen_excerpt=excerpt,
                        remediation="Replace smart quotes, em-dashes, or emojis with GSM-7 ASCII equivalents.",
                    )
                )

            # Check 4: Screen payload overflow
            if not enc.within_budget:
                findings.append(
                    UssdFinding(
                        rule_id="USSD-001",
                        severity=Severity.ERROR,
                        title="USSD Screen Exceeds Character Budget",
                        message=(
                            f"Screen uses {enc.unit_count} {enc.encoding} units "
                            f"(max {enc.max_units}; overflow by {enc.overflow_units}). "
                            "Telco gateways will silently truncate options."
                        ),
                        path=path,
                        screen_excerpt=excerpt,
                        remediation="Shorten menu labels or paginate options across submenus.",
                    )
                )

            # Check 5: Excessive menu depth
            if depth > self.recommended_max_depth:
                findings.append(
                    UssdFinding(
                        rule_id="USSD-005",
                        severity=Severity.WARNING,
                        title="Deep USSD Menu Nesting",
                        message=(
                            f"Path depth {depth} exceeds recommended depth "
                            f"({self.recommended_max_depth}), increasing 180s telco timeout drop-offs."
                        ),
                        path=path,
                        screen_excerpt=excerpt,
                        remediation="Flatten menu hierarchy or support direct shortcode fast-paths.",
                    )
                )

            if resp.is_terminal or depth >= self.max_depth:
                continue

            fp = _fingerprint(resp.directive, resp.message)
            if fp in ancestor_fps:
                findings.append(
                    UssdFinding(
                        rule_id="USSD-006",
                        severity=Severity.NOTE,
                        title="Menu Navigation Cycle Detected",
                        message=(
                            f"Path {' -> '.join(path) or '<root>'} loops back to an earlier "
                            "screen state (back/retry navigation)."
                        ),
                        path=path,
                        screen_excerpt=excerpt,
                        remediation="Ensure every cyclic submenu also offers a clear exit or home option.",
                    )
                )
                continue

            next_ancestors = (*ancestor_fps, fp)
            if options:
                for opt in options:
                    queue.append(((*path, opt), next_ancestors))
            else:
                # Non-terminal screen without numbered options: check if it looks like a free-form prompt
                prompt_hint = bool(
                    re.search(
                        r"(?i)\b(enter|input|type|amount|pin|number|phone|name|id|confirm|code)\b",
                        resp.message,
                    )
                )
                if not prompt_hint:
                    findings.append(
                        UssdFinding(
                            rule_id="USSD-007",
                            severity=Severity.WARNING,
                            title="Ambiguous Non-Terminal Screen (No Options or Input Prompt)",
                            message=(
                                "CON screen lists neither numbered menu choices nor a clear prompt "
                                "instructing the subscriber what to enter."
                            ),
                            path=path,
                            screen_excerpt=excerpt,
                            remediation="End the session with END or prompt explicitly for input.",
                        )
                    )
                else:
                    queue.append(((*path, self.sample_freeform_input), next_ancestors))

        return CrawlReport(
            service_code=self.service_code,
            nodes_visited=len(nodes),
            terminal_screens=terminal_count,
            max_depth_reached=max_depth_seen,
            truncated_by_budget=truncated,
            nodes=tuple(nodes),
            findings=tuple(findings),
        )
