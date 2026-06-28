"""NetSysDB — query executor.

Executes the AST produced by ``query.parser`` against the storage engine and
B+ tree index. Range predicates on ``timestamp`` use the B+ tree; everything
else is a linear pass over the (already narrowed) row set.

``machine_name`` is not stored in the binary record (only ``machine_id`` is),
so it is resolved from the machine registry sidecar (``machines.json``) written
by the collector. Querying ``FROM alerts`` reads ``alerts.json`` if present
(populated from Phase 10 onward).
"""

import json
import os

from query.parser import parse

_METRIC_COLUMNS = [
    "machine_id",
    "machine_name",
    "timestamp",
    "cpu_percent",
    "ram_used_mb",
    "ram_total_mb",
    "disk_read_kb",
    "disk_write_kb",
    "net_rx_kb",
    "net_tx_kb",
]


class QueryEngine:
    """Runs SQL-like queries over stored metrics (and alerts)."""

    def __init__(self, storage_engine, bplus_tree, data_dir=None):
        self.engine = storage_engine
        self.tree = bplus_tree
        self.data_dir = data_dir or getattr(storage_engine, "data_dir", "data")

    # -- registries --------------------------------------------------------

    def _load_registry(self) -> dict:
        path = os.path.join(self.data_dir, "machines.json")
        try:
            with open(path, "r") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _resolve_name(self, registry, machine_id):
        return registry.get(str(machine_id), f"machine-{machine_id}")

    def _load_alerts(self) -> list:
        path = os.path.join(self.data_dir, "alerts.json")
        try:
            with open(path, "r") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return []

    # -- loading -----------------------------------------------------------

    def _load_metrics(self, ast) -> list:
        ts_range = ast["where"]["ts_range"]
        records = []
        if ts_range is not None:
            t1, t2 = ts_range
            for page_id, slot_offset in self.tree.range_query(t1, t2):
                records.append(self.engine.read(page_id, slot_offset))
        else:
            records = [rec for _pid, _off, rec in self.engine.scan_all()]

        registry = self._load_registry()
        for r in records:
            r["machine_name"] = self._resolve_name(registry, r["machine_id"])
        return records

    # -- execution ---------------------------------------------------------

    def execute(self, query_str: str) -> list:
        ast = parse(query_str)
        table = ast["from"]
        if table == "metrics":
            rows = self._load_metrics(ast)
        elif table == "alerts":
            rows = self._load_alerts()
        else:
            raise ValueError(f"unknown table '{table}'")
        return self._run(rows, ast)

    def _run(self, rows, ast) -> list:
        rows = self._apply_filters(rows, ast["where"]["filters"])

        has_agg = any(item["type"] == "agg" for item in ast["select"])
        group_by = ast["group_by"]
        order_by = ast["order_by"]
        limit = ast["limit"]

        if group_by:
            result = self._grouped(rows, ast, group_by)
            result = self._order_and_limit(result, order_by, limit)
        elif has_agg:
            result = [self._aggregate_row(rows, ast)]
        else:
            rows = self._order_and_limit(rows, order_by, limit)
            result = [self._project(r, ast) for r in rows]
        return result

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _match(row, field, op, value):
        if field not in row:
            return False
        actual = row[field]
        try:
            if op == "=":
                return actual == value
            if op == "!=":
                return actual != value
            if op == ">":
                return actual > value
            if op == "<":
                return actual < value
            if op == ">=":
                return actual >= value
            if op == "<=":
                return actual <= value
        except TypeError:
            return False
        return False

    def _apply_filters(self, rows, filters):
        for field, op, value in filters:
            rows = [r for r in rows if self._match(r, field, op, value)]
        return rows

    @staticmethod
    def _agg(func, field, group):
        if func == "count":
            return len(group)
        values = [r[field] for r in group if field in r and r[field] is not None]
        if not values:
            return 0
        if func == "avg":
            return round(sum(values) / len(values), 2)
        if func == "sum":
            return round(sum(values), 2)
        if func == "max":
            return max(values)
        if func == "min":
            return min(values)
        raise ValueError(f"unknown aggregate '{func}'")

    def _grouped(self, rows, ast, group_by):
        from collections import defaultdict

        groups = defaultdict(list)
        for r in rows:
            groups[r.get(group_by)].append(r)

        out = []
        for key, group in groups.items():
            row = {}
            for item in ast["select"]:
                if item["type"] == "agg":
                    row[item["label"]] = self._agg(item["func"], item["field"], group)
                elif item["type"] == "col":
                    name = item["name"]
                    row[name] = key if name == group_by else group[0].get(name)
                elif item["type"] == "all":
                    row[group_by] = key
            out.append(row)
        return out

    def _aggregate_row(self, rows, ast):
        row = {}
        for item in ast["select"]:
            if item["type"] == "agg":
                row[item["label"]] = self._agg(item["func"], item["field"], rows)
            elif item["type"] == "col":
                row[item["name"]] = rows[0].get(item["name"]) if rows else None
        return row

    def _project(self, record, ast):
        # SELECT * -> all known columns (metric order if present, else all keys)
        for item in ast["select"]:
            if item["type"] == "all":
                if "cpu_percent" in record:
                    return {c: record.get(c) for c in _METRIC_COLUMNS if c in record}
                return dict(record)
        out = {}
        for item in ast["select"]:
            if item["type"] == "col":
                out[item["name"]] = record.get(item["name"])
        return out

    @staticmethod
    def _order_and_limit(rows, order_by, limit):
        if order_by:
            field, direction = order_by
            rows = sorted(
                rows,
                key=lambda r: (r.get(field) is None, r.get(field)),
                reverse=(direction == "DESC"),
            )
        if limit is not None:
            rows = rows[:limit]
        return rows

    # -- pretty printing ---------------------------------------------------

    @staticmethod
    def _format_cell(value):
        if isinstance(value, float):
            return f"{value:.4f}".rstrip("0").rstrip(".")
        return str(value)

    def format_table(self, rows: list) -> str:
        if not rows:
            return "(no rows)"
        columns = []
        for r in rows:
            for k in r.keys():
                if k not in columns:
                    columns.append(k)

        cells = [[self._format_cell(r.get(c, "")) for c in columns] for r in rows]
        widths = [len(c) for c in columns]
        for row in cells:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(cell))

        def fmt_row(values):
            return " | ".join(v.ljust(widths[i]) for i, v in enumerate(values))

        header = fmt_row(columns)
        divider = "-+-".join("-" * w for w in widths)
        body = "\n".join(fmt_row(row) for row in cells)
        return f"{header}\n{divider}\n{body}\n({len(rows)} row{'s' if len(rows) != 1 else ''})"
