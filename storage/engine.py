"""NetSysDB — page-based binary storage engine.

Metrics are stored in fixed-size 4 KiB pages inside a single file
(``metrics.db``). Each page has a 32-byte header followed by tightly packed
44-byte records. A separate ``pages.bitmap`` file tracks, one byte per page,
whether a page still has free space (0) or is full (1).

No external database is used — everything is hand-packed with ``struct``.

WAL integration (crash safety) is layered on in Phase 5; this module exposes
the raw page read/write/scan primitives.
"""

import os
import struct

from storage.wal import WAL

PAGE_SIZE = 4096
HEADER_SIZE = 32
DATA_START = 32
RECORD_SIZE = 44
MAX_DATA = PAGE_SIZE - HEADER_SIZE - 44  # usable bytes, leaving a 44B tail margin
RECORD_FORMAT = (
    "!QdffIIIII"  # machine_id, ts, cpu, ram_used, ram_total, dr, dw, nrx, ntx
)
MAGIC_PAGE = 0xB00BFACE

# Page header: magic(I) page_id(I) record_count(H) free_offset(H) flags(B) reserved(19s)
_PAGE_HEADER_FORMAT = "!IIHHB19s"
_RESERVED = b"\x00" * 19

# Order of fields in a packed record, used to build the result dict.
_RECORD_FIELDS = (
    "machine_id",
    "timestamp",
    "cpu_percent",
    "ram_used_mb",
    "ram_total_mb",
    "disk_read_kb",
    "disk_write_kb",
    "net_rx_kb",
    "net_tx_kb",
)


def pack_record(record: dict) -> bytes:
    """Pack a metric dict into a 44-byte binary record."""
    return struct.pack(
        RECORD_FORMAT,
        int(record["machine_id"]) & 0xFFFFFFFFFFFFFFFF,
        float(record["timestamp"]),
        float(record["cpu_percent"]),
        float(record["ram_used_mb"]),
        int(record["ram_total_mb"]),
        int(record["disk_read_kb"]),
        int(record["disk_write_kb"]),
        int(record["net_rx_kb"]),
        int(record["net_tx_kb"]),
    )


def unpack_record(blob: bytes) -> dict:
    """Unpack a 44-byte binary record into a metric dict."""
    values = struct.unpack(RECORD_FORMAT, blob)
    return dict(zip(_RECORD_FIELDS, values))


