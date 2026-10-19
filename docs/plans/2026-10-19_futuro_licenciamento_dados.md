# Futuro — Licenciar o Arquivo de Dados PIT a Terceiros (B2B) (2026-10-19)

**Gate de arranque:** só começa quando o José decidir explicitamente avançar com esta opção no
plano `docs/plans/2026-10-19_futuro_decisao_estrategica.md` (passo 1, Opção A ou B podem
coexistir com este plano — licenciar dados não exige reativar trading). Verificar com:
```bash
grep -n "José decidiu" /home/servidor/.claude/projects/-home-servidor/memory/MEMORY-trading.md
```
→ esperado: existe uma linha a confirmar decisão de avançar com licenciamento. **Sem esta linha,
não avançar nenhum passo abaixo** — esta decisão está pendente há 99 dias (desde 2026-08-11) e
não deve ser assumida por omissão.

## Contexto para o executor (lê isto primeiro, sem precisar da conversa original)

Desde 13 de julho de 2026, o `ib_bot` guarda todos os dias uma "fotografia" (PIT — point-in-time)
de 11 fontes de dados públicas (relatórios de políticos dos EUA, 13F de fundos, dados de curto
interesse FINRA, contratos federais, COT da CFTC, etc.). Hoje (2026-10-19) tem **1086 linhas / 99
dias** acumulados, a crescer ~11 linhas/dia. Existe já um documento de venda pronto
(`docs/altdata_b2b_one_pager_draft.md`) de uma auditoria anterior — este plano assume que esse
documento já foi revisto e só faltam os passos de EXECUÇÃO comercial/técnica.

**O que este arquivo vale (e não vale):** o valor NÃO é "sinal de trading" (as 56 estratégias que
usavam estes dados para prever preços já reprovaram) — é o **arquivo histórico point-in-time em
si**, que outras empresas/investigadores poderiam querer para os seus próprios estudos (evita que
tenham de reconstruir o histórico do zero, porque muitas destas fontes só mostram o estado atual,
não o que mostravam num dia passado).

**Paths importantes:**
- Documento de venda: `/home/servidor/Desktop/cursor-projects/ib_bot/docs/
  altdata_b2b_one_pager_draft.md`.
- Dados: tabela `altdata_snapshots` no Postgres do bot (`docker exec ib_bot-db-1 psql -U
  ibbot_app -d ibbot`), mais os backups offsite geridos por `infra/scripts/
  backup_altdata_snapshots.sh`.
- Base de dados tem um gatilho (`altdata_snapshots_reject_mutation`) que impede UPDATE/DELETE —
  os dados são imutáveis por desenho (importante para qualquer cliente que confie na integridade
  do arquivo).

**Regras obrigatórias:** as mesmas do plano de fixes. Adicional específico deste plano: **nenhum
passo aqui autoriza enviar dados a terceiros antes de confirmação explícita do José sobre
licença/preço/contrato** — isto é uma decisão comercial com implicações legais (dados de
congressistas/13F são públicos, mas o PACOTE curado point-in-time é o produto).

---

## Passo 1 — Validar o documento de venda com dados atuais

**Objetivo:** confirmar que o one-pager de venda ainda reflete o estado real do arquivo (99 dias,
não os números de quando foi escrito em agosto).

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
cat docs/altdata_b2b_one_pager_draft.md
docker exec ib_bot-db-1 psql -U ibbot_app -d ibbot -c \
  "SELECT source, count(*), min(as_of_date), max(as_of_date) FROM altdata_snapshots GROUP BY source ORDER BY source;"
```

**Oracle de aceitação:** o one-pager é atualizado (se necessário) para citar o número correto de
dias/fontes/linhas, com uma nota "dados verificados em 2026-10-19". Commit da atualização.

**Rollback:** `git revert <hash>` se a atualização introduzir um erro.

**Gotchas:** não prometer cobertura de fontes que já falharam parcialmente — o audit de hoje
mostra `quiver_congress_trades` excluído ("bulk endpoint timed out, requires licensed access") e
`house_periodic_transaction_report_index`/`house_financial_disclosure_index` como "index
metadata only, não parseia todos os anexos" — ser honesto sobre as limitações no one-pager.

---

## Passo 2 — Preparar um export de amostra (sem dados sensíveis/credenciais)

**Objetivo:** criar um export de demonstração (ex.: 30 dias de 2-3 fontes) para mostrar a
potenciais clientes, sem expor a infraestrutura de produção.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git worktree add -b feature/altdata-sample-export-20261019 \
  /home/servidor/ib-altdata-sample-20261019 \
  main
cd /home/servidor/ib-altdata-sample-20261019

# Export de amostra (read-only, só SELECT, para um ficheiro local — nunca enviar diretamente da BD)
docker exec ib_bot-db-1 psql -U ibbot_app -d ibbot -c \
  "\copy (SELECT source, as_of_date, n_rows, content_hash FROM altdata_snapshots WHERE source IN ('sec_13f_berkshire_hathaway','fred_market_regime') ORDER BY as_of_date) TO '/tmp/altdata_sample_metadata.csv' WITH CSV HEADER;"
cat /tmp/altdata_sample_metadata.csv | head -5
```

**Oracle de aceitação:** ficheiro de amostra gerado (metadados apenas: fonte, data, nº de linhas,
hash de conteúdo — NÃO o `payload` jsonb completo, que pode ser grande e deve ser entregue só sob
contrato). Confirmar com `wc -l /tmp/altdata_sample_metadata.csv`.

**Rollback:** apagar o ficheiro temporário (`rm /tmp/altdata_sample_metadata.csv`); nenhum
commit necessário para este passo (é só um export local).

**Gotchas:** nunca incluir o `payload` completo de nenhuma fonte na amostra pública sem
aprovação explícita — o one-pager deve vender o CONCEITO (histórico point-in-time íntegro, com
hash-chain de integridade) e os metadados, não o conteúdo completo de graça.

---

## Passo 3 — Decidir o modelo de preço/licença e formalizar

**Objetivo:** passo puramente comercial — fora do âmbito de execução técnica deste plano. O
José decide o modelo (subscrição mensal, licença por fonte, pagamento único por histórico
completo) com apoio de um advogado se necessário (dados públicos agregados têm geralmente menos
risco legal do que dados privados, mas confirmar antes de assinar qualquer contrato).

**Comandos exatos:** nenhum (decisão de negócio, não ação de sistema).

**Oracle de aceitação:** existe um contrato ou termo de serviço assinado, OU uma decisão
explícita de não avançar (registar em memória de qualquer forma, para não repetir esta
investigação noutra auditoria futura).

**Rollback:** não aplicável.

**Gotchas:** se a decisão for "não avançar", atualizar o plano de decisão estratégica
(`2026-10-19_futuro_decisao_estrategica.md`) para refletir isso e considerar se vale a pena
continuar a gastar armazenamento no arquivo PIT sem destino comercial (ligação ao achado ALTO #1
do audit).

---

## Fecho do plano

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git status --porcelain   # esperado: vazio
```
