# SupportTriage

SupportTriage is a small Python tool I built to speed up the “first 2 minutes” of IT troubleshooting.  
Instead of manually checking DNS, pinging things, and gathering system info one-by-one, this script runs a full triage pass and saves everything into clean, shareable reports.

It’s meant to be simple: run it once, get a report bundle you can screenshot, attach, or use for escalation.

## What it collects

### System basics
- Hostname, OS version, user, architecture, Python version
- Boot time + uptime (only if `psutil` is installed)

### Network checks
- DNS resolution test (resolves `google.com`)
- ICMP reachability (ping `1.1.1.1`, `8.8.8.8`, and `google.com`)
- TCP connectivity validation (checks ports 80/443 to confirm web traffic works even if ping is blocked)

### Performance checks (optional but recommended)
- CPU usage, memory usage, disk usage, and top memory processes  
- Requires `psutil`

## Output files

Every run creates a small “report bundle” inside the output folder (default is `./reports`):
- `support_report_<mode>_<timestamp>.json`  (full structured report)
- `support_report_<mode>_<timestamp>.csv`   (easy-to-skim key/value)
- `support_report_<mode>_<timestamp>.html`  (printable report)
- `support_tool.log`                        (timestamped run log)

## Requirements
- Python 3.10+ recommended  
- Optional (recommended): `psutil`

Install psutil:
```bash
py -m pip install psutil
