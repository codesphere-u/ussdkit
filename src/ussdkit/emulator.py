"""Stateful USSD session emulator supporting in-process handlers and HTTP webhook endpoints."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from typing import Protocol

from ussdkit.gateways import decode_gateway_response, encode_gateway_request
from ussdkit.models import (
    GatewayFormat,
    ResponseDirective,
    SessionTurn,
    UssdRequest,
    UssdResponse,
)

# Typical GSM USSD session timeout across East/West African mobile networks (seconds)
DEFAULT_TELCO_SESSION_TIMEOUT_S = 180.0


class UssdTransport(Protocol):
    """Transport abstraction invoking either a local Python handler or an HTTP endpoint."""

    def send(self, request: UssdRequest) -> UssdResponse: ...


class CallableTransport:
    """In-process transport wrapping a Python USSD handler function.

    Handler signature: `(UssdRequest) -> str` returning raw gateway text
    (e.g. `"CON Welcome\\n1. Check Balance"` or Hubtel/Infobip JSON string).
    """

    def __init__(
        self,
        handler: Callable[[UssdRequest], str],
        *,
        gateway: GatewayFormat = GatewayFormat.AFRICASTALKING,
        strict_160: bool = False,
    ) -> None:
        self.handler = handler
        self.gateway = gateway
        self.strict_160 = strict_160

    def send(self, request: UssdRequest) -> UssdResponse:
        start = time.perf_counter()
        raw = self.handler(request)
        latency_ms = round((time.perf_counter() - start) * 1000.0, 3)
        return decode_gateway_response(
            raw,
            self.gateway,
            status_code=200,
            latency_ms=latency_ms,
            strict_160=self.strict_160,
        )


class HttpTransport:
    """Live HTTP/HTTPS webhook transport using Python stdlib (no third-party deps)."""

    def __init__(
        self,
        url: str,
        *,
        gateway: GatewayFormat = GatewayFormat.AFRICASTALKING,
        timeout_s: float = 10.0,
        extra_headers: dict[str, str] | None = None,
        strict_160: bool = False,
    ) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError("Webhook URL must start with http:// or https://")
        self.url = url
        self.gateway = gateway
        self.timeout_s = timeout_s
        self.extra_headers = dict(extra_headers or {})
        self.strict_160 = strict_160

    def send(self, request: UssdRequest) -> UssdResponse:
        encoded = encode_gateway_request(request, self.gateway)
        headers = {**encoded.headers, **self.extra_headers}
        http_req = urllib.request.Request(
            self.url,
            data=encoded.body,
            headers=headers,
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(http_req, timeout=self.timeout_s) as resp:
                raw_body = resp.read().decode("utf-8", errors="replace")
                status_code = int(resp.status)
        except urllib.error.HTTPError as exc:
            raw_body = exc.read().decode("utf-8", errors="replace")
            status_code = int(exc.code)
        latency_ms = round((time.perf_counter() - start) * 1000.0, 3)
        return decode_gateway_response(
            raw_body,
            self.gateway,
            status_code=status_code,
            latency_ms=latency_ms,
            strict_160=self.strict_160,
        )


class UssdSessionTimeoutError(TimeoutError):
    """Raised when a simulated USSD session exceeds the telco session timeout."""


class UssdSession:
    """Stateful subscriber session emulating GSM USSD interaction and `*`-chained history."""

    def __init__(
        self,
        transport: UssdTransport,
        *,
        service_code: str = "*384#",
        phone_number: str = "+256772000111",
        network_code: str = "64110",
        session_id: str | None = None,
        timeout_seconds: float = DEFAULT_TELCO_SESSION_TIMEOUT_S,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.transport = transport
        self.service_code = service_code
        self.phone_number = phone_number
        self.network_code = network_code
        self.session_id = session_id or f"ATUid_{uuid.uuid4().hex[:12]}"
        self.timeout_seconds = timeout_seconds
        self._clock = clock or time.monotonic
        self._started_at: float | None = None
        self._inputs: list[str] = []
        self._turns: list[SessionTurn] = []
        self._closed: bool = False

    @property
    def turns(self) -> tuple[SessionTurn, ...]:
        return tuple(self._turns)

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def input_chain(self) -> str:
        return "*".join(self._inputs)

    def dial(self, fast_path: str | None = None) -> UssdResponse:
        """Initiate the USSD session (optionally with a fast-path shortcode like `*384*1*2#`)."""
        if self._started_at is not None:
            raise RuntimeError("Session already dialed; use reply() or open a new UssdSession.")
        self._started_at = self._clock()

        if fast_path:
            # Extract fast-path segments after service code root (e.g. *384*1*2# -> "1*2")
            cleaned = fast_path.strip().lstrip("*").rstrip("#")
            parts = cleaned.split("*")
            if len(parts) > 1:
                self._inputs.extend(parts[1:])

        return self._dispatch(user_input=self.input_chain)

    def reply(self, choice: str) -> UssdResponse:
        """Send the next subscriber input within an open CON session."""
        if self._started_at is None:
            raise RuntimeError("Session has not been dialed yet; call dial() first.")
        if self._closed:
            raise RuntimeError("Cannot reply to a closed USSD session.")

        elapsed = self._clock() - self._started_at
        if elapsed > self.timeout_seconds:
            self._closed = True
            raise UssdSessionTimeoutError(
                f"USSD session '{self.session_id}' exceeded telco timeout "
                f"({elapsed:.1f}s > {self.timeout_seconds:.1f}s)"
            )

        self._inputs.append(choice)
        return self._dispatch(user_input=choice)

    def replay_last(self) -> UssdResponse:
        """Simulate a telco gateway duplicate callback retry of the last sent request."""
        if not self._turns:
            raise RuntimeError("No previous turn to replay.")
        last_req = self._turns[-1].request
        return self.transport.send(last_req)

    def run_script(self, inputs: list[str] | tuple[str, ...]) -> list[UssdResponse]:
        """Dial and replay a sequence of subscriber inputs until completion or END."""
        responses = [self.dial()]
        for item in inputs:
            if self._closed:
                break
            responses.append(self.reply(item))
        return responses

    def _dispatch(self, *, user_input: str) -> UssdResponse:
        assert self._started_at is not None
        elapsed = max(0.0, self._clock() - self._started_at)
        req = UssdRequest(
            session_id=self.session_id,
            phone_number=self.phone_number,
            service_code=self.service_code,
            text=self.input_chain,
            latest_input=self._inputs[-1] if self._inputs else "",
            network_code=self.network_code,
            turn_index=len(self._turns),
            elapsed_seconds=round(elapsed, 3),
        )
        resp = self.transport.send(req)
        self._turns.append(
            SessionTurn(
                turn_index=req.turn_index,
                user_input=user_input,
                request=req,
                response=resp,
            )
        )
        if resp.directive == ResponseDirective.END:
            self._closed = True
        return resp
