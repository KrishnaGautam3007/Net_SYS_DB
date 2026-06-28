"""Unit tests for the NetSysDB paged storage engine."""

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.engine import PAGE_SIZE, StorageEngine  # noqa: E402


def _make_record(i: int) -> dict:
    """Build a metric record with randomized but representative values."""
    return {
        "machine_id": random.randint(1, 5),
        "timestamp": 1_700_000_000.0 + random.random() * 1_000_000,
        "cpu_percent": round(random.uniform(0, 100), 2),
        "ram_used_mb": round(random.uniform(0, 16000), 2),
        "ram_total_mb": 16000,
        "disk_read_kb": random.randint(0, 100000),
        "disk_write_kb": random.randint(0, 100000),
        "net_rx_kb": random.randint(0, 50000),
        "net_tx_kb": random.randint(0, 50000),
    }


def _assert_record_equal(written: dict, read_back: dict):
    assert read_back["machine_id"] == written["machine_id"]
    # cpu_percent and ram_used_mb are stored as 32-bit floats -> approx compare.
    assert read_back["cpu_percent"] == pytest.approx(written["cpu_percent"], rel=1e-5)
    assert read_back["ram_used_mb"] == pytest.approx(written["ram_used_mb"], rel=1e-5)
    # timestamp is a 64-bit double -> effectively exact.
    assert read_back["timestamp"] == pytest.approx(written["timestamp"], rel=1e-9)
    # integer fields are exact.
    for key in (
        "ram_total_mb",
        "disk_read_kb",
        "disk_write_kb",
        "net_rx_kb",
        "net_tx_kb",
    ):
        assert read_back[key] == written[key]


def test_500_record_roundtrip(tmp_path):
    """Insert 500 records and read each back by (page_id, offset)."""
    random.seed(1234)
    engine = StorageEngine(str(tmp_path))

    written = []  # list of (page_id, offset, record)
    for i in range(500):
        rec = _make_record(i)
        page_id, offset = engine.write(rec)
        written.append((page_id, offset, rec))

    for page_id, offset, rec in written:
        read_back = engine.read(page_id, offset)
        _assert_record_equal(rec, read_back)

    engine.close()


def test_scan_all_returns_all_records(tmp_path):
    """scan_all() returns exactly the number of records written."""
    random.seed(99)
    engine = StorageEngine(str(tmp_path))

    for i in range(500):
        engine.write(_make_record(i))

    scanned = engine.scan_all()
    assert len(scanned) == 500
    # Every scanned tuple is (page_id, offset, dict) and reads back consistently.
    for page_id, offset, rec in scanned:
        again = engine.read(page_id, offset)
        assert again == rec

    engine.close()


def test_db_file_created_and_paged(tmp_path):
    """The metrics.db file exists and is a whole number of 4 KiB pages."""
    engine = StorageEngine(str(tmp_path))
    for i in range(200):
        engine.write(_make_record(i))
    engine.close()

    db_path = os.path.join(str(tmp_path), "metrics.db")
    assert os.path.exists(db_path)
    size = os.path.getsize(db_path)
    assert size > 0
    assert size % PAGE_SIZE == 0


def test_persistence_across_reopen(tmp_path):
    """Records survive closing and reopening the engine."""
    random.seed(7)
    engine = StorageEngine(str(tmp_path))
    locs = [engine.write(_make_record(i)) for i in range(120)]
    engine.close()

    engine2 = StorageEngine(str(tmp_path))
    assert len(engine2.scan_all()) == 120
    # spot-check a record reads correctly after reopen
    pid, off = locs[0]
    assert "cpu_percent" in engine2.read(pid, off)
    engine2.close()
