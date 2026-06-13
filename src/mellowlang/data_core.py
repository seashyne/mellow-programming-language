from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator


class DataCoreError(RuntimeError):
    pass


@dataclass
class _Stream:
    kind: str
    iterator: Iterator[Any]
    resource: Any
    batch_size: int
    rows_read: int = 0
    closed: bool = False


class DataStreamManager:
    def __init__(
        self,
        *,
        resolve_read: Callable[[Any], str],
        resolve_write: Callable[[Any], str],
        check_cancelled: Callable[[], None],
        max_batch_size: int = 1000,
        max_open_streams: int = 8,
        max_record_bytes: int = 1_048_576,
        max_query_rows: int = 5000,
        allow_write: bool = False,
    ) -> None:
        self._resolve_read = resolve_read
        self._resolve_write = resolve_write
        self._check_cancelled = check_cancelled
        self.max_batch_size = max(1, int(max_batch_size))
        self.max_open_streams = max(1, int(max_open_streams))
        self.max_record_bytes = max(128, int(max_record_bytes))
        self.max_query_rows = max(1, int(max_query_rows))
        self.allow_write = bool(allow_write)
        self._streams: dict[str, _Stream] = {}
        self._databases: dict[str, sqlite3.Connection] = {}
        self._next_id = 1

    def _batch_size(self, value: Any) -> int:
        size = int(value or 100)
        if size < 1 or size > self.max_batch_size:
            raise DataCoreError(f"data batch size must be 1-{self.max_batch_size}")
        return size

    def _new_handle(self, stream: _Stream) -> str:
        if len(self._streams) >= self.max_open_streams:
            raise DataCoreError(f"too many open data streams (max {self.max_open_streams})")
        handle = f"data:{self._next_id}"
        self._next_id += 1
        self._streams[handle] = stream
        return handle

    def open_jsonl(self, path: Any, batch_size: Any = 100) -> str:
        full = self._resolve_read(path)
        resource = open(full, "r", encoding="utf-8")

        def rows() -> Iterator[Any]:
            for line_no, raw in enumerate(resource, 1):
                self._check_cancelled()
                if len(raw.encode("utf-8")) > self.max_record_bytes:
                    raise DataCoreError(f"JSONL record too large at line {line_no}")
                text = raw.strip()
                if text:
                    yield json.loads(text)

        return self._new_handle(_Stream("jsonl", rows(), resource, self._batch_size(batch_size)))

    def open_csv(self, path: Any, batch_size: Any = 100) -> str:
        full = self._resolve_read(path)
        resource = open(full, "r", encoding="utf-8", newline="")
        reader = csv.DictReader(resource)
        return self._new_handle(_Stream("csv", iter(reader), resource, self._batch_size(batch_size)))

    def open_iterable(self, rows: Iterator[Any], batch_size: Any = 100) -> str:
        class _NoopResource:
            @staticmethod
            def close() -> None:
                return None

        return self._new_handle(_Stream("iterable", iter(rows), _NoopResource(), self._batch_size(batch_size)))

    def next_batch(self, handle: Any) -> list[Any]:
        self._check_cancelled()
        stream = self._streams.get(str(handle))
        if stream is None or stream.closed:
            raise DataCoreError(f"unknown or closed data stream: {handle}")
        batch: list[Any] = []
        try:
            for _ in range(stream.batch_size):
                self._check_cancelled()
                row = next(stream.iterator)
                if len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8")) > self.max_record_bytes:
                    raise DataCoreError("data record exceeds configured byte limit")
                batch.append(row)
                stream.rows_read += 1
        except StopIteration:
            self.close(handle)
        return batch

    def close(self, handle: Any) -> bool:
        stream = self._streams.pop(str(handle), None)
        if stream is None:
            return False
        stream.closed = True
        try:
            stream.resource.close()
        except Exception:
            pass
        return True

    def cancel(self, handle: Any) -> bool:
        return self.close(handle)

    def stream_info(self, handle: Any) -> dict[str, Any]:
        stream = self._streams.get(str(handle))
        if stream is None:
            return {"handle": str(handle), "open": False}
        return {
            "handle": str(handle),
            "open": not stream.closed,
            "kind": stream.kind,
            "batch_size": stream.batch_size,
            "rows_read": stream.rows_read,
        }

    @staticmethod
    def project(rows: Any, fields: Any) -> list[dict[str, Any]]:
        if not isinstance(rows, list) or not isinstance(fields, list):
            raise DataCoreError("data.project expects rows and field-name list")
        names = [str(field) for field in fields]
        return [{name: row.get(name) for name in names} for row in rows if isinstance(row, dict)]

    @staticmethod
    def where(rows: Any, field: Any, operator: Any, expected: Any) -> list[Any]:
        if not isinstance(rows, list):
            raise DataCoreError("data.where expects a row list")
        key = str(field)
        op = str(operator)

        def matches(row: Any) -> bool:
            if not isinstance(row, dict):
                return False
            actual = row.get(key)
            if op == "==":
                return actual == expected
            if op == "!=":
                return actual != expected
            if op == ">":
                return actual > expected
            if op == ">=":
                return actual >= expected
            if op == "<":
                return actual < expected
            if op == "<=":
                return actual <= expected
            if op == "contains":
                return expected in actual if isinstance(actual, (str, list, dict)) else False
            raise DataCoreError(f"unsupported data.where operator: {op}")

        return [row for row in rows if matches(row)]

    @staticmethod
    def sum_field(rows: Any, field: Any) -> Any:
        if not isinstance(rows, list):
            raise DataCoreError("data.sum expects a row list")
        total: Any = 0
        for row in rows:
            if isinstance(row, dict):
                total += row.get(str(field), 0)
        return total

    def sqlite_query(self, path: Any, sql: Any, params: Any = None, limit: Any = None) -> list[dict[str, Any]]:
        self._check_cancelled()
        statement = str(sql).strip()
        if statement.split(None, 1)[0].upper() not in {"SELECT", "WITH", "PRAGMA"}:
            raise DataCoreError("data.sqlite_query only allows read-only statements")
        row_limit = min(self.max_query_rows, max(1, int(limit or self.max_query_rows)))
        connection, owned = self._sqlite_connection(path, write=False)
        try:
            connection.row_factory = sqlite3.Row
            cursor = connection.execute(statement, params if isinstance(params, (list, tuple, dict)) else [])
            rows = cursor.fetchmany(row_limit + 1)
        finally:
            if owned:
                connection.close()
        if len(rows) > row_limit:
            raise DataCoreError(f"SQLite result exceeds row limit {row_limit}")
        return [dict(row) for row in rows]

    def sqlite_execute(self, path: Any, sql: Any, params: Any = None) -> dict[str, Any]:
        self._check_cancelled()
        if not self.allow_write:
            raise DataCoreError("data writes are disabled")
        statement = str(sql).strip()
        command = statement.split(None, 1)[0].upper()
        if command not in {"INSERT", "UPDATE", "DELETE", "CREATE"}:
            raise DataCoreError("unsupported SQLite write statement")
        connection, owned = self._sqlite_connection(path, write=True)
        try:
            cursor = connection.execute(statement, params if isinstance(params, (list, tuple, dict)) else [])
            connection.commit()
            return {"rows_changed": max(0, int(cursor.rowcount)), "last_row_id": cursor.lastrowid}
        finally:
            if owned:
                connection.close()

    def sqlite_open(self, path: Any = ":memory:", readonly: Any = False) -> str:
        is_readonly = bool(readonly)
        if str(path) == ":memory:":
            connection = sqlite3.connect(":memory:", timeout=1.0)
        elif is_readonly:
            full = Path(self._resolve_read(path)).resolve()
            connection = sqlite3.connect(f"{full.as_uri()}?mode=ro", uri=True, timeout=1.0)
        else:
            if not self.allow_write:
                raise DataCoreError("data writes are disabled")
            connection = sqlite3.connect(self._resolve_write(path), timeout=1.0)
        handle = f"db:{self._next_id}"
        self._next_id += 1
        self._databases[handle] = connection
        return handle

    def sqlite_close(self, handle: Any) -> bool:
        connection = self._databases.pop(str(handle), None)
        if connection is None:
            return False
        connection.close()
        return True

    def _sqlite_connection(self, target: Any, *, write: bool) -> tuple[sqlite3.Connection, bool]:
        handle = str(target)
        if handle in self._databases:
            return self._databases[handle], False
        if handle == ":memory:":
            raise DataCoreError("use data.sqlite_open for a persistent in-memory database")
        if write:
            return sqlite3.connect(self._resolve_write(target), timeout=1.0), True
        full = Path(self._resolve_read(target)).resolve()
        return sqlite3.connect(f"{full.as_uri()}?mode=ro", uri=True, timeout=1.0), True

    def close_all(self) -> None:
        for handle in list(self._streams):
            self.close(handle)
        for handle in list(self._databases):
            self.sqlite_close(handle)
