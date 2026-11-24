"""3GPP TS 23.038 GSM-7 and UCS-2 encoding analyzer and USSD screen budget guard."""

from __future__ import annotations

from dataclasses import dataclass

# 3GPP TS 23.038 Section 6.2.1 — GSM 7-bit default alphabet (1 septet each)
GSM7_BASIC_CHARS: frozenset[str] = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)

# 3GPP TS 23.038 Section 6.2.1.1 — GSM 7-bit extension table (2 septets: 0x1B ESC + code)
GSM7_EXTENDED_CHARS: frozenset[str] = frozenset("\f^{}\\[~]|€")

# Common accidental Unicode punctuation/symbols that silently force UCS-2 on telco gateways
SAFE_GSM7_REPLACEMENTS: dict[str, str] = {
    "\u2018": "'",  # left single quotation mark
    "\u2019": "'",  # right single quotation mark
    "\u201c": '"',  # left double quotation mark
    "\u201d": '"',  # right double quotation mark
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2026": "...",  # horizontal ellipsis
    "\u00a0": " ",  # non-breaking space
    "\u200b": "",  # zero-width space
    "\u2022": "-",  # bullet
    "\u2192": "->",  # right arrow
    "\u00d7": "x",  # multiplication sign
}

# Standard USSD Phase 2 single-message payload limits (3GPP TS 23.038 / MAP)
DEFAULT_USSD_GSM7_MAX_SEPTETS = 182
STRICT_USSD_GSM7_MAX_SEPTETS = 160
DEFAULT_USSD_UCS2_MAX_UNITS = 80
STRICT_USSD_UCS2_MAX_UNITS = 70


@dataclass(frozen=True)
class PayloadEncodingReport:
    """Exact encoding and telco screen-budget analysis for a USSD/SMS string."""

    encoding: str  # "GSM-7" or "UCS-2"
    char_count: int
    unit_count: int  # septets for GSM-7, UTF-16 code units for UCS-2
    max_units: int
    overflow_units: int
    within_budget: bool
    extended_chars: tuple[str, ...]
    non_gsm7_chars: tuple[str, ...]
    gsm7_bytes_packed: int
    ucs2_bytes: int
    suggested_gsm7_text: str | None


def analyze_payload_encoding(
    text: str,
    *,
    strict_160: bool = False,
    gsm7_limit: int | None = None,
    ucs2_limit: int | None = None,
) -> PayloadEncodingReport:
    """Analyze a USSD menu or SMS string under 3GPP TS 23.038 GSM-7 / UCS-2 rules.

    Detects characters outside the GSM-7 basic/extension tables that force telco
    gateways to switch the entire screen to UCS-2 (UTF-16BE), cutting the screen
    budget from 182 (or 160) septets down to 80 (or 70) code units.
    """
    max_gsm7 = (
        gsm7_limit
        if gsm7_limit is not None
        else (STRICT_USSD_GSM7_MAX_SEPTETS if strict_160 else DEFAULT_USSD_GSM7_MAX_SEPTETS)
    )
    max_ucs2 = (
        ucs2_limit
        if ucs2_limit is not None
        else (STRICT_USSD_UCS2_MAX_UNITS if strict_160 else DEFAULT_USSD_UCS2_MAX_UNITS)
    )

    extended: list[str] = []
    non_gsm7: list[str] = []
    septets = 0

    for ch in text:
        if ch in GSM7_BASIC_CHARS:
            septets += 1
        elif ch in GSM7_EXTENDED_CHARS:
            septets += 2
            if ch not in extended:
                extended.append(ch)
        else:
            if ch not in non_gsm7:
                non_gsm7.append(ch)

    utf16_bytes = text.encode("utf-16-be")
    utf16_units = len(utf16_bytes) // 2

    if non_gsm7:
        encoding = "UCS-2"
        units = utf16_units
        limit = max_ucs2
        packed_gsm7_bytes = 0
        suggested = sanitize_to_gsm7(text)
    else:
        encoding = "GSM-7"
        units = septets
        limit = max_gsm7
        packed_gsm7_bytes = (septets * 7 + 7) // 8
        suggested = None

    overflow = max(0, units - limit)
    return PayloadEncodingReport(
        encoding=encoding,
        char_count=len(text),
        unit_count=units,
        max_units=limit,
        overflow_units=overflow,
        within_budget=units <= limit,
        extended_chars=tuple(extended),
        non_gsm7_chars=tuple(non_gsm7),
        gsm7_bytes_packed=packed_gsm7_bytes,
        ucs2_bytes=len(utf16_bytes),
        suggested_gsm7_text=suggested,
    )


def sanitize_to_gsm7(text: str) -> str:
    """Replace common typographic Unicode characters with GSM-7 equivalents."""
    out: list[str] = []
    for ch in text:
        if ch in GSM7_BASIC_CHARS or ch in GSM7_EXTENDED_CHARS:
            out.append(ch)
        elif ch in SAFE_GSM7_REPLACEMENTS:
            out.append(SAFE_GSM7_REPLACEMENTS[ch])
        else:
            # Drop unrepresentable symbols (e.g., emojis) rather than silently triggering UCS-2
            continue
    return "".join(out)
