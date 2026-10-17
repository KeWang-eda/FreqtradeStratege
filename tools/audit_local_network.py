"""Run local research/backtests under a process-local network audit policy.

Reference contracts: Freqtrade 2026.7 Exchange.reload_markets and IFreqaiModel.start;
CCXT 4.5.75 Binance.fetch_markets; Python sys.addaudithook socket events.
No installed framework files, TLS settings or global proxy settings are changed.
"""

import argparse
import ipaddress
import json
import socket
import sys
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class NetworkDenied(OSError):
    """The audit policy denied an attempted network operation."""


def install_policy(policy: str, report: dict[str, Any]) -> None:
    """Block all networking or permit only Binance exchangeInfo over loopback proxy.

    HTTP is checked at requests/aiohttp entry points; socket audit events also
    reject direct external TCP/DNS, including code outside these HTTP libraries.
    This instrumentation is for diagnosis, never for live/dry-run execution.
    """
    allowed = {
        ("api.binance.com", "/api/v3/exchangeInfo"),
        ("fapi.binance.com", "/fapi/v1/exchangeInfo"),
        ("dapi.binance.com", "/dapi/v1/exchangeInfo"),
    }

    def check_http(method: str, url: Any) -> None:
        parsed = urlsplit(str(url))
        permit = (
            policy == "metadata-only"
            and method.upper() == "GET"
            and parsed.scheme == "https"
            and (parsed.hostname, parsed.path) in allowed
        )
        report["http_requests"].append(
            {
                "method": method.upper(),
                "host": parsed.hostname,
                "path": parsed.path,
                "allowed": permit,
            }
        )
        if not permit:
            raise NetworkDenied(f"Audit denied HTTP {method} {parsed.hostname}{parsed.path}")

    def loopback(host: Any) -> bool:
        if host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def socket_audit(event: str, args: tuple) -> None:
        if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"}:
            host, port = args[0], args[1] if event == "socket.getaddrinfo" else None
        elif event in {"socket.connect", "socket.sendto"} and args[0].family in {
            socket.AF_INET,
            socket.AF_INET6,
        }:
            host, port = args[1][:2]
        else:
            return
        permit = policy == "metadata-only" and loopback(host)
        report["socket_events"].append(
            {"event": event, "host": str(host), "port": port, "allowed": permit}
        )
        if not permit:
            raise NetworkDenied(f"Audit denied {event} to {host}:{port}")

    sys.addaudithook(socket_audit)
    import aiohttp
    import requests

    original_sync = requests.Session.request
    original_async = aiohttp.ClientSession._request

    def request(session: Any, method: str, url: Any, *args: Any, **kwargs: Any) -> Any:
        check_http(method, url)
        return original_sync(session, method, url, *args, **kwargs)

    async def async_request(
        session: Any, method: str, str_or_url: Any, *args: Any, **kwargs: Any
    ) -> Any:
        check_http(method, str_or_url)
        return await original_async(session, method, str_or_url, *args, **kwargs)

    requests.Session.request = request
    aiohttp.ClientSession._request = async_request


def main(argv: list[str] | None = None) -> int:
    """Audit one process; preserve its exit code and write a JSON evidence report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", choices=("deny-all", "metadata-only"), required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("component", choices=("research", "freqtrade", "offline-backtest"))
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    arguments = args.arguments
    if arguments and arguments[0] == "--":
        arguments = arguments[1:]
    if args.component == "freqtrade" and (not arguments or arguments[0] != "backtesting"):
        parser.error("This diagnostic tool supports freqtrade backtesting only")
    if args.component == "offline-backtest" and (not arguments or arguments[0] != "backtesting"):
        parser.error("Offline diagnostic supports historical backtesting only (no capture)")
    report: dict[str, Any] = {
        "policy": args.policy,
        "component": args.component,
        "arguments": arguments,
        "http_requests": [],
        "socket_events": [],
    }
    install_policy(args.policy, report)
    code = 2
    try:
        if args.component == "research":
            from quant_strategy.cli import main as run
        elif args.component == "offline-backtest":
            from quant_strategy.execution.offline_backtest import main as run
        else:
            from freqtrade.main import main as run
        returned = run(arguments)
        code = 0 if returned is None else int(returned)
    except SystemExit as exc:
        code = int(exc.code or 0)
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        code = 1
        traceback.print_exc()
    finally:
        report["exit_code"] = code
        report["denied_operations"] = sum(
            not item["allowed"]
            for key in ("http_requests", "socket_events")
            for item in report[key]
        )
        report["freqtrade_imported"] = "freqtrade" in sys.modules
        report["ccxt_imported"] = "ccxt" in sys.modules
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
