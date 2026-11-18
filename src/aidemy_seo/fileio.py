"""Reading user CSVs and writing output files safely - shared by batch, abtest, series and experiments.

`read_table()` is the CSV reader of the batch analysis (specs/batch-analysis.md), with the required
columns as a parameter: UTF-8 (a BOM is fine), delimiter `,` `;` or tab found from the header, header
names trimmed and case-insensitive, quoted multi-line fields, line numbers as an editor shows them.
It never guesses: a row with the wrong number of fields is returned with an `error`, the caller
skips it with a warning. Handles user/channel data: never commit real exports.

`write_text_atomic()` writes a temp file next to the target, then `os.replace`, so a crash never
leaves half a file (used by abtest and by the experiment ledger). `same_file()` lets a command
refuse to write over one of its input files.
"""

from __future__ import annotations

import codecs
import contextlib
import csv
import io
import json
import os
import secrets
import shutil
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DELIMITERS = (",", ";", "\t")


class CsvError(ValueError):
    """A file-level problem: the CSV can't be read at all. The message is one line, safe to show as is."""


class InputFileError(ValueError):
    """An input file (stats JSON, bundle, description, ...) can't be read. One line, safe to show as is."""


def read_input_text(path: str | Path, what: str) -> str:
    """The UTF-8 text of an input file (a BOM is fine). Every problem is one InputFileError line:
    `can't read <what> <path>: No such file or directory` / `Is a directory` / `Permission denied` /
    `not UTF-8 (line 3) - save it as UTF-8`."""
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as e:
        raise InputFileError(f"can't read {what} {p}: {e.strerror or e}") from None
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        line = data[: e.start].count(b"\n") + 1
        raise InputFileError(f"can't read {what} {p}: not UTF-8 (line {line}) - save it as UTF-8") from None


def read_input_json(path: str | Path, what: str) -> Any:
    """read_input_text + json.loads; broken JSON is `can't read <what> <path>: not valid JSON (line 1, column 2)`."""
    text = read_input_text(path, what)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise InputFileError(f"can't read {what} {path}: not valid JSON (line {e.lineno}, column {e.colno})") from None


@dataclass
class CsvWarning:
    line: int | None  # None = about the whole file
    message: str
    skipped_row: bool = field(default=False, kw_only=True)  # this warning is why a row was not used


@dataclass
class CsvRow:
    line: int  # line in the file where the row starts (header = line 1)
    fields: list[str]
    error: str | None = None  # set when the row can't be used as it is (wrong number of fields)


@dataclass
class CsvTable:
    path: Path
    delimiter: str
    bom: bool  # the file started with a UTF-8 BOM (Excel "CSV UTF-8")
    columns: dict[str, int]  # known column name (lower case) -> field index
    ignored: list[str]  # other columns as written in the header, "(unnamed column N)" for empty names
    rows: list[CsvRow]  # every non-blank row after the header, in file order

    def value(self, row: CsvRow, name: str) -> str:
        """The raw field of column `name`; "" when the file has no such column or a short row lacks it."""
        i = self.columns.get(name)
        return row.fields[i] if i is not None and i < len(row.fields) else ""


def _read_text(path: Path) -> tuple[str, bool]:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise CsvError(f"file not found: {path}") from None
    except IsADirectoryError:
        raise CsvError(f"{path} is a directory, not a CSV file") from None
    except OSError as e:
        raise CsvError(f"can't read {path}: {e.strerror or e}") from None
    try:
        return data.decode("utf-8-sig"), data.startswith(codecs.BOM_UTF8)
    except UnicodeDecodeError as e:
        line = data[: e.start].count(b"\n") + 1
        raise CsvError(f"{path} is not UTF-8 (line {line}) - save it as CSV UTF-8") from None


