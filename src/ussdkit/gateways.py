"""Multi-gateway webhook codecs for Africa's Talking, Hubtel, Infobip, and generic USSD gateways."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from ussdkit.encoding import analyze_payload_encoding
from ussdkit.models import GatewayFormat, ResponseDirective, UssdRequest, UssdResponse


@dataclass(frozen=True)
class EncodedHttpRequest:
    """Wire-level HTTP request payload formatted for a specific USSD aggregator."""

    content_type: str
    body: bytes
    headers: dict[str, str]


def encode_gateway_request(
    req: UssdRequest,
    gateway: GatewayFormat = GatewayFormat.AFRICASTALKING,
) -> EncodedHttpRequest:
    """Serialize a normalized `UssdRequest` into the target aggregator's webhook format."""
    if gateway == GatewayFormat.AFRICASTALKING:
        form_data = urlencode(
            {
                "sessionId": req.session_id,
                "serviceCode": req.service_code,
                "phoneNumber": req.phone_number,
                "text": req.text,
                "networkCode": req.network_code,
            }
        ).encode("utf-8")
        return EncodedHttpRequest(
            content_type="application/x-www-form-urlencoded",
            body=form_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if gateway == GatewayFormat.HUBTEL:
        msg_type = "Initiation" if req.turn_index == 0 else "Response"
        payload: dict[str, Any] = {
            "Type": msg_type,
            "Mobile": req.phone_number.lstrip("+"),
            "SessionId": req.session_id,
            "ServiceCode": req.service_code.strip("*#"),
            "Message": req.service_code if req.turn_index == 0 else req.latest_input,
            "Operator": req.metadata.get("operator", "MTN"),
            "Sequence": req.turn_index + 1,
            "ClientState": req.metadata.get("client_state", ""),
        }
        return EncodedHttpRequest(
            content_type="application/json",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    if gateway == GatewayFormat.INFOBIP:
        payload = {
            "sessionId": req.session_id,
            "msisdn": req.phone_number.lstrip("+"),
            "shortCode": req.service_code,
            "text": req.latest_input if req.turn_index > 0 else req.service_code,
            "imsi": req.metadata.get("imsi", ""),
            "networkCode": req.network_code,
            "type": "INITIAL" if req.turn_index == 0 else "RESPONSE",
        }
        return EncodedHttpRequest(
            content_type="application/json",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    # Generic JSON USSD payload
    payload = {
        "session_id": req.session_id,
        "phone_number": req.phone_number,
        "service_code": req.service_code,
        "text": req.text,
        "latest_input": req.latest_input,
        "network_code": req.network_code,
        "turn_index": req.turn_index,
    }
    return EncodedHttpRequest(
        content_type="application/json",
        body=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def decode_gateway_response(
    raw_body: str,
    gateway: GatewayFormat = GatewayFormat.AFRICASTALKING,
    *,
    status_code: int = 200,
    latency_ms: float = 0.0,
    strict_160: bool = False,
) -> UssdResponse:
    """Parse an aggregator response body into a normalized `UssdResponse` with encoding checks."""
    protocol_errors: list[str] = []

    if status_code >= 400:
        protocol_errors.append(f"HTTP error status {status_code} returned by USSD handler")

    if gateway == GatewayFormat.AFRICASTALKING:
        stripped = raw_body.strip()
        if stripped.startswith("CON "):
            directive = ResponseDirective.CON
            message = stripped[4:]
        elif stripped == "CON":
            directive = ResponseDirective.CON
            message = ""
            protocol_errors.append("CON directive returned with empty screen body")
        elif stripped.startswith("END "):
            directive = ResponseDirective.END
            message = stripped[4:]
        elif stripped == "END":
            directive = ResponseDirective.END
            message = ""
            protocol_errors.append("END directive returned with empty screen body")
        else:
            directive = ResponseDirective.END
            message = stripped
            protocol_errors.append(
                "Missing required 'CON ' or 'END ' prefix for Africa's Talking protocol"
            )
    elif gateway == GatewayFormat.HUBTEL:
        directive, message = _decode_hubtel_json(raw_body, protocol_errors)
    elif gateway == GatewayFormat.INFOBIP:
        directive, message = _decode_infobip_json(raw_body, protocol_errors)
    else:
        directive, message = _decode_generic_response(raw_body, protocol_errors)

    enc = analyze_payload_encoding(message, strict_160=strict_160)
    return UssdResponse(
        directive=directive,
        message=message,
        raw_body=raw_body,
        status_code=status_code,
        latency_ms=latency_ms,
        encoding_report=enc,
        protocol_errors=tuple(protocol_errors),
    )


def _decode_hubtel_json(
    raw_body: str, protocol_errors: list[str]
) -> tuple[ResponseDirective, str]:
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        protocol_errors.append(f"Invalid Hubtel JSON response: {exc}")
        return ResponseDirective.END, raw_body

    if not isinstance(data, dict):
        protocol_errors.append("Hubtel response must be a JSON object")
        return ResponseDirective.END, str(data)

    resp_type = str(data.get("Type", "")).strip().lower()
    message = str(data.get("Message", ""))
    if resp_type == "response":
        return ResponseDirective.CON, message
    if resp_type == "release":
        return ResponseDirective.END, message
    protocol_errors.append(f"Unexpected Hubtel Type '{data.get('Type')}' (expected Response/Release)")
    return ResponseDirective.END, message


def _decode_infobip_json(
    raw_body: str, protocol_errors: list[str]
) -> tuple[ResponseDirective, str]:
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        protocol_errors.append(f"Invalid Infobip JSON response: {exc}")
        return ResponseDirective.END, raw_body

    if not isinstance(data, dict):
        protocol_errors.append("Infobip response must be a JSON object")
        return ResponseDirective.END, str(data)

    message = str(data.get("text", data.get("message", "")))
    should_close = bool(data.get("shouldClose", False))
    return (ResponseDirective.END if should_close else ResponseDirective.CON), message


def _decode_generic_response(
    raw_body: str, protocol_errors: list[str]
) -> tuple[ResponseDirective, str]:
    stripped = raw_body.strip()
    if stripped.startswith("CON "):
        return ResponseDirective.CON, stripped[4:]
    if stripped.startswith("END "):
        return ResponseDirective.END, stripped[4:]
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        protocol_errors.append("Generic response must be JSON or start with 'CON '/'END '")
        return ResponseDirective.END, stripped

    if not isinstance(data, dict):
        protocol_errors.append("Generic JSON response must be an object")
        return ResponseDirective.END, str(data)

    raw_dir = str(data.get("directive", "END")).upper()
    directive = ResponseDirective.CON if raw_dir == "CON" else ResponseDirective.END
    message = str(data.get("message", ""))
    return directive, message