class StorageEngine:
    """Fixed-size paged binary store for metric records."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        self._db_path = os.path.join(data_dir, "metrics.db")
        self._bitmap_path = os.path.join(data_dir, "pages.bitmap")

        db_is_new = (not os.path.exists(self._db_path)) or os.path.getsize(
            self._db_path
        ) == 0
        if not os.path.exists(self._db_path):
            open(self._db_path, "wb").close()
        if not os.path.exists(self._bitmap_path):
            open(self._bitmap_path, "wb").close()

        self._db = open(self._db_path, "r+b")
        self._bitmap_file = open(self._bitmap_path, "r+b")

        # Load bitmap into memory (one byte per page; 0 = free, 1 = full).
        self._bitmap = bytearray(self._bitmap_file.read())

        if db_is_new:
            self._allocate_page(0)

        # Crash safety: replay any logged-but-uncommitted writes on startup.
        self.wal = WAL(data_dir)
        recovered = self.wal.recover()
        for entry in recovered:
            self.write_raw(
                entry["page_id"], entry["slot_offset"], entry["record_bytes"]
            )
            # Commit the replayed entry so it won't be re-applied next startup.
            self.wal.write_commit(entry["lsn"])
        self.recovered_count = len(recovered)
        print(f"WAL recovery: applied {len(recovered)} uncommitted entries")

    # -- internal helpers --------------------------------------------------

    def _flush_bitmap(self):
        self._bitmap_file.seek(0)
        self._bitmap_file.write(self._bitmap)
        self._bitmap_file.flush()

    def _allocate_page(self, page_id: int):
        """Write a blank page at ``page_id`` and mark it free in the bitmap."""
        header = struct.pack(
            _PAGE_HEADER_FORMAT, MAGIC_PAGE, page_id, 0, 0, 0, _RESERVED
        )
        blank = header + b"\x00" * (PAGE_SIZE - HEADER_SIZE)
        self._db.seek(page_id * PAGE_SIZE)
        self._db.write(blank)
        self._db.flush()

        # Grow the bitmap if necessary, then mark this page as having space.
        while len(self._bitmap) <= page_id:
            self._bitmap.append(0)
        self._bitmap[page_id] = 0
        self._flush_bitmap()

    def _read_header(self, page_id: int) -> tuple:
        self._db.seek(page_id * PAGE_SIZE)
        raw = self._db.read(HEADER_SIZE)
        magic, pid, record_count, free_offset, flags, _reserved = struct.unpack(
            _PAGE_HEADER_FORMAT, raw
        )
        return magic, pid, record_count, free_offset, flags

    def _write_header(self, page_id: int, record_count: int, free_offset: int, flags=0):
        header = struct.pack(
            _PAGE_HEADER_FORMAT,
            MAGIC_PAGE,
            page_id,
            record_count,
            free_offset,
            flags,
            _RESERVED,
        )
        self._db.seek(page_id * PAGE_SIZE)
        self._db.write(header)
        self._db.flush()

    def _find_free_page(self) -> int:
        """Return the first page with free space, allocating one if needed."""
        for i, b in enumerate(self._bitmap):
            if b == 0:
                return i
        new_id = len(self._bitmap)
        self._allocate_page(new_id)
        return new_id

    def _page_has_room(self, free_offset: int) -> bool:
        return DATA_START + free_offset + RECORD_SIZE <= PAGE_SIZE - 44

    # -- public API --------------------------------------------------------

    def write(self, record: dict) -> tuple:
        """Append a record; return ``(page_id, slot_offset)`` of where it went."""
        blob = pack_record(record)

        # Find a page that has room, marking full pages as we go.
        while True:
            page_id = self._find_free_page()
            _magic, _pid, record_count, free_offset, _flags = self._read_header(page_id)
            if self._page_has_room(free_offset):
                break
            # Page is full — record that and look again.
            self._bitmap[page_id] = 1
            self._flush_bitmap()

        slot_offset = free_offset

        # WAL: log the pending write BEFORE touching the data file.
        lsn = self.wal.append_entry(page_id, slot_offset, blob)

        self._db.seek(page_id * PAGE_SIZE + DATA_START + slot_offset)
        self._db.write(blob)
        self._db.flush()

        new_count = record_count + 1
        new_free = free_offset + RECORD_SIZE
        self._write_header(page_id, new_count, new_free)

        if not self._page_has_room(new_free):
            self._bitmap[page_id] = 1
            self._flush_bitmap()

        # WAL: the write is durable — record the commit.
        self.wal.write_commit(lsn)

        return page_id, slot_offset

    def read(self, page_id: int, slot_offset: int) -> dict:
        """Read and unpack a single record at ``(page_id, slot_offset)``."""
        self._db.seek(page_id * PAGE_SIZE + DATA_START + slot_offset)
        blob = self._db.read(RECORD_SIZE)
        return unpack_record(blob)

    def write_raw(self, page_id: int, slot_offset: int, blob: bytes):
        """Write pre-packed record bytes to a slot (used by WAL recovery)."""
        self._db.seek(page_id * PAGE_SIZE + DATA_START + slot_offset)
        self._db.write(blob)
        self._db.flush()

    def page_count(self) -> int:
        size = os.path.getsize(self._db_path)
        return size // PAGE_SIZE

    def count_records(self) -> int:
        """Total record count, read cheaply from page headers only."""
        total = 0
        for page_id in range(self.page_count()):
            _magic, _pid, record_count, _free, _flags = self._read_header(page_id)
            total += record_count
        return total

    def scan_all(self) -> list:
        """Return ``[(page_id, slot_offset, record_dict), ...]`` for all records."""
        results = []
        for page_id in range(self.page_count()):
            _magic, _pid, record_count, _free_offset, _flags = self._read_header(
                page_id
            )
            for i in range(record_count):
                slot_offset = i * RECORD_SIZE
                results.append((page_id, slot_offset, self.read(page_id, slot_offset)))
        return results

    def close(self):
        self._db.close()
        self._bitmap_file.close()
        self.wal.close()
