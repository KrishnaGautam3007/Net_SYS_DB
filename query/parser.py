"""NetSysDB — SQL-like query tokenizer and parser.

Supports a deliberately small dialect::

    SELECT <items> FROM <metrics|alerts>
      [WHERE <cond> [AND <cond> ...]]
      [GROUP BY <field>]
      [ORDER BY <field> [ASC|DESC]]
      [LIMIT <n>]

Where ``<items>`` is a comma-separated list of:

* ``*``
* a column name (e.g. ``machine_name``, ``cpu_percent``)
* an aggregate: ``avg(field)``, ``max(field)``, ``min(field)``, ``count(*)``

And ``<cond>`` is one of:

* ``field BETWEEN v1 AND v2``  (on ``timestamp`` this becomes a ts_range)
* ``field <op> value``         (op in ``= > < >= <=``)

The parser returns an AST dict consumed by ``query.engine.QueryEngine``.
"""

_KEYWORDS = {
    "SELECT",
    "FROM",
    "WHERE",
    "AND",
    "BETWEEN",
    "GROUP",
    "ORDER",
    "BY",
    "LIMIT",
    "ASC",
    "DESC",
}
_AGG_FUNCS = {"avg", "max", "min", "count", "sum"}
_OPERATORS = {"=", ">", "<", ">=", "<=", "!="}


def tokenize(query: str) -> list:
    """Split a query into tokens, keeping single-quoted strings intact."""
    tokens = []
    i, n = 0, len(query)
    while i < n:
        c = query[i]
        if c.isspace():
            i += 1
            continue
        if c == "'":  # quoted string literal (may contain spaces)
            j = i + 1
            while j < n and query[j] != "'":
                j += 1
            tokens.append(query[i : j + 1])  # keep the surrounding quotes
            i = j + 1
            continue
        if c in ",()*":
            tokens.append(c)
            i += 1
            continue
        if c in "<>=!":  # comparison operator (one or two chars)
            if i + 1 < n and query[i + 1] == "=":
                tokens.append(query[i : i + 2])
                i += 2
            else:
                tokens.append(c)
                i += 1
            continue
        # bareword: identifier or numeric literal
        j = i
        while j < n and (not query[j].isspace()) and query[j] not in ",()*<>=!'":
            j += 1
        tokens.append(query[i:j])
        i = j
    return tokens


def _parse_value(token: str):
    """Convert a literal token into a Python str/int/float."""
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1]
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token


class _Cursor:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def expect_kw(self, kw):
        tok = self.next()
        if tok is None or tok.upper() != kw:
            raise ValueError(f"expected '{kw}', got {tok!r}")
        return tok


def parse(query: str) -> dict:
    """Parse a query string into an AST dict."""
    cur = _Cursor(tokenize(query))
    ast = {
        "select": [],
        "from": None,
        "where": {"ts_range": None, "filters": []},
        "group_by": None,
        "order_by": None,
        "limit": None,
    }

    cur.expect_kw("SELECT")
    ast["select"] = _parse_select_list(cur)

    cur.expect_kw("FROM")
    table = cur.next()
    if table is None:
        raise ValueError("missing table name after FROM")
    ast["from"] = table.lower()

    while cur.peek() is not None:
        kw = cur.peek().upper()
        if kw == "WHERE":
            cur.next()
            _parse_where(cur, ast)
        elif kw == "GROUP":
            cur.next()
            cur.expect_kw("BY")
            ast["group_by"] = cur.next()
        elif kw == "ORDER":
            cur.next()
            cur.expect_kw("BY")
            field = cur.next()
            direction = "ASC"
            if cur.peek() is not None and cur.peek().upper() in ("ASC", "DESC"):
                direction = cur.next().upper()
            ast["order_by"] = (field, direction)
        elif kw == "LIMIT":
            cur.next()
            ast["limit"] = int(cur.next())
        else:
            raise ValueError(f"unexpected token {cur.peek()!r}")

    return ast


def _parse_select_list(cur: _Cursor) -> list:
    items = []
    while True:
        tok = cur.next()
        if tok is None:
            raise ValueError("unexpected end of SELECT list")
        if tok == "*":
            items.append({"type": "all"})
        elif tok.lower() in _AGG_FUNCS and cur.peek() == "(":
            cur.next()  # consume '('
            arg = cur.next()
            if cur.peek() == ")":
                cur.next()
            else:
                raise ValueError("expected ')' in aggregate")
            label = f"{tok.lower()}({arg})"
            items.append(
                {"type": "agg", "func": tok.lower(), "field": arg, "label": label}
            )
        else:
            items.append({"type": "col", "name": tok})

        if cur.peek() == ",":
            cur.next()
            continue
        break
    return items


def _parse_where(cur: _Cursor, ast: dict):
    while True:
        field = cur.next()
        if field is None:
            raise ValueError("incomplete WHERE clause")
        nxt = cur.peek()
        if nxt is not None and nxt.upper() == "BETWEEN":
            cur.next()  # BETWEEN
            v1 = _parse_value(cur.next())
            cur.expect_kw("AND")
            v2 = _parse_value(cur.next())
            if field == "timestamp":
                ast["where"]["ts_range"] = (float(v1), float(v2))
            else:
                ast["where"]["filters"].append((field, ">=", v1))
                ast["where"]["filters"].append((field, "<=", v2))
        elif nxt in _OPERATORS:
            op = cur.next()
            value = _parse_value(cur.next())
            ast["where"]["filters"].append((field, op, value))
        else:
            raise ValueError(f"invalid condition near {field!r}")

        if cur.peek() is not None and cur.peek().upper() == "AND":
            cur.next()
            continue
        break
