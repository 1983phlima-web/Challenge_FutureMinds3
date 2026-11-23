# Arquitetura e governança de IA

## Princípios

A solução separa domínio/regras determinísticas, orquestração de aplicação, infraestrutura de arquivos e adaptadores de modelos. A IA é usada para classificação e sugestão; validações de schema, codificação da fila, deduplicação e ordenação permanecem determinísticas. O provedor é injetado pela interface `LLMClient`, permitindo testes sem rede e troca controlada de implementação.

## Limites de confiança e segurança

- O texto de entrada é dado não confiável. O prompt instrui o modelo a ignorar instruções embutidas na reclamação; texto é delimitado e a saída é validada contra o contrato esperado.
- CPF, CNPJ, e-mail, cartão e telefone são mascarados antes do envio ao modelo quando `mask_pii: true`. O modo de produção deve manter essa opção ativa e ter aprovação de segurança/privacidade para o provedor e a finalidade do tratamento.
- Segredos são obtidos do ambiente de execução; não devem constar em YAML, logs, testes, exemplos ou commits.
- Logs e trilhas de auditoria registram metadados operacionais, identificadores de execução e indicadores agregados. Não registrar prompt completo, texto integral da reclamação, resposta bruta do modelo ou credenciais.
- A camada de logging aplica mascaramento adicional de dados pessoais e redação de campos com aparência de credencial. Logs ainda exigem controle de acesso e prazo de retenção.

## Uso de saídas geradas

Respostas geradas são marcadas como `[Sugestão IA - revisar]`. Elas são recomendações para revisão humana e não são enviadas automaticamente ao cliente. Respostas de política aprovada são renderizadas a partir do texto cadastrado; a aprovação e a validade das políticas são responsabilidade do negócio.

## Avaliação e operação

A suíte usa um corpus sintético determinístico e um gabarito independente para testar qualidade, cobertura, rejeições, mascaramento, fallback e comportamento de lote. Antes do Go-Live, valide com amostra real rotulada por especialistas e acompanhe, por versão de modelo e hash do prompt, concordância por classe, erros graves, taxa de fallback, confiança e latência p50/p95/p99.

Monitore código de saída, CSVs que permaneçam em `Input` por falha, arquivos `_loop`/`_nok`, chamadas e falhas de provedor, latência, volume e taxa de rejeição. Interrompa ou reverta a automação se houver degradação de qualidade, exposição de dados ou aumento sustentado de falhas. Mudanças de modelo, prompt, regras e política devem ser avaliadas e versionadas separadamente.

## Limites

Os indicadores de confiança reportados são os valores retornados pelo modelo e não são, isoladamente, uma probabilidade calibrada. O corpus de teste é sintético e não substitui avaliação humana representativa. A arquitetura não constitui avaliação jurídica, de conformidade ou de risco do provedor.
