# Plano Futuro — Decisão de negócio sobre o arquivo PIT (pós-fixes)

**Gate de arranque:** só começar quando o Passo 1-3 do `2026-10-12_plano_fixes.md` estiver verde
— verificar com:
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT status FROM paper_rebalance_logs WHERE account_id = 2 ORDER BY timestamp DESC LIMIT 1;"
```
→ deve devolver algo diferente de `ERROR` (idealmente `SUCCESS`). Não é um gate técnico rígido
(este plano é uma decisão de negócio, não depende tecnicamente do bug de caixa), mas convém que o
José não tenha de decidir sobre o futuro dos dados enquanto ainda há um bug crítico aberto a
distrair a atenção.

## Contexto para o executor

O **PIT (point-in-time) archive** é uma coleção diária de "fotografias" de 11 fontes de dados
públicas (compras de políticos dos EUA, 13F de fundos famosos, etc.) que o `ib_bot` guarda desde
2026-07-13, sem nunca apagar nem corrigir retroativamente. Em 2026-10-12 tem **1009 linhas / 92
dias** e cresce ~11 linhas/dia. O motivo original de guardar isto (alimentar as 56 estratégias de
trading) morreu em maio (nenhuma estratégia tem edge real). O que resta de valor é **vender o
acesso a estes dados** a terceiros (um produto B2B tipo Quiver Quantitative/Unusual Whales) — um
one-pager de vendas já está pronto em
`/home/servidor/Desktop/cursor-projects/ib_bot/docs/altdata_b2b_one_pager_draft.md` desde
2026-08-11, à espera de uma decisão do José há mais de 2 meses.

Este NÃO é um plano de engenharia — é um pedido de decisão. O "executor" deste plano é
principalmente alguém (agente ou o próprio José) que force a decisão a acontecer, e só depois
executa a consequência técnica escolhida.

## Passo 1 — Preparar a decisão (ler e resumir, não decidir por ele)

**Objetivo:** apresentar ao José, de forma compacta, as 3 opções reais e os seus custos/ganhos,
para ele decidir numa frase.

**Comandos exatos:**
```bash
cat /home/servidor/Desktop/cursor-projects/ib_bot/docs/altdata_b2b_one_pager_draft.md
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT count(*), count(distinct captured_at::date), min(captured_at), max(captured_at) \
   FROM altdata_snapshots;"
du -sh /home/servidor/Desktop/cursor-projects/ib_bot/backups/altdata_snapshots
```

**As 3 opções a apresentar (texto sugerido para a pergunta ao José):**
1. **Avançar com outreach comercial** (o one-pager já está pronto) — custo: tempo de vendas/
   networking, risco de reputação quase nulo (dados públicos agregados). Ganho potencial:
   receita nova, validação de que o motor de dados tem valor standalone.
2. **Arquivar e parar de gastar engenharia nisto** — desligar `ib-altdata-backup.timer` e
   `ib-altdata-qa.timer`, manter só `altdata_snapshot_daily_task` a correr de graça (ou parar
   tudo e exportar um dump final). Custo: zero manutenção futura. Perda: fecha a porta à opção 1
   sem voltar atrás facilmente (gaps de dados a partir da data de paragem).
3. **Continuar como está, sem decisão** (o status quo desde 08-11) — custo: nenhum imediato, mas
   acumula ~599 MB de dumps/ano no `.git` (ver achado ALTO do audit sobre o tamanho do repositório,
   2,1 GB hoje) e engenharia de manutenção (QA diário, backup noturno) sem retorno claro.

**Oracle de aceitação:** uma frase do José escolhendo 1, 2, ou 3 (ou uma variante), registada em
memória (ver passo 2). Sem isto, não avançar.

**Rollback:** nenhum (passo de comunicação).

**Gotchas:** não pressionar por uma resposta rápida — já passaram 2 meses, mais um dia não muda o
risco; o que importa é a próxima auditoria encontrar uma resposta registada, não inventada.

## Passo 2 — Registar a decisão e executar a consequência técnica mínima

**Objetivo:** uma vez que o José decida, aplicar SÓ a consequência técnica dessa escolha — nada
mais.

**Se escolher opção 1 (outreach comercial):**
```bash
# Nenhuma mudança técnica imediata — o one-pager já existe. Registar em memória:
# "José decidiu avançar com outreach B2B do PIT archive em <data>. One-pager:
#  docs/altdata_b2b_one_pager_draft.md. Próximo passo: ele próprio, não um agente, faz o outreach."
```
**Oracle de aceitação:** entrada de memória nova confirmável com `grep -n "outreach B2B"
MEMORY-trading.md`.

**Se escolher opção 2 (arquivar e parar):**
```bash
sudo systemctl disable --now ib-altdata-backup.timer ib-altdata-qa.timer
# Exportar um dump final antes de qualquer coisa:
docker exec ib_bot-db-1 pg_dump -U ibbot -d ibbot -t altdata_snapshots \
  -f /home/servidor/Desktop/cursor-projects/ib_bot/backups/altdata_snapshots/FINAL_ARCHIVE_$(date +%Y%m%d).dump
cd /home/servidor/Desktop/cursor-projects/ib_bot
git add backups/altdata_snapshots/FINAL_ARCHIVE_*.dump
git commit -m "chore(altdata): final archive dump before stopping daily PIT capture (José decision $(date +%Y-%m-%d))"
git push origin main
```
**Oracle de aceitação:**
```bash
systemctl is-enabled ib-altdata-backup.timer ib-altdata-qa.timer
```
→ esperado: `disabled` para ambos.

**Se escolher opção 3 (continuar sem decisão):** não fazer nada técnico; registar em memória que
a decisão foi explicitamente "continuar sem decidir, revisitar em <data futura, ex. +30 dias>" —
isto evita que a próxima auditoria trate isto como "ainda pendente por omissão" quando na verdade
foi uma escolha consciente.

**Rollback (opção 2):**
```bash
sudo systemctl enable --now ib-altdata-backup.timer ib-altdata-qa.timer
```

**Gotchas:**
- Nunca escolher a consequência técnica sem a frase explícita do José — um agente nunca decide
  isto por conta própria (é uma decisão de negócio, não um bug a corrigir).
- Se optar por arquivar (opção 2), confirmar que o `pg_dump` não corre durante a janela do backup
  noturno (04:3x WEST) para não colidir com o lock da BD.
