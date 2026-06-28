"""NetSysDB — Write-Ahead Log (crash safety for the storage engine).

Every record write is logged here BEFORE it touches ``metrics.db`` and a
commit marker is written AFTER. On startup, ``recover()`` replays any logged
write whose commit marker is missing (a crash between the data write and the
commit), guaranteeing no half-applied writes are lost.

Log layout — every line is a fixed ``WAL_RECORD_SIZE`` (64) bytes so the log
can be scanned with uniform chunked reads:

* data entry  : ``"!QII44sI"`` = lsn(8) page_id(4) slot_offset(4) record(44) crc32(4)
* commit line : ``"!IIQ48x"``  = sentinel(0xFFFFFFFF) COMMIT_MAGIC lsn, zero-padded

A data entry's first 4 bytes are the high word of its (small) LSN, which is 0
for any realistic LSN, so it can never be mistaken for the 0xFFFFFFFF commit
sentinel.

NOTE: this resolves an inconsistency in the original spec, where the commit
marker size (12 vs 16 bytes) did not align with the 64-byte chunked reads.
"""

import struct
import zlib

WAL_RECORD_SIZE = 64
LOG_ENTRY_FORMAT = "!QII44sI"  # lsn, page_id, slot_offset, record, crc32 -> 64 bytes
COMMIT_FORMAT = "!IIQ48x"  # sentinel, COMMIT_MAGIC, lsn, padding -> 64 bytes
COMMIT_MAGIC = 0xC0FFEEEE
_COMMIT_SENTINEL = 0xFFFFFFFF


class WAL:
    """Append-only write-ahead log with crash recovery."""

    def __init__(self, data_dir: str):
        import os

        self._path = os.path.join(data_dir, "wal.log")
        # a+b: appends always go to EOF; we seek(0) explicitly to read.
        self._file = open(self._path, "a+b")
        self._lsn = self._next_lsn()

    def _next_lsn(self) -> int:
        """Scan the existing log to continue LSNs without collisions."""
        self._file.seek(0)
        max_lsn = -1
        while True:
            chunk = self._file.read(WAL_RECORD_SIZE)
            if len(chunk) < WAL_RECORD_SIZE:
                break
            sentinel = struct.unpack("!I", chunk[:4])[0]
            if sentinel == _COMMIT_SENTINEL:
                _s, _magic, lsn = struct.unpack(COMMIT_FORMAT, chunk)
            else:
                lsn = struct.unpack("!Q", chunk[:8])[0]
            if lsn > max_lsn:
                max_lsn = lsn
        self._file.seek(0, 2)  # back to EOF for appends
        return max_lsn + 1

    def append_entry(self, page_id: int, slot_offset: int, record_bytes: bytes) -> int:
        """Log a pending write; return its LSN. Call BEFORE writing the page."""
        lsn = self._lsn
        self._lsn += 1
        crc = zlib.crc32(record_bytes) & 0xFFFFFFFF
        line = struct.pack(
            LOG_ENTRY_FORMAT, lsn, page_id, slot_offset, record_bytes, crc
        )
        self._file.write(line)
        self._file.flush()
        return lsn

    def write_commit(self, lsn: int):
        """Mark ``lsn`` durably applied. Call AFTER writing the page."""
        line = struct.pack(COMMIT_FORMAT, _COMMIT_SENTINEL, COMMIT_MAGIC, lsn)
        self._file.write(line)
        self._file.flush()

    def recover(self) -> list:
        """Return logged writes that were never committed (need replay).

        Each item: ``{"lsn", "page_id", "slot_offset", "record_bytes"}``.
        Corrupt entries (bad CRC, e.g. a torn tail write) are skipped.
        """
        self._file.seek(0)
        committed = set()
        pending = {}
        while True:
            chunk = self._file.read(WAL_RECORD_SIZE)
            if len(chunk) < WAL_RECORD_SIZE:
                break  # incomplete trailing write — ignore
            sentinel = struct.unpack("!I", chunk[:4])[0]
            if sentinel == _COMMIT_SENTINEL:
                _s, _magic, lsn = struct.unpack(COMMIT_FORMAT, chunk)
                committed.add(lsn)
                continue
            lsn, page_id, slot_offset, record_bytes, crc = struct.unpack(
                LOG_ENTRY_FORMAT, chunk
            )
            if (zlib.crc32(record_bytes) & 0xFFFFFFFF) != crc:
                continue  # corrupt entry — skip
            pending[lsn] = {
                "lsn": lsn,
                "page_id": page_id,
                "slot_offset": slot_offset,
                "record_bytes": record_bytes,
            }
        self._file.seek(0, 2)  # restore append position
        return [pending[lsn] for lsn in sorted(pending) if lsn not in committed]

    def close(self):
        self._file.close()
