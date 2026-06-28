#!/usr/bin/env python
"""NetSysDB — manual alert injection tool.

Create and resolve alerts for testing without waiting for metric thresholds.

Examples:
  python tools/inject_alert.py --machine node-1 --severity HIGH --message "disk failing"
  python tools/inject_alert.py --list
  python tools/inject_alert.py --resolve <alert_id>
"""

import argparse
import json
import sys

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed. Run: pip install requests")
    sys.exit(1)


def create_alert(host, port, machine, severity, message):
    """Create a manual alert."""
    url = f"http://{host}:{port}/api/alerts/create"
    payload = {"machine": machine, "severity": severity, "message": message}
    try:
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f"[OK] Alert created: {data['alert_id']}")
            print(f"     Machine: {machine}")
            print(f"     Severity: {severity}")
            return data["alert_id"]
        else:
            print(f"[ERR] Failed: {resp.status_code} {resp.text}")
            return None
    except Exception as e:
        print(f"[ERR] Error: {e}")
        return None


def resolve_alert(host, port, alert_id):
    """Resolve a manual alert."""
    url = f"http://{host}:{port}/api/alerts/{alert_id}/resolve"
    try:
        resp = requests.post(url, timeout=5)
        if resp.status_code == 200:
            print(f"[OK] Alert resolved: {alert_id}")
            return True
        else:
            print(f"[ERR] Failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"[ERR] Error: {e}")
        return False


def list_alerts(host, port):
    """List all open alerts."""
    url = f"http://{host}:{port}/api/alerts"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            alerts = resp.json()
            open_alerts = [a for a in alerts if a.get("resolved_at") is None]
            if not open_alerts:
                print("No open alerts.")
                return
            print(f"Open alerts ({len(open_alerts)}):")
            for a in open_alerts:
                print(
                    f"  {a['id'][:8]}... | {a['machine']:20s} | {a['rule']:15s} | {a['severity']}"
                )
        else:
            print(f"✗ Failed: {resp.status_code}")
    except Exception as e:
        print(f"✗ Error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Manually create or resolve alerts for testing"
    )
    parser.add_argument(
        "--host", default="localhost", help="Collector host (default: localhost)"
    )
    parser.add_argument(
        "--port", type=int, default=5000, help="Collector port (default: 5000)"
    )
    parser.add_argument("--machine", help="Machine name (for create)")
    parser.add_argument(
        "--severity",
        choices=["HIGH", "MEDIUM", "LOW"],
        default="MEDIUM",
        help="Alert severity (default: MEDIUM)",
    )
    parser.add_argument("--message", help="Alert message (for create)")
    parser.add_argument(
        "--list", action="store_true", help="List all open alerts"
    )
    parser.add_argument("--resolve", help="Resolve alert by ID")

    args = parser.parse_args()

    if args.list:
        list_alerts(args.host, args.port)
    elif args.resolve:
        resolve_alert(args.host, args.port, args.resolve)
    elif args.machine:
        create_alert(
            args.host, args.port, args.machine, args.severity, args.message or ""
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
