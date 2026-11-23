"""Orquestração sequencial e segura de arquivos CSV de entrada."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from challenge.ai.base import LLMClient
from challenge.config import Settings
from challenge.infra.io import InputNotFoundError, timestamp
from challenge.logging_setup import AuditLog
from challenge.metrics import MetricsRegistry
from challenge.performer.pipeline import FileOutcome, PerformerPipeline
from challenge.pii import mask_pii
from challenge.preprocess.pipeline import PreprocessPipeline
from challenge.reporting.render import write_json


@dataclass(frozen=True)
class BatchOutcome:
    """Resumo do processamento de um arquivo de entrada."""

    source: Path
    status: str
    archived_path: Path | None = None
    performer: FileOutcome | None = None
    error: str | None = None


@dataclass(frozen=True)
class BatchResult:
    """Resumo imutável de uma execução de processamento em lote."""

    outcomes: tuple[BatchOutcome, ...]
    stats: dict[str, Any]
    stats_path: Path


class BatchRunner:
    """Processa arquivos CSV em ordem estável, isolando erros entre arquivos."""

    def __init__(self, settings: Settings, llm: LLMClient | None, run_id: str) -> None:
        """Guarda as dependências da execução."""
        self._settings = settings
        self._llm = llm
        self._run_id = run_id
        self._log = logging.getLogger("challenge.batch")

    def run(self, include_performer: bool = True) -> BatchResult:
        """Processa todos os CSVs elegíveis, um a um, e arquiva os concluídos."""
        settings = self._settings
        settings.input_dir.mkdir(parents=True, exist_ok=True)
        settings.processed_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(
            (
                path
                for path in settings.input_dir.iterdir()
                if path.is_file() and not path.is_symlink() and path.suffix.casefold() == ".csv"
            ),
            key=lambda path: path.name.casefold(),
        )
        if not files:
            raise InputNotFoundError(f"Nenhum arquivo CSV encontrado em {settings.input_dir}")

        registry = MetricsRegistry()
        outcomes: list[BatchOutcome] = []
        started_at = datetime.now(UTC)
        self._log.info("Arquivos CSV elegíveis: %d", len(files))
        for source in files:
            outcomes.append(self._process_one(source, include_performer, registry))

        status_counts: dict[str, int] = {}
        for outcome in outcomes:
            status_counts[outcome.status] = status_counts.get(outcome.status, 0) + 1
        stats = {
            "schema_version": "1.0",
            "stage": "batch",
            "run_id": self._run_id,
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "files_discovered": len(files),
            "files_processed": sum(item.status != "failed" for item in outcomes),
            "files_archived": sum(item.archived_path is not None for item in outcomes),
            "files_failed": sum(item.status == "failed" for item in outcomes),
            "status_counts": status_counts,
            "metrics": registry.snapshot(),
        }
        stats_path = settings.logs_dir / f"stats_batch_{timestamp()}.json"
        write_json(stats_path, stats)
        self._log.info("Resumo do lote gravado: %s", stats_path.name)
        return BatchResult(tuple(outcomes), stats, stats_path)

    def _process_one(
        self, source: Path, include_performer: bool, registry: MetricsRegistry
    ) -> BatchOutcome:
        """Processa e arquiva um arquivo, preservando-o na entrada em caso de falha."""
        settings = self._settings
        audit_path = settings.logs_dir / f"audit_batch_{timestamp()}.jsonl"
        started = time.perf_counter()
        registry.increment("files_discovered")
        with AuditLog(audit_path, self._run_id) as audit:
            audit.write(
                "file_detected",
                source_file=source.name,
                mode="run_all" if include_performer else "preprocess",
            )
            try:
                preprocessed = PreprocessPipeline(settings, self._llm, self._run_id).run(source)
                registry.increment("files_preprocessed")
                registry.increment("rows_read", float(preprocessed.stats["linhas_lidas"]))
                registry.increment("rows_rejected", float(preprocessed.stats["linhas_rejeitadas"]))
                performer_outcome: FileOutcome | None = None
                if include_performer:
                    performer_outcome = PerformerPipeline(
                        settings, self._llm, self._run_id
                    ).process_batch(preprocessed.read_path)
                    registry.increment("performer_files_" + performer_outcome.status)

                archived_path = self._archive_destination(source)
                status = performer_outcome.status if performer_outcome else "preprocessed"
                duration_ms = (time.perf_counter() - started) * 1000
                registry.observe("file_processing_duration_ms", duration_ms)
                audit.write(
                    "file_processing_completed",
                    source_file=source.name,
                    status=status,
                    rows_read=preprocessed.stats["linhas_lidas"],
                    rows_valid=preprocessed.stats["linhas_validas"],
                    rows_rejected=preprocessed.stats["linhas_rejeitadas"],
                    performer_status=performer_outcome.status if performer_outcome else None,
                    duration_ms=round(duration_ms, 2),
                    artifacts={
                        "queue": preprocessed.fila_path.name,
                        "read": preprocessed.read_path.name,
                        "reports": [path.name for path in preprocessed.report_paths],
                    },
                )
                source.replace(archived_path)
                registry.increment("files_archived")
                audit.write(
                    "input_archived",
                    source_file=source.name,
                    archived_file=archived_path.name,
                    archived_path=str(archived_path),
                )
                self._log.info("Arquivo processado e arquivado: %s", archived_path.name)
                return BatchOutcome(source, status, archived_path, performer_outcome)
            except Exception as exc:
                registry.increment("files_failed")
                duration_ms = (time.perf_counter() - started) * 1000
                registry.observe("file_processing_duration_ms", duration_ms)
                message = mask_pii(f"{type(exc).__name__}: {exc}")[:500]
                audit.write(
                    "file_processing_failed",
                    source_file=source.name,
                    error_type=type(exc).__name__,
                    error=message,
                    duration_ms=round(duration_ms, 2),
                    retryable=True,
                )
                self._log.exception("Falha ao processar %s; mantido em Input", source.name)
                return BatchOutcome(source, "failed", error=message)

    def _archive_destination(self, source: Path) -> Path:
        """Escolhe destino sem sobrescrever um arquivo previamente processado."""
        destination = self._settings.processed_dir / source.name
        if not destination.exists():
            return destination
        return destination.with_name(f"{source.stem}_{timestamp()}{source.suffix}")
