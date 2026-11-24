"""Tests for Africa's Talking, Hubtel, Infobip, and generic USSD gateway codecs."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

from ussdkit.gateways import decode_gateway_response, encode_gateway_request
from ussdkit.models import GatewayFormat, ResponseDirective, UssdRequest


def _sample_req(turn_index: int = 0, text: str = "", latest: str = "") -> UssdRequest:
    return UssdRequest(
        session_id="sess-001",
        phone_number="+256772111222",
        service_code="*384#",
        text=text,
        latest_input=latest,
        network_code="64110",
        turn_index=turn_index,
    )


def test_africastalking_encode_and_decode() -> None:
    enc = encode_gateway_request(_sample_req(1, "1*5000", "5000"), GatewayFormat.AFRICASTALKING)
    assert enc.content_type == "application/x-www-form-urlencoded"
    parsed = parse_qs(enc.body.decode())
    assert parsed["sessionId"] == ["sess-001"]
    assert parsed["text"] == ["1*5000"]

    ok_con = decode_gateway_response("CON Choose option:\n1. Yes", GatewayFormat.AFRICASTALKING)
    assert ok_con.directive == ResponseDirective.CON
    assert ok_con.protocol_errors == ()

    bad = decode_gateway_response("Hello without prefix", GatewayFormat.AFRICASTALKING)
    assert bad.directive == ResponseDirective.END
    assert len(bad.protocol_errors) == 1


def test_hubtel_encode_and_decode() -> None:
    init_req = encode_gateway_request(_sample_req(0), GatewayFormat.HUBTEL)
    init_json = json.loads(init_req.body.decode())
    assert init_json["Type"] == "Initiation"
    assert init_json["Mobile"] == "256772111222"

    resp_req = encode_gateway_request(_sample_req(1, "2", "2"), GatewayFormat.HUBTEL)
    resp_json = json.loads(resp_req.body.decode())
    assert resp_json["Type"] == "Response"
    assert resp_json["Message"] == "2"

    con_res = decode_gateway_response(
        json.dumps({"Type": "Response", "Message": "1. Balance"}),
        GatewayFormat.HUBTEL,
    )
    assert con_res.directive == ResponseDirective.CON
    assert con_res.message == "1. Balance"

    end_res = decode_gateway_response(
        json.dumps({"Type": "Release", "Message": "Done"}),
        GatewayFormat.HUBTEL,
    )
    assert end_res.directive == ResponseDirective.END


def test_infobip_and_generic_codecs() -> None:
    ib = encode_gateway_request(_sample_req(0), GatewayFormat.INFOBIP)
    assert json.loads(ib.body.decode())["type"] == "INITIAL"
    ib_resp = decode_gateway_response(
        json.dumps({"text": "Welcome", "shouldClose": False}),
        GatewayFormat.INFOBIP,
    )
    assert ib_resp.directive == ResponseDirective.CON

    gen_resp = decode_gateway_response(
        json.dumps({"directive": "END", "message": "Goodbye"}),
        GatewayFormat.GENERIC,
    )
    assert gen_resp.directive == ResponseDirective.END
    assert gen_resp.message == "Goodbye"
