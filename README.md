# Challenge_FutureMinds3 — V2 · Release 1.0

Aplicação de triagem de reclamações com IA, processamento sequencial de arquivos CSV e observabilidade estruturada. O pacote mantém provedores intercambiáveis e segue a arquitetura de domínio, aplicação, infraestrutura e adaptadores.

## Pré-requisitos
- Windows 10/11 ou Server, Python 3.11+
- Conta StackSpot com **Service Credential** (client_id/client_secret) e o **realm** da conta
- Um **agente dedicado** no portal: instruções mínimas (ex.: "responda apenas com o JSON pedido no prompt"), **sem Knowledge Sources**, com o LLM de sua escolha. As configurações do agente valem em toda chamada; o prompt do sistema deste projeto segue dentro do `user_prompt`.

## Instalação
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Configuração
1. **Substitua** `config\motor_regras.txt` e `config\politica.txt` pelos seus TXT (SPEC §5.3–5.4).
2. Em `config\settings.yaml` informe `stackspot_realm` e `stackspot_agent_id`.
3. Defina as credenciais **no ambiente** (veja `env.example`):
   ```powershell
   $env:STACKSPOT_CLIENT_ID = "<client_id>"
   $env:STACKSPOT_CLIENT_SECRET = "<client_secret>"
   ```
4. Mantenha `mask_pii: true`: os textos são enviados à plataforma. Valide o enquadramento LGPD/contratual com seu time de segurança.

## Execução
```powershell
futureminds preprocess   # processa todos os CSVs em Input
futureminds perform      # consome lotes pendentes em Output
futureminds run-all      # pré-processamento + respostas para cada CSV
futureminds check        # validação de configuração e ambiente
```

## Pastas e arquivos gerados
```
C:\Challenge\
  Input\      *.csv (entrada; qualquer nome, contrato CSV documentado abaixo)
  Processados\ *.csv (arquivos concluídos, movidos somente após logs e artefatos)
  Fila\       processadas_<ts>.csv · rejeitadas_<ts>.csv
  Output\     processadas_<ts>_read.csv  →  _ok.csv (respondidos) | _loop.csv (pendentes) | _nok.csv (humano)
  Logs\       *.log (JSON) · audit_*.jsonl · stats_*.json · preflight_*.json
  Relatorios\ relatorio_*.md / .html (Resumo, Tendências, Top Riscos)
```

`preprocess` e `run-all` consideram todos os arquivos regulares com extensão `.csv` (sem distinção entre maiúsculas e minúsculas), ordenados pelo nome e processados um por vez. Cada arquivo deve conter `id,data_reclamacao,canal,texto_reclamacao,produto,status`. Arquivos concluídos são movidos para `Processados` após a geração dos logs, estatísticas e artefatos. Em caso de falha de leitura, schema ou processamento, o CSV permanece em `Input` para correção e nova tentativa; arquivos que não sejam CSV são ignorados.

O caminho-base padrão é `C:\Challenge`; pode ser alterado com `--base-dir` ou `base_dir` no YAML. `input_subdir` e `processed_subdir` são configuráveis.

## Ciclo `_loop` (itens sem resposta)
| Situação | Resultado |
|---|---|
| Todos respondidos | `<lote>_ok.csv` completo, na ordem da fila; nada pendente |
| Alguns sem resposta | respondidos → `_ok.csv`; **só os pendentes** → `_loop.csv` (sem coluna `Resposta`) |
| Mesma execução | pendentes ganham `loop_rounds_per_run − 1` rodada(s) extra(s) |
| Ainda pendentes | `_loop.csv` espera a **próxima execução** (agende a tarefa periodicamente) |
| `max_loop_cycles` atingido | pendentes → `_nok.csv` para análise humana |
| Arquivo ilegível / colunas ausentes na entrada | Mantido em `Input`; evento de falha é registrado para correção e reexecução |

Códigos de saída: `0` tudo concluído · `1` há `_loop`/`_nok` · `2` entrada/config inválida · `3` erro inesperado.

## Operação
```powershell
futureminds run-all --config C:\Challenge\config\settings.yaml
schtasks /Create /SC HOURLY /TN "Challenge_FutureMinds3" /TR "C:\Challenge\.venv\Scripts\futureminds.exe run-all --config C:\Challenge\config\settings.yaml"
```
Lock órfão (`*.lock` em `Output\`) após queda: apague só depois de confirmar que nenhum processo está ativo.

## Testes e validação com 500 casos
```powershell
pytest -q                 # suíte completa (inclui o dataset de 500 casos com gabarito)
ruff check src tests ; mypy src
python tests\dataset_factory.py --valid 500 --invalid 40 --out C:\Challenge\Input\validacao.csv --expected gabarito.csv
```
`tests\data\dataset_500.csv` traz **500 reclamações bancárias distintas** mais 40 linhas inválidas. `dataset_500_expected.csv` é o gabarito: fila esperada, motivo da rejeição e cenário por linha. O gerador é `tests\corpus.py`. Copie o CSV para `C:\Challenge\Input\validacao.csv` para uma validação ponta a ponta com a IA real.

## Validação da implantação
```powershell
futureminds check                 # ambiente, TXT, pastas, IA (tensão, resposta, concorrência)
futureminds check --smoke --rows 40   # Processos 1 e 2 reais em amostra temporária
futureminds check --golden        # 500 textos distintos vs. gabarito (use --golden-rows 150 para amostra)
```
Saída `0` = sem FAIL; `1` = há FAIL. Relatório JSON em `Logs\preflight_<ts>.json`. Roteiro completo, com critérios de aceite e Go/No-Go, em `docs\DEPLOY.md`.

## Documentação
`docs\DEPLOY.md` (requisitos do ambiente e gates de aceite) · `docs\SPEC.md` (requisitos, contratos, regras, estados) · `docs\C4.md` (C4 níveis 1–4, dinâmico, estados, implantação) · `docs\ADR.md`.

## Observabilidade e privacidade
- Logs operacionais JSON têm `schema_version`, timestamps UTC, severidade, `run_id`, `trace_id`, evento, serviço e atributos; auditorias JSONL incluem `event_id` e sequência monotônica.
- Estatísticas agregadas incluem contagens de arquivos/linhas, origens de classificação, confiança e latências médias e percentis (p50/p95/p99), falhas e estado final. O texto integral da reclamação não é incluído nos logs.
- PII detectada em campos textuais dos logs é mascarada. Chaves de credenciais e tokens são redigidas. A amostra `examples/observability.synthetic.jsonc` é exclusivamente sintética e demonstra o contrato estatístico.

## Dicas para StackSpot
- HTTP 429 e 5xx são retentados com backoff; HTTP 401 renova o token automaticamente. Credencial inválida interrompe com erro claro (código de saída 3).
- Se a conta limitar requisições, reduza `llm_workers`; o que falhar vai para `_loop`.
- Endpoints usados: `https://idm.stackspot.com/{realm}/oidc/oauth/token` e `https://genai-inference-app.stackspot.com/v1/agent/{agent_id}/chat` (sobrescreva com `stackspot_auth_url` e `llm_base_url` se sua conta usar outro host).
