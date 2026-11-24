"""Tests for 3GPP TS 23.038 GSM-7 and UCS-2 payload encoding & screen budget checks."""

from __future__ import annotations

from ussdkit.encoding import analyze_payload_encoding, sanitize_to_gsm7


def test_gsm7_basic_ascii_stays_in_budget() -> None:
    screen = "Welcome to Wallet\n1. Check Balance\n2. Send Money\n0. Exit"
    rep = analyze_payload_encoding(screen)
    assert rep.encoding == "GSM-7"
    assert rep.unit_count == len(screen)
    assert rep.within_budget is True
    assert rep.overflow_units == 0
    assert rep.non_gsm7_chars == ()
    assert rep.suggested_gsm7_text is None


def test_gsm7_extension_table_characters_consume_two_septets() -> None:
    screen = "Fee: €5 [promo] {ok}"
    rep = analyze_payload_encoding(screen)
    assert rep.encoding == "GSM-7"
    # €, [, ], {, } are 5 extended characters -> +5 escape septets
    assert rep.unit_count == len(screen) + 5
    assert set(rep.extended_chars) == {"€", "[", "]", "{", "}"}


def test_single_curly_apostrophe_triggers_ucs2_cliff_and_suggests_fix() -> None:
    # 90 chars: fits easily in GSM-7 (182), overflows UCS-2 (80) due to a single smart apostrophe
    screen = "Welcome to Farmer\u2019s Cooperative Wallet! Select: 1. Balance 2. Loans 3. Harvest Prices 4. Help"
    assert len(screen) > 80
    rep = analyze_payload_encoding(screen)
    assert rep.encoding == "UCS-2"
    assert rep.max_units == 80
    assert rep.within_budget is False
    assert "\u2019" in rep.non_gsm7_chars
    assert rep.suggested_gsm7_text is not None
    fixed = analyze_payload_encoding(rep.suggested_gsm7_text)
    assert fixed.encoding == "GSM-7"
    assert fixed.within_budget is True


def test_strict_160_and_emoji_surrogate_pair_units() -> None:
    # Surrogate-pair emoji takes 2 UTF-16 code units in UCS-2
    rep = analyze_payload_encoding("Pay now 💰", strict_160=True)
    assert rep.encoding == "UCS-2"
    assert rep.max_units == 70
    assert rep.unit_count == len("Pay now ") + 2
    assert sanitize_to_gsm7("Pay now 💰") == "Pay now "


def test_gsm7_overflow_detected_accurately() -> None:
    long_menu = "A" * 190
    rep = analyze_payload_encoding(long_menu)
    assert rep.encoding == "GSM-7"
    assert rep.within_budget is False
    assert rep.overflow_units == 8
    rep_strict = analyze_payload_encoding("A" * 165, strict_160=True)
    assert rep_strict.within_budget is False
    assert rep_strict.overflow_units == 5
