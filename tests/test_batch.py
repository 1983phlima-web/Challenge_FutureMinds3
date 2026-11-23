"""Testes de processamento sequencial e arquivamento seguro dos arquivos de entrada."""

import json
from pathlib import Path

from challenge.batch import BatchRunner
from conftest import make_settings

CSV = (
    "id,data_reclamacao,canal,texto_reclamacao,produto,status\n"
    'REC-ONE,2025-11-03,Ouvidoria,"Estou com demora e cobrança no empréstimo.",Empréstimo,Aberta\n'
)


def _write_csv(path: Path, contents: str = CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def test_processa_csvs_em_ordem_e_armazena_somente_apos_logs(tmp_path):
    settings = make_settings(tmp_path)
    _write_csv(settings.input_dir / "zeta.csv")
    _write_csv(settings.input_dir / "alpha.CSV")
    (settings.input_dir / "observacoes.txt").write_text("ignorar", encoding="utf-8")

    result = BatchRunner(settings, None, "batch-001").run(include_performer=False)

    assert [item.source.name for item in result.outcomes] == ["alpha.CSV", "zeta.csv"]
    assert all(item.status == "preprocessed" for item in result.outcomes)
    assert {path.name for path in settings.processed_dir.iterdir()} == {"alpha.CSV", "zeta.csv"}
    assert [path.name for path in settings.input_dir.iterdir()] == ["observacoes.txt"]
    assert result.stats["files_archived"] == 2
    assert result.stats["metrics"]["counters"]["files_preprocessed"] == 2

    batch_logs = list(settings.logs_dir.glob("audit_batch_*.jsonl"))
    assert len(batch_logs) == 2
    for path in batch_logs:
        events = [json.loads(line)["event"] for line in path.read_text(encoding="utf-8").splitlines()]
        assert events.index("file_processing_completed") < events.index("input_archived")
    assert len(list(settings.logs_dir.glob("stats_preprocess_*.json"))) == 2
    assert result.stats_path.is_file()


def test_falha_de_arquivo_fica_na_entrada_e_nao_interrompe_proximo(tmp_path):
    settings = make_settings(tmp_path)
    _write_csv(settings.input_dir / "a-invalido.csv", "id,produto\n1,Seguro\n")
    _write_csv(settings.input_dir / "b-valido.csv")

    result = BatchRunner(settings, None, "batch-002").run(include_performer=False)

    by_name = {item.source.name: item for item in result.outcomes}
    assert by_name["a-invalido.csv"].status == "failed"
    assert by_name["b-valido.csv"].status == "preprocessed"
    assert (settings.input_dir / "a-invalido.csv").is_file()
    assert (settings.processed_dir / "b-valido.csv").is_file()
    assert result.stats["files_failed"] == 1
    failed_audit = next(settings.logs_dir.glob("audit_batch_*.jsonl"))
    assert "file_processing_failed" in failed_audit.read_text(encoding="utf-8")


def test_arquivo_com_nome_duplicado_nao_sobrescreve_o_arquivado(tmp_path):
    settings = make_settings(tmp_path)
    _write_csv(settings.input_dir / "lote.csv")
    settings.processed_dir.mkdir(parents=True)
    existing = settings.processed_dir / "lote.csv"
    existing.write_text("arquivo anterior", encoding="utf-8")

    result = BatchRunner(settings, None, "batch-003").run(include_performer=False)

    archived = result.outcomes[0].archived_path
    assert archived is not None and archived != existing
    assert existing.read_text(encoding="utf-8") == "arquivo anterior"
    assert archived.is_file()
