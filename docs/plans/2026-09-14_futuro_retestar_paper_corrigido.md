# Plano Futuro 2/3 — Retestar estratégias com o motor de paper trading corrigido (2026-09-14)

**Gate de arranque:** só começa quando o Passo 1 do `2026-09-14_plano_fixes.md` estiver verde —
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
quebrado há pelo menos 24 dias; o audit de 2026-09-14 confirmou que continuou quebrado, sem
interrupção, até pelo menos 2026-09-13 (31 dias corridos de falha) — todas as tentativas de
rebalanceamento das 9 estratégias (contas 1 e 2) falhavam silenciosamente com `tuple index out of
range`. Isto significa que **toda a curva de equity de paper trading documentada até agora
(incluindo em auditorias anteriores) reflete uma carteira CONGELADA desde 2026-05-09, não um teste
ativo das estratégias** — inclusive a queda de quase 2% na conta 2 na semana de 07 a 13 de
setembro, que é só o mercado a corrigir sobre posições paradas, não uma decisão de saída de
nenhuma estratégia. Depois do Passo 1 do plano de fixes corrigir o bug, este plano futuro serve
para: (a) confirmar que os rebalanceamentos voltam a acontecer de facto, e (b) decidir, com dados
reais e frescos, se alguma das estratégias mostra sinal diferente do que a auditoria de
investibilidade v4 (maio de 2026) concluiu com o Deflated Sharpe Ratio (nenhuma das 56 passa).

**Importante — isto NÃO é para reabrir a discussão de investibilidade do zero.** A conclusão v4
(AUTORITATIVA) continua válida: nenhuma das 56 estratégias tem edge estatisticamente robusto
depois de corrigir para o facto de se terem testado 56 ideias. Este plano serve só para ter dados
de paper trading CORRETOS daqui em diante (não quebrados), não para reabrir a pergunta "vale a
pena ligar o robô a dinheiro real" — essa pergunta já tem resposta (não, edge decaindo/reprovado).

## Passo 1 — Confirmar rebalanceamento diário real por 14 dias corridos

**Objetivo:** ter prova de que a correção do Passo 1 do plano de fixes não é uma correção
cosmética (o erro desaparece mas nada muda na prática).

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# Correr diariamente (ou verificar retroativamente ao fim de 14 dias):
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "select account_id, count(*), max(timestamp) from paper_trades where timestamp > (CURRENT_DATE - 14) group by account_id;"
```

**Oráculo de aceitação:** ao fim de 14 dias corridos desde a correção, existem **linhas NOVAS em
`paper_trades`** para pelo menos a conta 2 (a conta 1 pode legitimamente não ter trades novos se
as regras das 3 estratégias Ackman/Burry/Howard Marks não gerarem sinal de rebalanceamento nesse
período — mas o rebalanceamento tem de ao menos EXECUTAR sem erro, mesmo que decida "não fazer
nada" corretamente).

**Rollback:** não aplicável (é só observação).

## Passo 2 — Recalcular métricas com dados pós-correção

**Objetivo:** ter uma curva de equity que reflita rebalanceamento real, não mercado sobre posições
paradas, para decisões futuras.

**Comandos:**
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -A -F',' -t -c \
  "select date(timestamp), equity from paper_snapshots where account_id=2 and timestamp > (CURRENT_DATE - 14) order by timestamp;"
```
Gerar novo `metrics.json` (mesmo formato do audit) comparando o Sharpe/Sortino/drawdown do período
PRÉ-correção (congelado, maio-setembro, já documentado) com o período PÓS-correção — a comparação
em si é o resultado interessante, não apenas o número novo isolado.

**Oráculo de aceitação:** documento comparativo existe com os dois períodos lado a lado.

## Passo 3 — Decisão informada (não reabrir o veredito v4)

**Objetivo:** se, e só se, os dados pós-correção de 90+ dias mostrarem um Sharpe consistentemente
diferente do esperado por acaso (o que é estatisticamente improvável dado o veredito v4, mas deve
ser verificado, não presumido), escalar ao José com os números — não decidir sozinho reabrir
capital real.

**Oráculo de aceitação:** ou (a) os números pós-correção continuam consistentes com "sem edge"
(nenhuma ação necessária, documentar e arquivar), ou (b) existe uma mensagem explícita ao José com
os números concretos, pedindo decisão — nunca uma alteração automática de `LIVE_AUTO_REBALANCE`.

**Gotchas:** 90 dias de paper trading NUNCA é suficiente para provar edge com confiança
estatística (a auditoria v4 já usou anos de dados e 56 estratégias e reprovou todas com Deflated
Sharpe) — trata este passo como "verificação de saúde do motor corrigido", não como "novo teste de
investibilidade". Não maquilhar isto como um turnaround de tese sem o rigor estatístico que a v4
já aplicou.
