"""ussdkit — Stateful USSD emulator, GSM-7/UCS-2 budget guard, crawler, and telco chaos suite."""

from ussdkit.chaos import UssdChaosRunner
from ussdkit.crawler import UssdTreeCrawler, extract_menu_options
from ussdkit.emulator import (
    DEFAULT_TELCO_SESSION_TIMEOUT_S,
    CallableTransport,
    HttpTransport,
    UssdSession,
    UssdSessionTimeoutError,
    UssdTransport,
)
from ussdkit.encoding import (
    DEFAULT_USSD_GSM7_MAX_SEPTETS,
    DEFAULT_USSD_UCS2_MAX_UNITS,
    GSM7_BASIC_CHARS,
    GSM7_EXTENDED_CHARS,
    STRICT_USSD_GSM7_MAX_SEPTETS,
    STRICT_USSD_UCS2_MAX_UNITS,
    PayloadEncodingReport,
    analyze_payload_encoding,
    sanitize_to_gsm7,
)
from ussdkit.gateways import EncodedHttpRequest, decode_gateway_response, encode_gateway_request
from ussdkit.models import (
    ChaosCaseResult,
    ChaosReport,
    CrawlNode,
    CrawlReport,
    GatewayFormat,
    ResponseDirective,
    SessionTurn,
    Severity,
    UssdFinding,
    UssdRequest,
    UssdResponse,
)
from ussdkit.reporting import (
    chaos_report_to_json,
    crawl_report_to_json,
    crawl_report_to_markdown,
    findings_to_sarif,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_TELCO_SESSION_TIMEOUT_S",
    "DEFAULT_USSD_GSM7_MAX_SEPTETS",
    "DEFAULT_USSD_UCS2_MAX_UNITS",
    "GSM7_BASIC_CHARS",
    "GSM7_EXTENDED_CHARS",
    "STRICT_USSD_GSM7_MAX_SEPTETS",
    "STRICT_USSD_UCS2_MAX_UNITS",
    "CallableTransport",
    "ChaosCaseResult",
    "ChaosReport",
    "CrawlNode",
    "CrawlReport",
    "EncodedHttpRequest",
    "GatewayFormat",
    "HttpTransport",
    "PayloadEncodingReport",
    "ResponseDirective",
    "SessionTurn",
    "Severity",
    "UssdChaosRunner",
    "UssdFinding",
    "UssdRequest",
    "UssdResponse",
    "UssdSession",
    "UssdSessionTimeoutError",
    "UssdTransport",
    "UssdTreeCrawler",
    "__version__",
    "analyze_payload_encoding",
    "chaos_report_to_json",
    "crawl_report_to_json",
    "crawl_report_to_markdown",
    "decode_gateway_response",
    "encode_gateway_request",
    "extract_menu_options",
    "findings_to_sarif",
    "sanitize_to_gsm7",
]
