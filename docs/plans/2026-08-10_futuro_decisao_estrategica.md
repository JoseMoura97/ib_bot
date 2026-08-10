# Plano futuro — Decisão estratégica + licenciamento B2B do arquivo alt-data (atualização 2026-08-10)

Este ficheiro **atualiza e substitui**
`docs/plans/2026-07-20_futuro_decisao_estrategica.md` (mantém-se no disco como
histórico, não apagar) — o conteúdo é o mesmo objetivo, com o gate e os
números re-verificados a 2026-08-10 e um novo aviso sobre o finding CRÍTICO
C1 do audit de hoje.

## Gate de arranque (obrigatório — verificar antes de começar)

**Só começa quando (1) o plano de fixes `docs/plans/2026-08-10_plano_fixes.md`
tiver os passos 1 e 2 verdes E (2) a fase `a1_altdata_b2b` do Conductor tiver
o export empacotado com ≥30 partições (não é mais um gate de "dias na DB" —
esse já foi cumprido em 07-26; é um gate de export técnico).** Verificar com:

```bash
# (1a) paper_rebalance_daily corrigido ou explicitamente desligado
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT status, count(*) FROM paper_rebalance_logs WHERE timestamp > now() - interval '2 days' GROUP BY status"
# esperado: ou aparecem linhas SUCCESS, ou aparece zero linhas (tarefa desligada) —
# NUNCA aceitar continuar se ainda houver ERROR novo sem explicação registada

# (1b) funding ledger existe
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "\d paper_funding_ledger"
# esperado: tabela existe

# (2) export empacotado >= 30 partições
ls /home/servidor/Desktop/cursor-projects/ib_bot/.worktrees/phase-a1_altdata_b2b-2ac2/exports/congress_pit/ 2>/dev/null | grep -c "^date="
# esperado: >= 30 (eram 16 em 2026-08-10; o arquivo fonte já tinha 29 dias
# distintos nessa data — o passo de export só precisa de re-correr para apanhar)
```

Se qualquer verificação falhar, **não avançar** — voltar mais tarde. Há uma
entrada de `plan_knowledge` do Conductor já a agendar a reentrada no
worktree `phase-a1_altdata_b2b-2ac2` para **2026-08-12** — confirma primeiro
se essa reentrada já correu (`git -C
/home/servidor/Desktop/cursor-projects/ib_bot/.worktrees/phase-a1_altdata_b2b-2ac2
log -3` e conta as partições de novo) antes de assumir que precisas de a
disparar tu mesmo.

## Contexto para o executor

Este plano assume que já leste `docs/audits/2026-08-10_audit_profundo.md` e
`docs/plans/2026-08-10_plano_fixes.md` (contexto de paths/DBs/regras é o
mesmo, não repetido aqui). O projeto está pausado desde maio de 2026 porque
nenhuma das 56 estratégias de trading tem vantagem real comprovada (audit v4,
26-mai-2026). O **caminho recomendado por esse audit** (e re-confirmado por
todos os audits seguintes, incluindo este) não é "encontrar mais alpha" — é
**licenciar os dados alternativos que o sistema já recolhe** (trades de
congressistas dos EUA, holdings 13F de fundos famosos, etc., todos de fontes
públicas/gratuitas) a compradores B2B (fundos, emissores de ETF). Este plano
só executa a PARTE TÉCNICA (QA + empacotamento + material comercial) — **o
contacto com compradores é 100% decisão do José**, o executor nunca contacta
ninguém de fora.

**IMPORTANTE — porque este plano ainda não arrancou há 3 semanas:** o gate
técnico de tempo (14 dias de arquivo) foi cumprido em ~2026-07-26. Desde
então, a frota tem mantido o arquivo vivo (21 commits automáticos
`qa(altdata): daily receipt`) mas **ninguém disparou o passo de export final
nem apresentou o one-pager ao José**. Não repetir este padrão — se o gate
técnico abrir e este plano não arrancar dentro de ~3 dias, escalar
explicitamente ao José em vez de deixar o arquivo crescer indefinidamente sem
conversão em ação.

## Passo 1 — QA diário do arquivo alt-data

**Objetivo:** confirmar que as ~11 fontes/dia recolhidas desde 2026-07-13
(29 dias distintos verificados hoje) são de confiança antes de empacotar
qualquer coisa para venda.

```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "
SELECT as_of_date, count(*) AS rows, count(DISTINCT source) AS sources
FROM altdata_snapshots
GROUP BY 1 ORDER BY 1"
```

Para cada dia, confirmar: `rows` não cai mais de 20% face à média móvel de 7
dias, e nenhuma fonte falta 2 dias seguidos.

