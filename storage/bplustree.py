"""NetSysDB — in-memory B+ tree indexed on timestamps.

A hand-written B+ tree used for fast timestamp range queries over stored
metric records. Values are ``(page_id, slot_offset)`` locations in the
storage engine.

Design:
* Minimum degree ``t``: every node except the root holds between ``t-1`` and
  ``2t-1`` keys. A node is "full" at ``2t-1`` keys.
* Insertion uses the proactive top-down split strategy (CLRS B-tree style):
  any full node is split *before* we descend into it, so splits never
  propagate back up.
* Only **leaf** nodes hold values. Internal nodes hold separator keys for
  routing. Leaves are chained via ``next`` pointers into a sorted linked
  list, which makes range scans cheap.
* On a leaf split the median key is **copied** up (it remains as the first
  key of the right leaf) — the defining B+ tree property. On an internal
  split the median key **moves** up.
"""


class BPlusNode:
    """A single B+ tree node (internal or leaf)."""

    def __init__(self, is_leaf=False):
        self.keys = []  # sorted list of float keys
        # internal: child BPlusNodes (len == len(keys)+1)
        # leaf: parallel list of values, one per key (len == len(keys))
        self.children = []
        self.is_leaf = is_leaf
        self.next = None  # leaf-only: next leaf in the linked list


class BPlusTree:
    """B+ tree keyed on float timestamps."""

    def __init__(self, t=50):
        if t < 2:
            raise ValueError("minimum degree t must be >= 2")
        self.t = t
        self.root = BPlusNode(is_leaf=True)

    # -- insertion ---------------------------------------------------------

    def insert(self, key: float, value: tuple):
        """Insert ``key`` -> ``value`` (duplicate keys are allowed)."""
        root = self.root
        if len(root.keys) == 2 * self.t - 1:
            new_root = BPlusNode(is_leaf=False)
            new_root.children.append(root)
            self._split_child(new_root, 0)
            self.root = new_root
            self._insert_non_full(new_root, key, value)
        else:
            self._insert_non_full(root, key, value)

    def _insert_non_full(self, node, key, value):
        if node.is_leaf:
            # Find insert position (after equal keys -> stable for duplicates).
            i = 0
            while i < len(node.keys) and key >= node.keys[i]:
                i += 1
            node.keys.insert(i, key)
            node.children.insert(i, value)
            return

        # Internal node: route to the correct child.
        i = 0
        while i < len(node.keys) and key >= node.keys[i]:
            i += 1
        if len(node.children[i].keys) == 2 * self.t - 1:
            self._split_child(node, i)
            # A new separator now sits at node.keys[i]; pick the right side.
            if key >= node.keys[i]:
                i += 1
        self._insert_non_full(node.children[i], key, value)

    def _split_child(self, parent, i):
        """Split the full child ``parent.children[i]`` in two."""
        t = self.t
        child = parent.children[i]
        z = BPlusNode(is_leaf=child.is_leaf)

        if child.is_leaf:
            # Right leaf keeps the median key (B+ property): t keys go right,
            # t-1 stay left. The copied-up separator is the right leaf's first.
            up_key = child.keys[t - 1]
            z.keys = child.keys[t - 1 :]
            z.children = child.children[t - 1 :]
            child.keys = child.keys[: t - 1]
            child.children = child.children[: t - 1]
            # Maintain the leaf linked list.
            z.next = child.next
            child.next = z
        else:
            # Internal: median moves up and out of both children.
            up_key = child.keys[t - 1]
            z.keys = child.keys[t:]
            z.children = child.children[t:]
            child.keys = child.keys[: t - 1]
            child.children = child.children[:t]

        parent.keys.insert(i, up_key)
        parent.children.insert(i + 1, z)

    # -- lookup ------------------------------------------------------------

    def _find_leaf(self, key: float) -> BPlusNode:
        """Descend from the root to the leaf that would hold ``key``."""
        node = self.root
        while not node.is_leaf:
            i = 0
            while i < len(node.keys) and key >= node.keys[i]:
                i += 1
            node = node.children[i]
        return node

    def search(self, key: float):
        """Return the value stored for ``key``, or ``None`` if absent."""
        leaf = self._find_leaf(key)
        # Binary search within the leaf's sorted keys.
        lo, hi = 0, len(leaf.keys) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            k = leaf.keys[mid]
            if k == key:
                return leaf.children[mid]
            if k < key:
                lo = mid + 1
            else:
                hi = mid - 1
        return None

    def range_query(self, k1: float, k2: float) -> list:
        """Return all values whose key is in ``[k1, k2]`` (inclusive)."""
        results = []
        node = self._find_leaf(k1)
        while node is not None:
            for i, k in enumerate(node.keys):
                if k < k1:
                    continue
                if k > k2:
                    return results  # leaves are sorted -> nothing more to find
                results.append(node.children[i])
            node = node.next
        return results
