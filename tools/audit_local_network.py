"""Run local research/backtests under a process-local network audit policy.

Reference contracts: Freqtrade 2026.7 Exchange.reload_markets and IFreqaiModel.start;
CCXT 4.5.75 Binance.fetch_markets; Python sys.addaudithook socket events.
No installed framework files, TLS settings or global proxy settings are changed.
"""

import argparse
import ipaddress
import json
import shutil
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

    HTTP is checked at requests/aiohttp entry points; Python socket audit events
    reject TCP/UDP/DNS. Child creation is rejected except exact local Git provenance
    queries with fsmonitor/external diff/textconv disabled; all are recorded.
    Native libraries can bypass Python hooks: use a network namespace and strace
    for OS isolation/evidence, rather than claiming this hook covers C syscalls.
    This instrumentation is for diagnosis, never for live/dry-run execution.
    """
    allowed = {
        ("api.binance.com", "/api/v3/exchangeInfo"),
        ("fapi.binance.com", "/fapi/v1/exchangeInfo"),
        ("dapi.binance.com", "/dapi/v1/exchangeInfo"),
    }
    git = shutil.which("git")
    git_prefix = [
        git,
        "--no-pager",
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(Path(__file__).resolve().parents[1]),
    ]
    local_queries = [
        [*git_prefix, "rev-parse", "HEAD"],
        [*git_prefix, "status", "--porcelain"],
        [*git_prefix, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD"],
    ]

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
        if event in {
            "subprocess.Popen",
            "os.system",
            "os.posix_spawn",
            "os.exec",
            "os.fork",
            "os.forkpty",
        }:
            permit = (
                event == "subprocess.Popen"
                and git is not None
                and args[0] == git
                and args[1] in local_queries
            )
            report.setdefault("process_events", []).append(
                {
                    "event": event,
                    "allowed": permit,
                    "executable": str(args[0]) if args else None,
                    "scope": "fixed local Git provenance query" if permit else "unaudited child",
                }
            )
            if not permit:
                raise NetworkDenied(f"Audit denied unaudited child process: {event}")
            return
        if event == "socket.getnameinfo":
            host, port = args[0][:2]
        elif event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"}:
            host, port = args[0], args[1] if event == "socket.getaddrinfo" else None
        elif event in {"socket.connect", "socket.sendto", "socket.sendmsg"} and args[0].family in {
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
        "process_events": [],
        "completed": False,
    }
    code = 2
    try:
        install_policy(args.policy, report)
        if args.component == "research":
            from quant_strategy.cli import main as run
        elif args.component == "offline-backtest":
            from quant_strategy.execution.offline_backtest import main as run
        else:
            from freqtrade.main import main as run
        returned = run(arguments)
        code = 0 if returned is None else int(returned)
        report["completed"] = True
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        report["completed"] = True
    except KeyboardInterrupt:
        code = 130
        report["error"] = {"type": "KeyboardInterrupt", "message": "Interrupted"}
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
        code = 1
        traceback.print_exc()
    finally:
        report["denied_operations"] = sum(
            not item["allowed"]
            for key in ("http_requests", "socket_events", "process_events")
            for item in report[key]
        )
        if code == 0 and report["denied_operations"]:
            code = 3
        report["exit_code"] = code
        report["freqtrade_imported"] = "freqtrade" in sys.modules
        report["ccxt_imported"] = "ccxt" in sys.modules
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
