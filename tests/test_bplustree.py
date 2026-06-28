"""Unit tests for the NetSysDB B+ tree index."""

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.bplustree import BPlusNode, BPlusTree  # noqa: E402


def _leftmost_leaf(tree: BPlusTree) -> BPlusNode:
    node = tree.root
    while not node.is_leaf:
        node = node.children[0]
    return node


def _scan_leaves(tree: BPlusTree):
    """Return all keys by walking the leaf linked list left-to-right."""
    keys = []
    node = _leftmost_leaf(tree)
    while node is not None:
        keys.extend(node.keys)
        node = node.next
    return keys


def _assert_tree_invariants(tree: BPlusTree, expected_count: int):
    leaf_keys = _scan_leaves(tree)
    # Leaves are globally sorted and contain every inserted key exactly once.
    assert leaf_keys == sorted(leaf_keys)
    assert len(leaf_keys) == expected_count


def test_10000_random_insert_then_search():
    """Insert 10k keys in random order; search must find every one."""
    random.seed(2024)
    keys = [float(i) for i in range(10_000)]
    random.shuffle(keys)

    tree = BPlusTree(t=50)
    expected = {}
    for idx, k in enumerate(keys):
        value = (idx % 7, (idx * 3) % 4096)
        tree.insert(k, value)
        expected[k] = value

    for k, value in expected.items():
        assert tree.search(k) == value

    # A key that was never inserted is not found.
    assert tree.search(10_001.5) is None
    _assert_tree_invariants(tree, 10_000)


def test_range_query_inclusive_count():
    """Keys 1.0..100.0 step 1.0; range (25, 75) yields exactly 51 values."""
    tree = BPlusTree(t=4)
    for i in range(1, 101):
        tree.insert(float(i), (i, 0))

    result = tree.range_query(25.0, 75.0)
    assert len(result) == 51  # 25..75 inclusive

    # The returned values correspond to keys 25..75.
    returned_keys = sorted(pid for pid, _ in result)
    assert returned_keys == list(range(25, 76))


def test_tiny_degree_forces_many_splits():
    """t=2 (max 3 keys/node) forces deep splitting; tree stays correct."""
    random.seed(7)
    keys = list(range(2000))
    random.shuffle(keys)

    tree = BPlusTree(t=2)
    for k in keys:
        tree.insert(float(k), (k, 0))

    for k in keys:
        assert tree.search(float(k)) == (k, 0)

    # Range over the whole set and a sub-range.
    assert len(tree.range_query(0.0, 1999.0)) == 2000
    assert len(tree.range_query(500.0, 599.0)) == 100
    _assert_tree_invariants(tree, 2000)


def test_50000_insertions_correct():
    """After 50k random insertions the tree is fully consistent."""
    random.seed(123456)
    keys = [float(i) for i in range(50_000)]
    random.shuffle(keys)

    tree = BPlusTree(t=16)
    for idx, k in enumerate(keys):
        tree.insert(k, (idx, 0))

    _assert_tree_invariants(tree, 50_000)

    # Spot-check searches across the range.
    for k in (0.0, 12345.0, 49999.0, 25000.0):
        assert tree.search(k) is not None

    # A mid-size range returns the expected inclusive count.
    assert len(tree.range_query(1000.0, 1999.0)) == 1000


def test_range_below_and_above_all():
    """Ranges entirely outside the data return nothing."""
    tree = BPlusTree(t=3)
    for i in range(10, 20):
        tree.insert(float(i), (i, 0))
    assert tree.range_query(0.0, 5.0) == []
    assert tree.range_query(100.0, 200.0) == []
    assert len(tree.range_query(0.0, 100.0)) == 10
