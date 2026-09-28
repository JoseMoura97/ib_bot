# Futuro 2 — Retestar estratégias com o motor de paper trading corrigido (2026-09-28)

**Gate de arranque:** só começa quando o Passo 1 do plano de fixes de 2026-09-28 estiver verde —
verificar com:
```
docker logs ib_bot-worker-1 --since 48h | grep paper_rebalance_daily | grep -c "error="
```
Tem de devolver `0` (nenhum erro nas últimas 48h, cobrindo pelo menos 2 execuções diárias
consecutivas às 15:00 WEST) antes de começar este plano.

## Contexto para o executor

O bug crítico do `paper_rebalance_daily_task` (`tuple index out of range`, ativo desde
2026-08-14, ver auditoria 2026-09-28) significa que TODA a curva de equity de paper trading da
conta 2 desde então é só reavaliação de preço de mercado sobre uma carteira parada — não um teste
real de estratégia. Depois do fix (Futuro 2 do plano de fixes), é preciso confirmar que o
rebalanceamento voltou a funcionar de verdade e produzir métricas limpas, sem reabrir a decisão de
investibilidade já tomada em maio de 2026 (Deflated Sharpe Ratio reprovou as 56 estratégias — essa
conclusão NÃO muda só porque o paper trading volta a funcionar).

## Objetivo

Confirmar rebalanceamento ativo por pelo menos 2 semanas corridas e produzir um relatório curto
com as métricas reais (não confundir com "reabrir se vale a pena ir a live" — isso é uma decisão
de negócio separada e já foi tomada).

## Passo 1 — Monitorizar 2 semanas de rebalanceamento real

**Comandos exatos (correr diariamente ou agendar uma verificação):**
```
docker logs ib_bot-worker-1 --since 24h | grep paper_rebalance_daily
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "select account_id, count(*) from paper_trades where timestamp > now() - interval '14 days' group by account_id;"
```

**Oracle de aceitação:** pelo menos 1 trade novo por conta nas 2 semanas (ou confirmação explícita
de que nenhuma estratégia estava "due" nesse período pela sua cadência própria — reler
`resolve_frequency`/`is_due` em `backend/app/worker/tasks.py`).

## Passo 2 — Relatório de métricas reais pós-fix

**Comandos exatos:**
```
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -t -A -F',' -c \
  "select timestamp::date, equity from paper_snapshots where account_id=2 and timestamp > '<data do fix>' order by timestamp asc;"
```
Recalcula Sharpe/Sortino/drawdown com o mesmo método usado em `metrics.json` desta auditoria
(retornos diários, `sqrt(252)` para anualizar).

**Oracle de aceitação:** ficheiro `docs/plans/2026-09-28_futuro_retestar_paper_corrigido_relatorio.md`
com as métricas novas e uma frase explícita: "isto confirma/infirma que o motor voltou a testar
estratégias ativamente" — sem opinar sobre se deve ir a live (fora de âmbito).

**Rollback:** nenhum (é só leitura/relatório).

**Gotchas:** não uses os dados de ANTES do fix misturados com os de DEPOIS no mesmo cálculo de
Sharpe/drawdown — isso inflacionaria artificialmente as métricas com o período "congelado".
