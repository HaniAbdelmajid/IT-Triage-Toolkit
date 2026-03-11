"""
SupportTriage
Run it once and it generates a full IT support report bundle.
This helps you save time from doing it manually, which is crucial to save time and pinpoint what the issue was.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Tuple


try:
    import psutil  # type: ignore
    HAS_PSUTIL = True
except Exception:
    psutil = None
    HAS_PSUTIL = False


def setup_logging(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    log_path = out_dir / "support_tool.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    logging.info("Logging initialized.")
    return log_path


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def run_cmd(cmd: List[str], timeout: int = 10) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except Exception as e:
        return 1, f"Command failed: {e}"


def ping(host: str, count: int = 2, timeout_sec: int = 2) -> Dict[str, Any]:
    system = platform.system().lower()

    if "windows" in system:
        cmd = ["ping", "-n", str(count), "-w", str(timeout_sec * 1000), host]
    else:
        cmd = ["ping", "-c", str(count), "-W", str(timeout_sec), host]

    code, out = run_cmd(cmd, timeout=timeout_sec * count + 5)

    return {
        "host": host,
        "ok": (code == 0),
        "raw": out[:2000],
    }


def dns_resolve(name: str) -> Dict[str, Any]:
    try:
        infos = socket.getaddrinfo(name, None)
        ips = sorted({info[4][0] for info in infos})
        return {"name": name, "ok": True, "ips": ips}
    except Exception as e:
        return {"name": name, "ok": False, "error": str(e)}


def human_bytes(num: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    for u in units:
        if num < 1024 or u == units[-1]:
            return f"{num:.2f} {u}"
        num /= 1024
    return f"{num:.2f} B"


def check_tcp_port(host: str, port: int, timeout: int = 2) -> Dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"host": host, "port": port, "ok": True}
    except Exception as e:
        return {"host": host, "port": port, "ok": False, "error": str(e)}


def collect_basic_system() -> Dict[str, Any]:
    logging.info("Collecting basic system info...")

    info: Dict[str, Any] = {
        "hostname": socket.gethostname(),
        "user": os.getenv("USERNAME") or os.getenv("USER") or "unknown",
        "os": platform.platform(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
    }

    if HAS_PSUTIL:
        boot = dt.datetime.fromtimestamp(psutil.boot_time())
        info["boot_time"] = boot.isoformat()
        info["uptime_hours"] = round((dt.datetime.now() - boot).total_seconds() / 3600, 2)
    else:
        info["boot_time"] = "psutil not installed"
        info["uptime_hours"] = "psutil not installed"

    return info


def collect_performance() -> Dict[str, Any]:
    logging.info("Collecting performance info...")

    perf: Dict[str, Any] = {}

    if HAS_PSUTIL:
        perf["cpu_logical_cores"] = psutil.cpu_count(logical=True)
        perf["cpu_physical_cores"] = psutil.cpu_count(logical=False)
        perf["cpu_percent_1s"] = psutil.cpu_percent(interval=1)

        vm = psutil.virtual_memory()
        perf["memory_total"] = human_bytes(vm.total)
        perf["memory_used"] = human_bytes(vm.used)
        perf["memory_available"] = human_bytes(vm.available)
        perf["memory_percent"] = vm.percent

        disks: List[Dict[str, Any]] = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append(
                    {
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total": human_bytes(usage.total),
                        "used": human_bytes(usage.used),
                        "free": human_bytes(usage.free),
                        "percent": usage.percent,
                    }
                )
            except Exception:
                continue
        perf["disks"] = disks

        processes: List[Dict[str, Any]] = []
        for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info"]):
            try:
                mem = p.info.get("memory_info").rss if p.info.get("memory_info") else 0
                processes.append(
                    {
                        "pid": p.info.get("pid"),
                        "name": p.info.get("name"),
                        "user": p.info.get("username"),
                        "cpu_percent": p.info.get("cpu_percent"),
                        "rss": human_bytes(float(mem)),
                    }
                )
            except Exception:
                continue

        processes.sort(key=lambda x: float(x["rss"].split()[0]), reverse=True)
        perf["top_processes_by_memory"] = processes[:10]
    else:
        perf["note"] = "Install psutil to enable CPU/RAM/Disk/Process details."

    return perf


def collect_network() -> Dict[str, Any]:
    logging.info("Collecting network info...")

    net: Dict[str, Any] = {}

    if HAS_PSUTIL:
        addrs = psutil.net_if_addrs()
        iface_summary: Dict[str, Any] = {}

        for iface, addr_list in addrs.items():
            ips = []
            macs = []

            for a in addr_list:
                if getattr(a, "family", None) == socket.AF_INET or str(getattr(a, "family", "")).endswith("AF_INET"):
                    ips.append(a.address)

                if "AF_LINK" in str(getattr(a, "family", "")) or "AF_PACKET" in str(getattr(a, "family", "")):
                    macs.append(a.address)

            iface_summary[iface] = {"ipv4": ips, "mac": macs}

        net["interfaces"] = iface_summary
    else:
        net["interfaces"] = "psutil not installed"

    net["dns_google"] = dns_resolve("google.com")

    net["ping_gateway_like"] = ping("1.1.1.1")
    net["ping_google_dns"] = ping("8.8.8.8")
    net["ping_google"] = ping("google.com")

    net["port_checks"] = []
    for host, port in [("google.com", 443), ("google.com", 80)]:
        net["port_checks"].append(check_tcp_port(host, port, timeout=2))

    return net


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    items: Dict[str, Any] = {}

    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        elif isinstance(v, list):
            items[new_key] = json.dumps(v, ensure_ascii=False)
        else:
            items[new_key] = v

    return items


def write_json(report: Dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(f"Wrote JSON report: {path}")


def write_csv(report: Dict[str, Any], path: Path) -> None:
    flat = flatten_dict(report)

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "value"])
        for k, v in flat.items():
            w.writerow([k, v])

    logging.info(f"Wrote CSV report: {path}")


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&#039;")
    )


def write_html(report: Dict[str, Any], path: Path) -> None:
    def to_pre(obj: Any) -> str:
        return "<pre>" + html_escape(json.dumps(obj, indent=2, ensure_ascii=False)) + "</pre>"

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Support Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    h1 {{ margin-bottom: 0; }}
    .meta {{ color: #444; margin-top: 6px; }}
    section {{ margin-top: 18px; padding: 14px; border: 1px solid #ddd; border-radius: 10px; }}
    pre {{ background: #f7f7f7; padding: 12px; border-radius: 10px; overflow-x: auto; }}
    .small {{ font-size: 12px; color: #666; }}
  </style>
</head>
<body>
  <h1>IT Support Report</h1>
  <div class="meta">Generated: {html_escape(report.get("generated_at",""))}</div>
  <div class="small">psutil installed: {HAS_PSUTIL}</div>

  <section>
    <h2>System</h2>
    {to_pre(report.get("system", {}))}
  </section>

  <section>
    <h2>Network</h2>
    {to_pre(report.get("network", {}))}
  </section>

  <section>
    <h2>Performance</h2>
    {to_pre(report.get("performance", {}))}
  </section>

</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    logging.info(f"Wrote HTML report: {path}")


def build_report(mode: str) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "system": {},
        "network": {},
        "performance": {},
    }

    report["system"] = collect_basic_system()

    if mode in ("network", "full"):
        report["network"] = collect_network()

    if mode in ("performance", "full"):
        report["performance"] = collect_performance()

    return report


def print_summary(report: Dict[str, Any]) -> None:
    sysinfo = report.get("system", {})
    net = report.get("network", {})
    perf = report.get("performance", {})

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    print(f"Host: {sysinfo.get('hostname')} | OS: {sysinfo.get('os')}")
    print(f"User: {sysinfo.get('user')} | Uptime(h): {sysinfo.get('uptime_hours')}")

    if net:
        print(f"DNS google.com: {net.get('dns_google', {}).get('ok')}")
        print(f"Ping 1.1.1.1: {net.get('ping_gateway_like', {}).get('ok')}")
        print(f"Ping google.com: {net.get('ping_google', {}).get('ok')}")

    if perf and HAS_PSUTIL:
        print(f"CPU% (1s): {perf.get('cpu_percent_1s')} | RAM%: {perf.get('memory_percent')}")

    print("=" * 60 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="support_toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """
            SupportTriage

            Default behavior: runs FULL checks and generates reports.
            You can still choose a smaller mode if you want.

            Examples:
              python support_toolkit.py
              python support_toolkit.py --mode quick
              python support_toolkit.py --mode network
              python support_toolkit.py --mode performance
            """
        ).strip(),
    )

    parser.add_argument(
        "--mode",
        choices=["quick", "network", "performance", "full"],
        default="full",
        help="Defaults to full. Use quick/network/performance if you want shorter runs.",
    )
    parser.add_argument(
        "--out",
        default="reports",
        help="Output folder for reports/logs.",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Skip HTML output.",
    )

    args = parser.parse_args()

    out_dir = Path(args.out)
    setup_logging(out_dir)

    logging.info(f"Starting Support Toolkit | mode={args.mode} | out={out_dir.resolve()}")

    if not HAS_PSUTIL:
        logging.warning("psutil not found. For best results: py -m pip install psutil")

    report = build_report(args.mode)

    stamp = now_stamp()
    base = out_dir / f"support_report_{args.mode}_{stamp}"

    write_json(report, base.with_suffix(".json"))
    write_csv(report, base.with_suffix(".csv"))

    if not args.no_html:
        write_html(report, base.with_suffix(".html"))

    print_summary(report)

    # This line makes it super obvious where your files went which can be helpfully if it went somewhere you cant find it
    print(f"Saved reports to: {out_dir.resolve()}")

    logging.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())