def _header(first_line: str, required: Sequence[str]) -> tuple[str, list[str]]:
    """Pick the first delimiter that gives all required columns; the header's raw field names."""
    candidates = []
    for d in DELIMITERS:
        names = next(csv.reader([first_line], delimiter=d), [])
        missing = [r for r in required if r not in {n.strip().lower() for n in names}]
        if not missing:
            return d, names
        candidates.append((len(required) - len(missing), len(names), missing, names))
    # no delimiter works: report against the split that found the most required columns
    _, _, missing, names = max(candidates, key=lambda c: (c[0], c[1]))
    found = ", ".join(n.strip() for n in names if n.strip()) or "none"
    raise CsvError(f"missing column(s): {', '.join(missing)} (required: {', '.join(required)}; found: {found})")


def _blank(record: list[str]) -> bool:
    return all(not f.strip() for f in record)


def read_table(path: str | Path, required: Sequence[str], optional: Sequence[str] = ()) -> CsvTable:
    """Read a CSV with the `required` (and maybe `optional`) columns. Fully blank lines are dropped.

    Raises CsvError for file-level problems (missing, not UTF-8, empty, a required column missing,
    a known column twice, a csv.Error). Never writes anything."""
    path = Path(path)
    text, bom = _read_text(path)
    if not text.strip():
        raise CsvError(f"{path} is empty - expected a header with {', '.join(required)}")
    first_line = next(line for line in text.splitlines() if line.strip())
    delimiter = _header(first_line, required)[0]
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    rows: list[CsvRow] = []
    prev_line = 0
    try:
        header = next(reader)
        while _blank(header):  # leading blank lines before the header
            prev_line = reader.line_num
            header = next(reader)
        prev_line = reader.line_num
        norm = [h.strip().lower() for h in header]
        known = [*required, *optional]
        for name in known:
            if norm.count(name) > 1:
                raise CsvError(f"column '{name}' appears twice in the header")
        columns = {name: norm.index(name) for name in known if name in norm}
        used = set(columns.values())
        ignored = [h.strip() or f"(unnamed column {i + 1})" for i, h in enumerate(header) if i not in used]
        for record in reader:
            line, prev_line = prev_line + 1, reader.line_num
            if _blank(record):
                continue
            error = None
            if len(record) != len(header):
                error = f"skipped - {len(record)} fields, header has {len(header)}"
            rows.append(CsvRow(line, record, error))
    except csv.Error as e:
        raise CsvError(f"{path}: CSV error on line {prev_line + 1}: {e}") from None
    return CsvTable(path, delimiter, bom, columns, ignored, rows)


def csv_text(rows: Sequence[Sequence[object]], *, delimiter: str = ",", bom: bool = False) -> str:
    """CSV text (quoted where needed, '\\n' line ends); with `bom` it starts with a UTF-8 BOM for Excel."""
    buf = io.StringIO()
    csv.writer(buf, delimiter=delimiter, lineterminator="\n").writerows(rows)
    return ("\ufeff" if bom else "") + buf.getvalue()


def same_file(a: str | Path, b: str | Path) -> bool:
    """True when `a` and `b` name the same file: same resolved path, or (both exist) the same inode -
    which also catches hard links and a different letter case on a case-insensitive disk."""
    pa, pb = Path(a), Path(b)
    if pa.resolve() == pb.resolve():
        return True
    try:
        return pa.exists() and pb.exists() and os.path.samefile(pa, pb)
    except OSError:
        return False


def write_text_atomic(path: str | Path, text: str, *, new_file_mode: int = 0o666) -> None:
    """Atomic: write a temp file next to `path`, then os.replace - a crash never leaves half a file.
    An existing file keeps its file mode. A new one gets `new_file_mode` minus the umask: by default
    normal permissions (usually 0644, like any file the user creates); the experiment ledger passes
    0o600 (private)."""
    p = Path(path)
    tmp = p.parent / f".{p.name}.{secrets.token_hex(8)}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, new_file_mode)  # the umask applies, as for open()
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if p.exists():
            shutil.copymode(p, tmp)
        os.replace(tmp, p)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
