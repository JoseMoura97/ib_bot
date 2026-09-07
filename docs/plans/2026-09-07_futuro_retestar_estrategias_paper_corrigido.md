# Plano Futuro 2/3 — Retestar estratégias com o motor de paper trading corrigido (2026-09-07)

**Gate de arranque:** só começa quando o Passo 1 do `2026-09-07_plano_fixes.md` estiver verde —
verificar com:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker exec ib_bot-worker-1 python3 -c "from app.worker.tasks import paper_rebalance_daily_task; paper_rebalance_daily_task()"
docker logs ib_bot-worker-1 --since 5m | grep "paper_rebalance_daily.*error"
# esperado: SEM output (nenhuma linha "error=") — se aparecer qualquer "error=", o gate ainda
# não está verde, não avances.
```

## Contexto para o executor

O audit de 2026-09-07 (Finding CRÍTICO #0) descobriu que o motor diário de paper trading esteve
quebrado há pelo menos 24 dias — todas as tentativas de rebalanceamento das 9 estratégias (contas
1 e 2) falhavam silenciosamente com `tuple index out of range`. Isto significa que **toda a curva
de equity de paper trading documentada até agora (incluindo em auditorias anteriores) reflete uma
carteira CONGELADA desde 2026-05-09, não um teste ativo das estratégias**. Depois do Passo 1 do
plano de fixes corrigir o bug, este plano futuro serve para: (a) confirmar que os rebalanceamentos
voltam a acontecer de facto, e (b) decidir, com dados reais e frescos, se alguma das estratégias
mostra sinal diferente do que a auditoria de investibilidade v4 (maio de 2026, memória
`project_ib_bot_audit.md`) concluiu com o Deflated Sharpe Ratio (nenhuma das 56 passa).

**Importante — isto NÃO é para reabrir a discussão de investibilidade do zero.** A conclusão v4
(AUTORITATIVA) continua válida: nenhuma das 56 estratégias tem edge estatisticamente robusto
depois de corrigir para o facto de se terem testado 56 ideias. Este plano serve só para ter dados
de paper trading CORRETOS daqui em diante (não quebrados), não para reabrir a pergunta "vale a
pena ligar o robô a dinheiro real" — essa pergunta já tem resposta (não, edge decaindo/reprovado).

## Passo 1 — Confirmar rebalanceamentos reais nas 2 semanas seguintes ao fix

**Objetivo:** verificar que `paper_trades` volta a crescer (deixa de estar parado em
`max(timestamp)=2026-05-09`).

**Comandos (correr ~14 dias depois do fix do Passo 1 do plano de fixes):**
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -t -A -c "select account_id, count(*), max(timestamp)::date from paper_trades group by account_id"
```

**Oráculo de aceitação:** `max(timestamp)` para pelo menos uma das contas é posterior à data do
fix (não mais 2026-05-09), E `count(*)` aumentou face ao valor de 2026-09-07 (138 para a conta 2).

**Rollback:** N/A (só leitura).

**Gotchas:** algumas estratégias têm cadência trimestral ("quarterly" — ver
`resolve_frequency`/`is_due` em `backend/app/worker/tasks.py`), por isso pode levar semanas até
`is_due` disparar para todas; não esperar mudança em 1-2 dias para as estratégias de cadência
lenta.

## Passo 2 — Recalcular métricas de paper trading com dados pós-fix, separados do período congelado

**Objetivo:** produzir uma curva de equity que distinga claramente "período congelado (bug)" de
"período com rebalanceamento real (pós-fix)", para não confundir os dois em relatórios futuros.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -t -A -F"," -c "
select timestamp::date, cash, equity from paper_snapshots where account_id=2 order by timestamp asc
" > /tmp/paper_acct2_full.csv
python3 -c "
import csv
rows = []
with open('/tmp/paper_acct2_full.csv') as f:
    for line in f:
        parts = line.strip().split(',')
        if len(parts) == 3:
            rows.append(parts)
# Marca o corte na data do fix — substitui <DATA_DO_FIX> pela data real do commit do Passo 1.
CUTOFF = '<DATA_DO_FIX>'
before = [r for r in rows if r[0] < CUTOFF]
after = [r for r in rows if r[0] >= CUTOFF]
print(f'Período congelado (bug): {len(before)} dias, {before[0][2]} -> {before[-1][2] if before else \"N/A\"}')
print(f'Período pós-fix (real): {len(after)} dias')
"
```

**Oráculo de aceitação:** existe um ficheiro
`docs/reports/2026-XX-XX_paper_trading_pos_fix.md` (data real de quando este passo correr) que
documenta separadamente os dois períodos, com métricas (Sharpe, drawdown, win rate) calculadas
SÓ sobre o período pós-fix — nunca misturando os dois.

**Rollback:** N/A (só relatório).

**Gotchas:** não recalcular retroativamente as métricas do período congelado como se fossem
"resultado da estratégia" — esse período é 100% mark-to-market de posições paradas, documentar
isso explicitamente sempre que aparecer em qualquer relatório futuro.

## Passo 3 — Decisão final: manter paper trading a correr, ou parar também (dado que v4 já reprovou as estratégias)

**Objetivo:** evitar o mesmo padrão do arquivo PIT (recurso a correr sozinho sem decisão) — depois
de confirmar que o motor está tecnicamente saudável, perguntar explicitamente ao José se vale a
pena continuar a correr paper trading diário para estratégias já reprovadas pelo Deflated Sharpe
Ratio, ou se deve ficar só como registo histórico (parar novos rebalanceamentos, manter os dados).

**Comandos:** apresentar a pergunta ao José (mesma disciplina do passo 0 do plano de fixes —
resposta registada em memória, não presumida).

**Oráculo de aceitação:** ficheiro de memória novo com a decisão, datado.

**Rollback:** N/A.
