# Plano Futuro 3/3 — Retestar paper trading depois do bug corrigido (2026-09-21)

**Gate de arranque:** só começa quando o Passo 1 do `2026-09-21_plano_fixes.md` estiver verde —
verificar com:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker exec ib_bot-worker-1 python3 -c "from app.worker.tasks import paper_rebalance_daily_task; paper_rebalance_daily_task()"
docker logs ib_bot-worker-1 --since 2m | grep -c "paper_rebalance_daily.*error"
# esperado: 0
```

## Contexto para o executor

Depois de corrigido o bug `tuple index out of range` (38 dias corridos de falha confirmados até
2026-09-20), as duas contas de paper trading vão voltar a rebalancear de verdade pela primeira
vez desde 2026-05-09 (conta 2, 138 trades acumulados até essa data) ou desde sempre (conta 1,
nunca teve um trade real). Isto é uma mudança estrutural nos dados — **não avaliar a qualidade da
correção pelos mesmos números antigos**, e não confundir a primeira semana de rebalanceamento real
com um novo bug.

## Passo 1 — Deixar correr 2 semanas completas antes de qualquer conclusão

**Objetivo:** ter dados suficientes para separar "ruído normal de rebalanceamento" de "novo
problema".

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# Confirmar todos os dias sem erro, não só o primeiro:
docker logs ib_bot-worker-1 --since 336h | grep "paper_rebalance_daily" | grep -c error
```

**Oráculo de aceitação:** `0` erros em 14 dias corridos consecutivos a partir da data do fix.

**Rollback:** não aplicável (é só observação).

**Gotchas:** não declarar sucesso ao fim de 1-2 dias — mercados fechados em fins de semana/feriados
podem mascarar um problema intermitente; 14 dias cobre pelo menos 2 fins de semana e um ciclo
completo de rebalanceamento semanal (se a cadência das estratégias for semanal).

## Passo 2 — Recalcular métricas de paper trading desde a correção, separadas do histórico "congelado"

**Objetivo:** não misturar os 4+ meses de dados "carteira parada reavaliada a preço de mercado"
com os dados novos de rebalanceamento ativo — são duas séries com significados diferentes.

**Comandos:**
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "
select account_id, date(timestamp), equity
from paper_snapshots
where account_id in (1,2) and timestamp > '<DATA-DO-FIX>'
order by account_id, timestamp;
"
```
Produzir um `docs/audits/<data>_paper_ledger_reconciliacao.md` (seguir o formato de
`docs/audits/2026-07-12_paper_ledger_reconciliacao.md`, já existente no repo) comparando:
Sharpe/Sortino/drawdown do período "congelado" (2026-05-26 a `<DATA-DO-FIX>`) vs. período
"rebalanceamento ativo" (`<DATA-DO-FIX>` em diante).

**Oráculo de aceitação:** o documento existe e tem as duas séries separadas, com pelo menos 14
dias de dados no período "ativo".

**Rollback:** apagar o documento (não afeta sistema).

**Gotchas:** se o Sharpe do período "ativo" for MUITO diferente (para melhor ou pior) do período
"congelado", isso é esperado e não é por si só evidência de bug ou de edge — é só a diferença
entre "mercado" e "estratégia realmente a rebalancear". Só investigar como bug se houver erros nos
logs (Passo 1) ou valores impossíveis (equity negativo, posições que não batem certo com o
capital).

## Passo 3 — Decidir se vale a pena re-lançar a auditoria de investibilidade (DSR) só para a conta 2

**Objetivo:** avaliar se, com rebalanceamento ativo em vez de carteira parada, alguma das 9
estratégias configuradas nas contas de paper trading passa a mostrar sinal que a auditoria v4
(Deflated Sharpe Ratio, maio 2026) não via — sem prometer que vai passar.

**Comandos:**
```bash
grep -rn "strategies" /home/servidor/Desktop/cursor-projects/ib_bot/backend/app/api/routes/paper.py | head -10
```
Documentar (não implementar) num novo plano se a decisão for "sim, vale a pena" — este passo é só
avaliação, não execução do re-teste estatístico completo.

**Oráculo de aceitação:** decisão registada (sim/não/adiar) com justificação de 1 parágrafo, em
memória ou no documento do Passo 2.

**Rollback:** nenhum.

**Gotchas:** com só 9 estratégias em paper trading (vs. as 56 do backtest completo), a amostra é
pequena demais para tirar conclusões fortes de DSR num prazo curto — gerir expectativas do José
antes de prometer um veredicto novo.
