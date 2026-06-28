"""NetSysDB — query console (REPL).

Opens the on-disk storage, rebuilds the timestamp B+ tree, and runs an
interactive SQL-like prompt against it.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from query.engine import QueryEngine
from storage.bplustree import BPlusTree
from storage.engine import StorageEngine

DATA_DIR = os.environ.get("DATA_DIR", "data")


def main():
    engine = StorageEngine(DATA_DIR)
    tree = BPlusTree()
    count = 0
    for page_id, slot_offset, record in engine.scan_all():
        tree.insert(record["timestamp"], (page_id, slot_offset))
        count += 1

    qe = QueryEngine(engine, tree, data_dir=DATA_DIR)
    print(f"NetSysDB Query Console - {count} records loaded. Type 'exit' to quit.")
    while True:
        try:
            q = input("netsysdb> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if q.lower() in ("exit", "quit"):
            break
        if not q:
            continue
        try:
            rows = qe.execute(q)
            print(qe.format_table(rows))
        except Exception as e:
            print(f"Error: {e}")

    engine.close()


if __name__ == "__main__":
    main()
