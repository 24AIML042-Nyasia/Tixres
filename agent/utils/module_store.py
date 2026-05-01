from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

SQLALCHEMY_AVAILABLE = False

try:  # Optional dependency
    from sqlalchemy import ForeignKey, String, create_engine  # type: ignore
    from sqlalchemy.orm import (  # type: ignore
        Mapped,
        Session,
        declarative_base,
        mapped_column,
        relationship,
    )

    SQLALCHEMY_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover
    pass


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "module_store.sqlite3"
)


@dataclass(frozen=True)
class StoreSyncResult:
    modules: int
    functions: int


# =============================================================================
# SQLite fallback backend (always available)
# =============================================================================


class SqliteModuleStore:
    def __init__(self, path: Path = DEFAULT_DB_PATH):
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def init_db(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS modules (
                  module_id   TEXT PRIMARY KEY,
                  name        TEXT NOT NULL,
                  version     TEXT NOT NULL,
                  description TEXT,
                  updated_at  TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS functions (
                  full_name     TEXT PRIMARY KEY,
                  module_id     TEXT NOT NULL,
                  function_name TEXT NOT NULL,
                  dtype         TEXT NOT NULL,
                  fn_type       TEXT NOT NULL,
                  updated_at    TEXT NOT NULL,
                  FOREIGN KEY(module_id) REFERENCES modules(module_id) ON DELETE CASCADE
                );
                """
            )

    def sync_registry(self, registry) -> StoreSyncResult:
        self.init_db()

        modules: dict[str, Any] = {}
        functions: list[tuple[str, str, str, str, str]] = []

        for full_name, entry in registry.entries():
            module = getattr(entry, "module", None)
            if module is None:
                continue

            module_id = module.module_id
            modules[module_id] = module

            function_name = full_name.rsplit(".", 1)[-1]
            functions.append(
                (full_name, module_id, function_name, entry.dtype, entry.type)
            )

        now = _utcnow_iso()

        with sqlite3.connect(self._path) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")

            for module_id, module in modules.items():
                conn.execute(
                    """
                    INSERT INTO modules(module_id, name, version, description, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(module_id) DO UPDATE SET
                      name=excluded.name,
                      version=excluded.version,
                      description=excluded.description,
                      updated_at=excluded.updated_at;
                    """,
                    (module_id, module.name, module.version, module.description, now),
                )

            for full_name, module_id, function_name, dtype, fn_type in functions:
                conn.execute(
                    """
                    INSERT INTO functions(full_name, module_id, function_name, dtype, fn_type, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(full_name) DO UPDATE SET
                      module_id=excluded.module_id,
                      function_name=excluded.function_name,
                      dtype=excluded.dtype,
                      fn_type=excluded.fn_type,
                      updated_at=excluded.updated_at;
                    """,
                    (full_name, module_id, function_name, dtype, fn_type, now),
                )

        return StoreSyncResult(modules=len(modules), functions=len(functions))

    def list_modules(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        with sqlite3.connect(self._path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT module_id, name, version, description, updated_at FROM modules ORDER BY module_id;"
            ).fetchall()
            return [dict(r) for r in rows]


# =============================================================================
# SQLAlchemy backend (optional)
# =============================================================================


if SQLALCHEMY_AVAILABLE:  # pragma: no cover
    Base = declarative_base()

    class Module(Base):
        __tablename__ = "modules"

        module_id: Mapped[str] = mapped_column(String, primary_key=True)
        name: Mapped[str] = mapped_column(String, nullable=False)
        version: Mapped[str] = mapped_column(String, nullable=False)
        description: Mapped[str | None] = mapped_column(String, nullable=True)
        updated_at: Mapped[str] = mapped_column(String, nullable=False)

        functions: Mapped[list["Function"]] = relationship(
            back_populates="module", cascade="all, delete-orphan"
        )

    class Function(Base):
        __tablename__ = "functions"

        full_name: Mapped[str] = mapped_column(String, primary_key=True)
        module_id: Mapped[str] = mapped_column(
            String, ForeignKey("modules.module_id", ondelete="CASCADE"), nullable=False
        )
        function_name: Mapped[str] = mapped_column(String, nullable=False)
        dtype: Mapped[str] = mapped_column(String, nullable=False)
        fn_type: Mapped[str] = mapped_column(String, nullable=False)
        updated_at: Mapped[str] = mapped_column(String, nullable=False)

        module: Mapped[Module] = relationship(back_populates="functions")

    class SqlAlchemyModuleStore:
        def __init__(self, path: Path = DEFAULT_DB_PATH):
            self._path = Path(path)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._engine = create_engine(f"sqlite:///{self._path}")

        def init_db(self) -> None:
            Base.metadata.create_all(self._engine)

        def sync_registry(self, registry) -> StoreSyncResult:
            self.init_db()

            modules: dict[str, Any] = {}
            functions: list[tuple[str, str, str, str, str]] = []
            for full_name, entry in registry.entries():
                module = getattr(entry, "module", None)
                if module is None:
                    continue
                module_id = module.module_id
                modules[module_id] = module
                function_name = full_name.rsplit(".", 1)[-1]
                functions.append(
                    (full_name, module_id, function_name, entry.dtype, entry.type)
                )

            now = _utcnow_iso()
            with Session(self._engine) as session:
                for module_id, module in modules.items():
                    existing = session.get(Module, module_id)
                    if existing is None:
                        session.add(
                            Module(
                                module_id=module_id,
                                name=module.name,
                                version=module.version,
                                description=module.description,
                                updated_at=now,
                            )
                        )
                    else:
                        existing.name = module.name
                        existing.version = module.version
                        existing.description = module.description
                        existing.updated_at = now

                for full_name, module_id, function_name, dtype, fn_type in functions:
                    existing = session.get(Function, full_name)
                    if existing is None:
                        session.add(
                            Function(
                                full_name=full_name,
                                module_id=module_id,
                                function_name=function_name,
                                dtype=dtype,
                                fn_type=fn_type,
                                updated_at=now,
                            )
                        )
                    else:
                        existing.module_id = module_id
                        existing.function_name = function_name
                        existing.dtype = dtype
                        existing.fn_type = fn_type
                        existing.updated_at = now

                session.commit()

            return StoreSyncResult(modules=len(modules), functions=len(functions))

        def list_modules(self) -> list[dict[str, Any]]:
            if not self._path.exists():
                return []
            with Session(self._engine) as session:
                rows = session.query(Module).order_by(Module.module_id).all()
                return [
                    {
                        "module_id": r.module_id,
                        "name": r.name,
                        "version": r.version,
                        "description": r.description,
                        "updated_at": r.updated_at,
                    }
                    for r in rows
                ]


def get_module_store(path: Path = DEFAULT_DB_PATH):
    """
    Returns a module store.

    Prefers SQLAlchemy when installed; otherwise falls back to sqlite3.
    """
    if SQLALCHEMY_AVAILABLE:  # pragma: no cover
        return SqlAlchemyModuleStore(path)
    return SqliteModuleStore(path)

