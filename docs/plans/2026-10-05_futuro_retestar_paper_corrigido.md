# Futuro 3 — Retestar estratégias com o motor de paper trading corrigido (2026-10-05)

**Gate de arranque:** só começa quando o Passo 1 do plano de fixes de 2026-10-05 estiver `done`
(ou seja, a conta 2 deixa de falhar com `insufficient cash`) **E** se mantiver sem erro por pelo
menos 48h corridas — verificar com:
```
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT account_id, status, timestamp FROM paper_rebalance_logs WHERE timestamp > now() - interval '48 hours' ORDER BY timestamp;"
```
Tem de devolver zero linhas com `status='ERROR'` nas últimas 48h, cobrindo pelo menos 2 execuções
diárias consecutivas às 15:00 WEST, para ambas as contas, antes de começar este plano.

## Contexto para o executor

O bug crítico do `paper_rebalance_daily_task` (`tuple index out of range`, ativo 2026-08-14 a
2026-09-27) significava que toda a curva de equity de paper trading da conta 2 nesse período era
só reavaliação de preço de mercado sobre uma carteira parada — não um teste real de estratégia.
Esse bug foi corrigido em 2026-09-28 (commit `1391c6f`), mas a conta 2 imediatamente passou a
falhar com um erro diferente (`insufficient cash`, ver Futuro 1/Passo 1 do plano de fixes de hoje)
que continua sem correção à data desta auditoria. **Este plano só pode produzir números limpos
depois dos dois bugs (o antigo e o novo) estarem resolvidos e confirmados por 48h sem erro.**

Isto NÃO reabre a decisão de investibilidade já tomada em maio de 2026 (Deflated Sharpe Ratio
reprovou as 56 estratégias) — essa conclusão não muda só porque o paper trading volta a
funcionar. Também não reabre o estudo 0006 (earnings-vol iron-fly), que está KILL definitivo e
reconciliado desde 2026-07-16 (repo-irmão `trading`, não `ib_bot`) — não há contradição pendente
aí para investigar.

## Objetivo

Confirmar rebalanceamento ativo por pelo menos 2 semanas corridas, em ambas as contas, e produzir
um relatório curto com as métricas reais pós-fix (não confundir com "reabrir se vale a pena ir a
live" — isso é uma decisão de negócio separada, já tomada: não).

## Passo 1 — Monitorizar 2 semanas de rebalanceamento real em ambas as contas

**Comandos exatos (correr diariamente ou agendar uma verificação):**
```
docker logs ib_bot-worker-1 --since 24h | grep paper_rebalance_daily
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "select account_id, count(*) from paper_trades where timestamp > now() - interval '14 days' group by account_id;"
```

**Oracle de aceitação:** pelo menos 1 trade novo por conta nas 2 semanas (ou confirmação explícita
de que nenhuma estratégia estava "due" nesse período pela sua cadência própria — reler
`resolve_frequency`/`is_due` em `backend/app/worker/tasks.py`, já visto no fix de 09-28 a marcar a
conta 1 corretamente como `not due` entre execuções trimestrais).

## Passo 2 — Relatório de métricas reais pós-fix

**Comandos exatos:**
```
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -t -A -F',' -c \
  "select account_id, timestamp::date, equity from paper_snapshots where timestamp > '<data em que ambas as contas ficaram sem erro>' order by account_id, timestamp asc;"
```
Recalcula Sharpe/Sortino/drawdown com o mesmo método usado no `metrics.json` da auditoria de
2026-10-05 (retornos diários simples, dedupe por data tomando o último valor do dia,
`sqrt(252)` para anualizar).

**Oracle de aceitação:** ficheiro
`docs/plans/2026-10-05_futuro_retestar_paper_corrigido_relatorio.md` com as métricas novas, para
as duas contas separadamente, e uma frase explícita: "isto confirma/infirma que o motor voltou a
testar estratégias ativamente em ambas as contas" — sem opinar sobre se deve ir a live (fora de
âmbito, já decidido).

**Rollback:** nenhum (é só leitura/relatório).

**Gotchas:** não misturar dados de ANTES do fix da conta 2 com os de DEPOIS no mesmo cálculo de
Sharpe/drawdown — isso inflacionaria/deflacionaria artificialmente as métricas com o período
"congelado". Para a conta 1, o corte relevante é 2026-09-28 (dia do fix); para a conta 2, usar a
data em que o Futuro 1 do plano de fixes confirmar o fix definitivo (não é a mesma data).
