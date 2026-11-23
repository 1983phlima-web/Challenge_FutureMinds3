"""Garantias para telemetria estruturada e proteção de dados."""

import json
import logging

from challenge.logging_setup import AuditLog, JsonFormatter
from challenge.metrics import MetricsRegistry


def test_audit_log_tem_esquema_correlação_e_redige_dados(tmp_path):
    path = tmp_path / "audit.jsonl"
    with AuditLog(path, "run-abc") as audit:
        audit.write(
            "model_call_completed",
            email="cliente@example.com",
            authorization="Bearer secret-value",
            latency_ms=123.4,
        )
    with AuditLog(path, "run-abc") as audit:
        audit.write("metric_summary", rows=4)

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [event["sequence"] for event in events] == [1, 2]
    assert events[0]["schema_version"] == "1.0"
    assert events[0]["trace_id"] == "run-abc"
    assert events[0]["email"] == "[EMAIL]"
    assert events[0]["authorization"] == "[REDACTED]"
    assert events[0]["event_id"] != events[1]["event_id"]


def test_json_formatter_registra_atributos_e_mascara_pii():
    record = logging.LogRecord(
        "challenge.test",
        logging.INFO,
        __file__,
        1,
        "Contato 123.456.789-09",
        (),
        None,
    )
    record.run_id = "run-xyz"
    record.trace_id = "run-xyz"
    record.process_name = "test"
    record.event_name = "test.completed"
    record.attributes = {"rows": 5}

    result = json.loads(JsonFormatter().format(record))

    assert result["event"] == "test.completed"
    assert result["message"] == "Contato [CPF]"
    assert result["attributes"] == {"rows": 5}
    assert result["schema_version"] == "1.0"


def test_registry_calcula_contagens_e_percentis():
    metrics = MetricsRegistry()
    metrics.increment("files_processed")
    metrics.increment("files_processed", 2)
    for value in (10, 20, 30, 40, 50):
        metrics.observe("latency_ms", value)

    snapshot = metrics.snapshot()

    assert snapshot["counters"]["files_processed"] == 3
    assert snapshot["distributions"]["latency_ms"]["count"] == 5
    assert snapshot["distributions"]["latency_ms"]["p50"] == 30
    assert snapshot["distributions"]["latency_ms"]["p95"] == 50
