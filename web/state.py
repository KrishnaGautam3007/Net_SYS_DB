"""Shared application state.

The collector populates these module attributes on startup (and keeps the
``machines`` / ``last_seen`` dicts updated as metrics arrive). The REST API
reads them. Always access through the module (``state.machines``) so callers
see the latest values rather than an early-bound copy.
"""

import time

storage_engine = None  # storage.engine.StorageEngine
bplus_tree = None  # storage.bplustree.BPlusTree
alert_engine = None  # alerts.engine.AlertEngine
query_engine = None  # query.engine.QueryEngine

machines = {}  # machine_name -> last metric dict
last_seen = {}  # machine_name -> unix timestamp of last metric
names = {}  # machine_id (int) -> machine_name

start_time = time.time()
OFFLINE_AFTER = 60  # seconds without a metric => OFFLINE