**Oráculo de aceitação:**
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc "
SELECT count(*) FROM (
  SELECT as_of_date d, count(*) c FROM altdata_snapshots
  WHERE as_of_date >= current_date - 13
  GROUP BY 1
) t WHERE c < 7"
```
Esperado: `0`.

**Gotchas:** a coluna certa é `as_of_date` (confirmado hoje via `\d
altdata_snapshots` — **não** `captured_at::date` como o plano de 07-20
indicava; `captured_at` também existe mas é o timestamp de quando o job
correu, `as_of_date` é a data do dado em si — usa sempre `as_of_date` para
agrupar por vintage).

## Passo 2 — Re-exportar o dataset licenciável (congressional trades point-in-time) até ≥30 partições

**Objetivo:** o worktree `phase-a1_altdata_b2b-2ac2` já tem 16 partições
(2026-07-13 → 07-28) e o código de export intacto — só falta re-correr contra
o estado atual da tabela fonte (29 dias distintos a 2026-08-10).

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot/.worktrees/phase-a1_altdata_b2b-2ac2
git log -3 --oneline   # confirmar que ainda está em 4455e52 ou mais recente
python3 scripts/export_congress_pit.py \
  --source-table altdata_snapshots \
  --filter-source house_financial_disclosure_index,house_periodic_transaction_report_index \
  --out exports/congress_pit/ \
  --partition-by as_of_date
```

**REGRA DURA (não negociável):** 100% das linhas exportadas têm de vir de
fontes livres/gratuitas. Dados da Quiver (paga) estão **PROIBIDOS** neste
dataset:

```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT DISTINCT source FROM altdata_snapshots WHERE source ILIKE '%quiver%'"
```
Esperado: `0 rows`.

**Oráculo de aceitação:**
```bash
ls exports/congress_pit/ | grep -c "^date="
```
Esperado: `>= 30`.

```bash
python3 -c "
import pandas as pd
df = pd.read_parquet('exports/congress_pit/')
print(len(df), 'linhas')
print(df.head(3))
"
```
Esperado: abre sem erro.

Fazer spot-check manual de 3 trades aleatórias contra o site oficial de
disclosures do congresso dos EUA (`https://disclosures-clerk.house.gov/` ou
`https://efdsearch.senate.gov/`) — registar o resultado no `_DATASHEET.md`
existente (não recriar do zero).

**Rollback:** `rm -rf exports/congress_pit/` — não afeta a tabela fonte.

**Gotchas:** não misturar fontes pagas; documentar claramente que a cobertura
histórica começa em 2026-07.

## Passo 3 — Merge do trabalho do worktree para `main` e entrega do one-pager ao José

**Objetivo:** os 2 commits do worktree (`4455e52` PTR trade evidence,
`c6b4c43` filing-index vintages) continuam por fazer merge para `main` — fazer
isso antes de considerar o passo comercial "pronto".

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git log --oneline main..conductor/phase-a1_altdata_b2b-2ac2
git merge --no-ff conductor/phase-a1_altdata_b2b-2ac2 -m "merge(a1): congress PIT export + PTR evidence"
```

Prepara o one-pager (1 página, Markdown ou PDF): o que é o dataset, cobertura
real (2026-07 em diante, nunca inventar mais história), exemplo de 5 linhas,
comparação de preço com concorrentes citados no audit v4 (Quiver licenciou
dados semelhantes por $2.5M; Unusual Whales cobra royalties em ~$307M de AUM
de ETFs NANC/KRUZ — usar como referência de mercado, não como promessa de
valor).

Entregar ao José pelo **canal normal de comunicação do agente** (nunca
Telegram-spam, nunca contacto direto com terceiros). Registar a entrega e a
resposta do José no plano do Conductor.

**Oráculo de aceitação:**
```bash
conductor plan show ib_bot -v | grep -A3 a1_altdata_b2b
```
Esperado: uma entrada nova de resposta do José registada (licenciar / não
licenciar / adiar / retomar pessoal).

**Rollback:** não aplicável — entrega de informação, não muda sistemas.

**Gotchas:** o audit v4 (26-maio-2026, memória `project_ib_bot_audit.md`) já
fez a análise de mercado completa — reutilizar esses números, não repetir a
pesquisa do zero.

## Se a resposta do José for "matar o projeto"

Seguir para `docs/plans/2026-08-10_futuro_hardening_sunset.md`, que só
arranca exatamente nesse cenário.

## Se a resposta do José for "retomar em modo pessoal/família"

**Antes de confiar em qualquer curva de equity paper existente**, confirmar
que o finding CRÍTICO C1 do audit de 2026-08-10 (`paper_rebalance_daily_task`
100% quebrado desde 2026-05-27) está mesmo corrigido — não retomar decisões
com base numa carteira que não rebalanceia há meses. Ver plano de fixes passo
1 antes de qualquer coisa.
