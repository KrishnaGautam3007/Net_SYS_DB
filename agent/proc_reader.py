"""NetSysDB — /proc reader.

Reads live OS metrics by parsing the Linux ``/proc`` filesystem directly.
No third-party libraries (no psutil) are used anywhere in this module.

NOTE: ``/proc`` exists only on Linux. This module is designed to run inside
the Linux Docker containers (or under WSL). It will not work on a native
Windows host.

The disk and network readers are rate-based: they remember the previous
reading in module-level state and return deltas. The first call for each
returns zeros because there is no prior sample to diff against.
"""

import json
import os
import time

# Module-level state for delta-based readers (disk + network).
_last_disk = None  # (timestamp, reads, writes, sectors_read, sectors_written)
_last_net = None  # (timestamp, rx_bytes, tx_bytes)


def read_cpu() -> float:
    """Return total CPU utilization percentage as a float (2 decimals).

    Samples ``/proc/stat`` twice 0.5s apart and computes the busy fraction
    over the interval: ``100 * (1 - delta_idle / delta_total)``.
    """

    def _sample():
        with open("/proc/stat", "r") as fh:
            line = fh.readline()
        # Line looks like: "cpu  user nice system idle iowait irq softirq steal ..."
        parts = line.split()
        fields = [int(x) for x in parts[1:9]]  # user..steal (8 fields)
        idle = fields[3] + fields[4]  # idle + iowait
        total = sum(fields)
        return total, idle

    total1, idle1 = _sample()
    time.sleep(0.5)
    total2, idle2 = _sample()

    delta_total = total2 - total1
    delta_idle = idle2 - idle1
    if delta_total <= 0:
        return 0.0
    cpu_percent = 100.0 * (1.0 - (delta_idle / delta_total))
    return round(cpu_percent, 2)


def read_memory() -> dict:
    """Return memory usage in MB parsed from ``/proc/meminfo``."""
    info = {}
    with open("/proc/meminfo", "r") as fh:
        for line in fh:
            # Each line: "MemTotal:       16384000 kB"
            key, _, rest = line.partition(":")
            value_kb = int(rest.strip().split()[0])
            info[key] = value_kb

    total_mb = info.get("MemTotal", 0) // 1024
    available_mb = info.get("MemAvailable", 0) // 1024
    used_mb = total_mb - available_mb
    swap_total_mb = info.get("SwapTotal", 0) // 1024
    swap_free_mb = info.get("SwapFree", 0) // 1024
    swap_used_mb = swap_total_mb - swap_free_mb

    return {
        "total_mb": total_mb,
        "used_mb": used_mb,
        "available_mb": available_mb,
        "swap_used_mb": swap_used_mb,
    }


def read_processes() -> list:
    """Return the top 5 processes by resident memory (VmRSS).

    Iterates numeric directories under ``/proc``. Processes whose files
    vanish mid-read (they exited) are skipped.
    """
    procs = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            name = None
            state = None
            vmrss_kb = 0
            with open(f"/proc/{pid}/status", "r") as fh:
                for line in fh:
                    if line.startswith("Name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("State:"):
                        state = line.split(":", 1)[1].strip().split()[0]
                    elif line.startswith("VmRSS:"):
                        vmrss_kb = int(line.split(":", 1)[1].strip().split()[0])

            # Read /proc/[pid]/stat for utime (field 14) + stime (field 15).
            # The comm field (field 2) may contain spaces/parens, so split on
            # the last ')'. After that, field N maps to tokens[N-3].
            with open(f"/proc/{pid}/stat", "r") as fh:
                stat = fh.read()
            rpar = stat.rindex(")")
            after = stat[rpar + 2 :].split()
            _cpu_ticks = int(after[11]) + int(after[12])  # utime + stime

            if name is None:
                continue
            procs.append(
                {
                    "pid": pid,
                    "name": name,
                    "ram_mb": round(vmrss_kb / 1024, 2),
                    "state": state or "?",
                }
            )
        except (OSError, ValueError, IndexError):
            # Process exited mid-read or malformed entry — skip it.
            continue

    procs.sort(key=lambda p: p["ram_mb"], reverse=True)
    return procs[:5]


def read_disk() -> dict:
    """Return disk I/O rates from ``/proc/diskstats`` (delta since last call).

    NOTE: The kernel ``/proc/diskstats`` layout (whitespace-split, 0-based) is
    used directly: index 2 = device name, 3 = reads completed, 5 = sectors
    read, 7 = writes completed, 9 = sectors written. (The master spec's field
    numbers were inconsistent with the real layout, so the actual kernel field
    positions are used here.) One sector = 512 bytes.

    Returns zeros on the first call.
    """
    global _last_disk
    now = time.time()
    target = None
    with open("/proc/diskstats", "r") as fh:
        lines = fh.readlines()

    for pref in ("sda", "vda", "xvda"):
        for line in lines:
            parts = line.split()
            if len(parts) >= 10 and parts[2] == pref:
                target = parts
                break
        if target is not None:
            break

    if target is None:
        return {"reads_per_sec": 0, "writes_per_sec": 0, "read_kb": 0, "write_kb": 0}

    reads = int(target[3])
    sectors_read = int(target[5])
    writes = int(target[7])
    sectors_written = int(target[9])

    if _last_disk is None:
        _last_disk = (now, reads, writes, sectors_read, sectors_written)
        return {"reads_per_sec": 0, "writes_per_sec": 0, "read_kb": 0, "write_kb": 0}

    last_t, last_r, last_w, last_sr, last_sw = _last_disk
    elapsed = max(now - last_t, 1e-6)
    d_reads = max(reads - last_r, 0)
    d_writes = max(writes - last_w, 0)
    d_sr = max(sectors_read - last_sr, 0)
    d_sw = max(sectors_written - last_sw, 0)

    _last_disk = (now, reads, writes, sectors_read, sectors_written)
    return {
        "reads_per_sec": int(d_reads / elapsed),
        "writes_per_sec": int(d_writes / elapsed),
        "read_kb": int(d_sr * 512 / 1024),
        "write_kb": int(d_sw * 512 / 1024),
    }


def read_network() -> dict:
    """Return network throughput from ``/proc/net/dev`` (delta since last call).

    Sums rx/tx bytes across all interfaces except loopback (``lo``). Returns
    zeros on the first call.
    """
    global _last_net
    now = time.time()
    rx_total = 0
    tx_total = 0
    with open("/proc/net/dev", "r") as fh:
        lines = fh.readlines()

    for line in lines[2:]:  # skip the two header lines
        name, _, rest = line.partition(":")
        name = name.strip()
        if name == "lo" or not rest:
            continue
        fields = rest.split()
        if len(fields) < 9:
            continue
        rx_total += int(fields[0])  # rx_bytes
        tx_total += int(fields[8])  # tx_bytes

    if _last_net is None:
        _last_net = (now, rx_total, tx_total)
        return {"rx_kb": 0, "tx_kb": 0}

    _last_t, last_rx, last_tx = _last_net
    d_rx = max(rx_total - last_rx, 0)
    d_tx = max(tx_total - last_tx, 0)
    _last_net = (now, rx_total, tx_total)
    return {"rx_kb": int(d_rx / 1024), "tx_kb": int(d_tx / 1024)}


if __name__ == "__main__":
    print("NetSysDB proc_reader — sampling every 5 seconds (Ctrl+C to stop)")
    while True:
        snapshot = {
            "cpu_percent": read_cpu(),
            "memory": read_memory(),
            "processes": read_processes(),
            "disk": read_disk(),
            "network": read_network(),
        }
        print(json.dumps(snapshot, indent=2))
        time.sleep(5)
