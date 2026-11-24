# Changelog

## 1.0.1 — Correção do diretório raiz

- Alterado o caminho-base padrão de instalação, configuração e exemplos para `C:\FutureMinds`.
- Atualizados critérios de implantação, especificação e diagramas para refletir o mesmo diretório.
- Mantida a configuração de subpastas `Input` e `Processados` sob a raiz do projeto.

## 1.0.0 — Release 1.0

- Nova V2 publicada como pacote independente `challenge-futureminds3`.
- Processamento sequencial e estável de qualquer nome de CSV elegível em `Input`.
- Arquivamento sem sobrescrita em `Processados`, somente após a geração de artefatos e logs; entradas com falha permanecem disponíveis para correção.
- Eventos JSON/JSONL versionados com IDs de evento, sequência monotônica, `run_id`, `trace_id`, atributos de processo e redaction de PII/credenciais.
- Estatísticas agregadas de execução e distribuições de latência, com percentis, contadores de sucesso/falha e eventos de lifecycle.
- Amostra `examples/observability.synthetic.jsonc` composta apenas por dados sintéticos.
- Rastreabilidade de versão do prompt, provedor/modelo selecionado e métricas de fallback no resumo do classificador.
- Testes de lote, arquivamento, tratamento de falhas, proteção de logs e percentis, além da suíte de regressão herdada.
- Documentação de arquitetura de IA, implantação, critérios de validação e operação.

### Limites da versão

- Entradas de negócio aceitas são arquivos CSV com as seis colunas documentadas; formatos desconhecidos são ignorados.
- A IA precisa ser configurada separadamente. A validação offline e o corpus sintético não substituem o aceite de qualidade em dados reais.
- Respostas geradas continuam sendo recomendações para revisão humana, não ações enviadas automaticamente.
