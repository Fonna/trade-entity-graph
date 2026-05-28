"""Archive original import files and persist source-file metadata."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from pathlib import Path

from trade_entity_graph.config import get_settings
from trade_entity_graph.utils.ids import new_id

ArchivedFile = dict[str, str | int]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_source_files(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    sources: list[tuple[str, Path]],
    archive_root: str | Path | None = None,
) -> list[ArchivedFile]:
    """Copy import source files into the run archive directory and record metadata."""

    root = Path(archive_root) if archive_root else get_settings().import_archive_root
    run_archive_dir = root / run_id
    run_archive_dir.mkdir(parents=True, exist_ok=True)

    archived_files: list[ArchivedFile] = []
    for source_role, source_path in sources:
        source_file_id = new_id("SRC")
        original_path = Path(source_path)
        archived_path = run_archive_dir / f"{source_role}__{original_path.name}"
        shutil.copy2(original_path, archived_path)

        metadata: ArchivedFile = {
            "source_file_id": source_file_id,
            "source_role": source_role,
            "original_path": str(original_path.resolve()),
            "archived_path": str(archived_path.resolve()),
            "file_name": original_path.name,
            "file_size_bytes": archived_path.stat().st_size,
            "sha256": _sha256(archived_path),
        }
        connection.execute(
            """
            INSERT INTO import_source_file (
                source_file_id, run_id, source_role, original_path, archived_path,
                file_name, file_size_bytes, sha256
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_file_id,
                run_id,
                metadata["source_role"],
                metadata["original_path"],
                metadata["archived_path"],
                metadata["file_name"],
                metadata["file_size_bytes"],
                metadata["sha256"],
            ),
        )
        archived_files.append(metadata)

    connection.commit()
    return archived_files
