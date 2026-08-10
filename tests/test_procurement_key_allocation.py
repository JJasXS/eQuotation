"""Unit tests: PR/PO key + DOCNO allocation must not collide under concurrency."""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from utils.procurement_purchase_order_transfer import (
    _allocate_unique_purchase_order_number,
    _next_purchase_order_number,
)
from utils.procurement_purchase_request import (
    _allocate_unique_request_number,
    _insert_dynamic_with_pk_retry,
    _is_firebird_key_violation,
    _next_key,
)


class FakeCursor:
    """Minimal Firebird cursor stub for _next_key / DOCNO helpers."""

    def __init__(self) -> None:
        self.max_by_table: dict[str, int] = {}
        self.gen_value: dict[str, int] = {}
        self.exists: set[str] = set()
        self._last_sql = ""
        self._result: Any = None
        self.insert_calls = 0
        self.fail_inserts = 0

    def execute(self, sql: str, params: tuple | list | None = None) -> None:
        text = " ".join((sql or "").upper().split())
        self._last_sql = text
        params = tuple(params or ())

        if "COALESCE(MAX(" in text and " FROM " in text:
            table = text.split(" FROM ", 1)[1].split()[0].strip()
            self._result = (int(self.max_by_table.get(table, 0)),)
            return

        if text.startswith("SELECT GEN_ID("):
            # SELECT GEN_ID(NAME, N) FROM RDB$DATABASE
            inside = text.split("GEN_ID(", 1)[1].split(")", 1)[0]
            name, delta_s = [p.strip() for p in inside.split(",", 1)]
            delta = int(delta_s)
            current = int(self.gen_value.get(name, 0))
            current += delta
            self.gen_value[name] = current
            self._result = (current,)
            return

        if " FROM PH_PQ " in text and " LIKE ?" in text:
            # latest DOCNO for prefix — return highest existing match
            like = str(params[0]) if params else "%"
            prefix = like.rstrip("%")
            matches = sorted(d for d in self.exists if d.startswith(prefix))
            self._result = (matches[-1],) if matches else None
            return

        if " FROM PH_PQ " in text and " = ?" in text:
            doc = str(params[0]) if params else ""
            self._result = (doc,) if doc in self.exists else None
            return

        if " FROM PH_PO " in text and " LIKE ?" in text:
            like = str(params[0]) if params else "%"
            prefix = like.rstrip("%")
            matches = sorted(d for d in self.exists if d.startswith(prefix))
            self._result = (matches[-1],) if matches else None
            return

        if " FROM PH_PO " in text and " = ?" in text:
            doc = str(params[0]) if params else ""
            self._result = (doc,) if doc in self.exists else None
            return

        if text.startswith("INSERT INTO"):
            self.insert_calls += 1
            if self.fail_inserts > 0:
                self.fail_inserts -= 1
                raise Exception("violation of PRIMARY or UNIQUE KEY constraint")
            self._result = None
            return

        self._result = None

    def fetchone(self) -> Any:
        return self._result


class KeyViolationDetectionTests(unittest.TestCase):
    def test_detects_firebird_messages(self) -> None:
        self.assertTrue(_is_firebird_key_violation(Exception("KEY VIOLATION")))
        self.assertTrue(
            _is_firebird_key_violation(
                Exception("violation of PRIMARY or UNIQUE KEY constraint \"INTEG_123\"")
            )
        )
        self.assertTrue(_is_firebird_key_violation(Exception("error 335544665")))
        self.assertFalse(_is_firebird_key_violation(Exception("string truncation")))


class NextKeyCatchUpTests(unittest.TestCase):
    def test_prefers_table_named_generator(self) -> None:
        cur = FakeCursor()
        cur.max_by_table["PH_PQ"] = 76
        cur.gen_value["PH_PQ"] = 73  # lagging SQL Accounting generator
        val = _next_key(cur, "PH_PQ", "DOCKEY", ["GEN_PH_PQ_DOCKEY"])
        self.assertEqual(val, 77)
        self.assertEqual(cur.gen_value["PH_PQ"], 77)


    def test_catches_up_lagging_generator_instead_of_bare_max_plus_one(self) -> None:
        """Regression: old code returned MAX+1 without advancing the generator."""
        cur = FakeCursor()
        cur.max_by_table["PH_PQ"] = 500  # SQL Accounting already inserted up to 500
        cur.gen_value["PH_PQ"] = 100  # table-named SQL Accounting generator lagging
        val = _next_key(cur, "PH_PQ", "DOCKEY", ["GEN_PH_PQ_DOCKEY"])
        self.assertEqual(val, 501)
        # Generator must be caught up so the next SQL Accounting GEN_ID stays unique.
        self.assertEqual(cur.gen_value["PH_PQ"], 501)

    def test_concurrent_allocations_are_unique(self) -> None:
        cur = FakeCursor()
        cur.max_by_table["PH_PO"] = 10
        cur.gen_value["PH_PO"] = 10
        keys = [
            _next_key(cur, "PH_PO", "DOCKEY", ["GEN_PH_PO_DOCKEY"]) for _ in range(5)
        ]
        self.assertEqual(keys, [11, 12, 13, 14, 15])
        self.assertEqual(len(set(keys)), 5)


class DocNoAllocationTests(unittest.TestCase):
    def test_pr_docno_bumps_until_free(self) -> None:
        cur = FakeCursor()
        cur.exists = {"PR-26080001", "PR-26080002"}
        got = _allocate_unique_request_number(
            cur, {"DOCNO"}, preferred="PR-26080001"
        )
        self.assertEqual(got, "PR-26080003")

    def test_po_docno_bumps_until_free(self) -> None:
        cur = FakeCursor()
        preferred = "PO-20990101-0001"
        cur.exists = {preferred, "PO-20990101-0002"}
        with patch(
            "utils.procurement_purchase_order_transfer._next_purchase_order_number",
            side_effect=[
                "PO-20990101-0001",
                "PO-20990101-0002",
                "PO-20990101-0003",
            ],
        ):
            got = _allocate_unique_purchase_order_number(
                cur, {"DOCNO"}, preferred=preferred
            )
        self.assertEqual(got, "PO-20990101-0003")


class InsertRetryTests(unittest.TestCase):
    def test_pk_retry_reallocates_after_key_violation(self) -> None:
        cur = FakeCursor()
        cur.max_by_table["PH_PQDTL"] = 20
        cur.gen_value["GEN_PH_PQDTL_DTLKEY"] = 20
        cur.fail_inserts = 2  # fail twice, then succeed
        data = {"DTLKEY": 21, "DOCKEY": 1, "QTY": 1}
        key = _insert_dynamic_with_pk_retry(
            cur,
            "PH_PQDTL",
            data,
            {"DTLKEY", "DOCKEY", "QTY"},
            key_column="DTLKEY",
            generator_candidates=["GEN_PH_PQDTL_DTLKEY"],
            max_attempts=5,
        )
        self.assertEqual(cur.insert_calls, 3)
        self.assertEqual(key, data["DTLKEY"])
        self.assertGreater(int(data["DTLKEY"]), 21)


if __name__ == "__main__":
    unittest.main()
