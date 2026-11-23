"""Logging estruturado (JSON) e trilha de auditoria analítica (JSONL)."""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any

from challenge.pii import mask_pii

SCHEMA_VERSION = "1.0"
SERVICE_NAME = "futureminds-challenge"
_SENSITIVE_KEYS = re.compile(r"password|secret|token|authorization|api[_-]?key", re.IGNORECASE)
_BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._~+/-]+=*")


def _safe_value(value: Any, key: str = "") -> Any:
    """Redige PII e credenciais antes de persistir campos de telemetria."""
    if _SENSITIVE_KEYS.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _safe_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        return _BEARER.sub("Bearer [REDACTED]", mask_pii(value))
    return value


class RunContextFilter(logging.Filter):
    """Injeta ``run_id`` e ``process_name`` em todos os registros."""

    def __init__(self, run_id: str, process_name: str) -> None:
        """Guarda o contexto da execução."""
        super().__init__()
        self._run_id = run_id
        self._process_name = process_name

    def filter(self, record: logging.LogRecord) -> bool:
        """Anexa o contexto ao registro."""
        record.run_id = self._run_id
        record.trace_id = getattr(record, "trace_id", self._run_id)
        record.process_name = self._process_name
        return True


class JsonFormatter(logging.Formatter):
    """Serializa registros de log como uma linha JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Formata o registro."""
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "service": SERVICE_NAME,
            "severity": record.levelname,
            "run_id": getattr(record, "run_id", ""),
            "trace_id": getattr(record, "trace_id", ""),
            "process": getattr(record, "process_name", ""),
            "logger": record.name,
            "event": getattr(record, "event_name", "application.log"),
            "message": mask_pii(record.getMessage()),
        }
        attributes = getattr(record, "attributes", None)
        if attributes:
            payload["attributes"] = _safe_value(attributes)
        if record.exc_info:
            payload["exception"] = mask_pii(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(logs_dir: Path, run_id: str, process_name: str, level: str = "INFO") -> None:
    """Configura o logger ``challenge`` com arquivo rotativo (JSON) e console."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("challenge")
    logger.setLevel(level.upper())
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    context = RunContextFilter(run_id, process_name)

    file_handler = RotatingFileHandler(
        logs_dir / f"{process_name}.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(JsonFormatter())
    file_handler.addFilter(context)

    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(process_name)s:%(run_id)s] %(message)s")
    )
    console.addFilter(context)

    logger.addHandler(file_handler)
    logger.addHandler(console)


class AuditLog:
    """Escritor thread-safe de eventos analíticos em JSON Lines."""

    def __init__(self, path: Path, run_id: str) -> None:
        """Abre (append) o arquivo de auditoria."""
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._run_id = run_id
        self._lock = threading.Lock()
        if path.is_file():
            with path.open(encoding="utf-8") as existing:
                self._sequence = sum(1 for _ in existing)
        else:
            self._sequence = 0
        self._handle = path.open("a", encoding="utf-8")

    def write(self, event: str, **fields: Any) -> None:
        """Grava um evento com timestamp UTC."""
        with self._lock:
            self._sequence += 1
            record = {
                "schema_version": SCHEMA_VERSION,
                "event_id": str(uuid.uuid4()),
                "sequence": self._sequence,
                "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "service": SERVICE_NAME,
                "run_id": self._run_id,
                "trace_id": self._run_id,
                "event": event,
                **_safe_value(fields),
            }
            self._handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._handle.flush()

    def close(self) -> None:
        """Fecha o arquivo."""
        with self._lock:
            self._handle.close()

    def __enter__(self) -> AuditLog:
        """Entrada do context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Saída do context manager."""
        self.close()
