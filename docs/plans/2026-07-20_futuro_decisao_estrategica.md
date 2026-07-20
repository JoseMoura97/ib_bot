# Plano futuro — Decisão estratégica + licenciamento B2B do arquivo alt-data

## Gate de arranque (obrigatório — verificar antes de começar)

**Só começa quando (1) o plano de fixes `docs/plans/2026-07-20_plano_fixes.md`
estiver com os passos 1-2 verdes E (2) a fase `a1_altdata_b2b` do Conductor
tiver o gate de 14 vintages cumprido.** Verificar com:

```bash
# (1) fixes verdes — passo 1 (backtest normal) e passo 2 (funding ledger)
systemctl show ib-backtests.service --property=Result,ExecMainStatus
# esperado: success / 0, com InactiveEnterTimestamp posterior a 2026-07-26 04:15 UTC
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "\d paper_funding_ledger"
# esperado: tabela existe

# (2) gate de 14 vintages
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT count(DISTINCT captured_at::date) FROM altdata_snapshots"
# esperado: >= 14
```

Se qualquer uma destas verificações falhar, **não avançar** — voltar mais
tarde. ETA estimada para o gate (2): 2026-07-26 (verificado no audit de
2026-07-20: 8/14 vintages, ritmo de +1/dia).

## Contexto para o executor

Este plano assume que já leste `docs/audits/2026-07-20_audit_profundo.md`
e `docs/plans/2026-07-20_plano_fixes.md` (contexto de paths/DBs/regras é o
mesmo, não repetido aqui). O projeto está pausado desde maio de 2026
porque nenhuma das 56 estratégias de trading tem vantagem real comprovada
(audit v4, 26-mai-2026). O **caminho recomendado por esse audit** (e
re-confirmado por todos os audits seguintes) não é "encontrar mais
alpha" — é **licenciar os dados alternativos que o sistema já recolhe**
(trades de congressistas dos EUA, holdings 13F de fundos famosos, etc.,
todos de fontes públicas/gratuitas) a compradores B2B (fundos, emissores
de ETF). Este plano só executa a PARTE TÉCNICA (QA + empacotamento +
material comercial) — **o contacto com compradores é 100% decisão do
José**, o executor nunca contacta ninguém de fora.

## Passo 1 — QA diário do arquivo alt-data

**Objetivo:** confirmar que os ~11 fontes/dia recolhidas desde 2026-07-13
são de confiança antes de empacotar qualquer coisa para venda.

**Comandos exatos:**

```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "
SELECT captured_at::date, count(*) AS rows, count(DISTINCT source) AS sources
FROM altdata_snapshots
GROUP BY 1 ORDER BY 1"
```

Para cada dia, confirmar: `rows` não cai mais de 20% face à média móvel de
7 dias, e nenhuma fonte falta 2 dias seguidos (uma fonte falhar 1 dia é
tolerável — o desenho é "uma fonte falhar não mata o snapshot inteiro",
confirmado no audit de 2026-07-12 fase f5).

**Oráculo de aceitação:**

```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc "
SELECT count(*) FROM (
  SELECT captured_at::date d, count(*) c FROM altdata_snapshots
  WHERE captured_at::date >= current_date - 13
  GROUP BY 1
) t WHERE c < 7"
```

Esperado: `0` (nenhum dia com menos de 7 fontes num universo de ~11 —
ajustar o limiar `7` se o número normal de fontes mudar; usa a média
observada no audit, 9-11/dia, como referência).

**Rollback:** não aplicável (só leitura).

**Gotchas:** a coluna certa é `captured_at`, não `created_at` (bug já
identificado e corrigido no gate do Conductor a 2026-07-14 — não repetir
o erro).

## Passo 2 — Empacotar 1 dataset licenciável (congressional trades point-in-time)

**Objetivo:** produzir o primeiro artefacto vendável: export em parquet
(formato de dados colunar, eficiente e padrão da indústria) particionado
por dia, com um `DATASHEET.md` a documentar a origem e o schema.

**Comandos exatos:**

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
mkdir -p exports/congress_pit
python3 scripts/export_congress_pit.py \
  --source-table altdata_snapshots \
  --filter-source congress \
  --out exports/congress_pit/ \
  --partition-by captured_at
```

(Se `scripts/export_congress_pit.py` não existir ainda, criar seguindo o
padrão de outros scripts de export do repo — `grep -rln "to_parquet" scripts/`
para achar um exemplo a copiar.)

**REGRA DURA (não negociável):** 100% das linhas exportadas têm de vir de
fontes livres/gratuitas. Dados da Quiver (paga) estão **PROIBIDOS** neste
dataset — confirmar antes de exportar:

```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT DISTINCT source FROM altdata_snapshots WHERE source ILIKE '%quiver%'"
```

Esperado: `0 rows` nesta query aplicada ao subconjunto exportado (se a
tabela tiver alguma linha de Quiver por engano nalgum outro contexto,
excluir explicitamente no filtro do export).

**Oráculo de aceitação:**

```bash
ls /home/servidor/Desktop/cursor-projects/ib_bot/exports/congress_pit/ | grep -c "^date="
```

Esperado: `>= 30` partições diárias (nota: não prometer histórico anterior
a 2026-07 — o arquivo só começou nessa data, dizer isso explicitamente no
`DATASHEET.md`).

```bash
python3 -c "
import pandas as pd
df = pd.read_parquet('/home/servidor/Desktop/cursor-projects/ib_bot/exports/congress_pit/')
print(len(df), 'linhas')
print(df.head(3))
"
```

Esperado: abre sem erro, mostra linhas com colunas de trade + data de
captura.

Fazer spot-check manual de 3 trades aleatórias contra o site oficial de
disclosures do congresso dos EUA (`https://disclosures-clerk.house.gov/`
ou `https://efdsearch.senate.gov/`) — confirmar que o político, ticker e
data batem certo. Registar o resultado do spot-check no
`DATASHEET.md`.

**Rollback:** `rm -rf exports/congress_pit/` — não afeta a tabela fonte
`altdata_snapshots`, é só um export derivado.

**Gotchas:** não misturar fontes pagas; documentar claramente no
`DATASHEET.md` que a cobertura histórica começa em 2026-07 (não fingir
ter mais história do que existe).

## Passo 3 — Preparar o one-pager comercial e ENTREGAR AO JOSÉ (não a compradores)

**Objetivo:** ter material pronto para o José decidir se e como avançar
com licenciamento B2B — **o executor não contacta ninguém fora do
servidor**.

**Comandos exatos:**

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# Criar o one-pager (1 página, Markdown ou PDF) com: o que é o dataset,
# cobertura (data de início real, não inventada), exemplo de 5 linhas,
# comparação de preço com concorrentes citados no audit v4 (Quiver
# licenciou dados semelhantes por $2.5M; Unusual Whales cobra royalties
# em ~$307M de AUM de ETFs NANC/KRUZ — usar como referência de mercado,
# não como promessa de valor).
```

Entregar ao José pelo **canal normal de comunicação do agente** (nunca
Telegram-spam, nunca contacto direto com terceiros). Registar a entrega e
a resposta do José no plano do Conductor (`plan_knowledge`, `kind='decision'`).

**Oráculo de aceitação:**

```bash
psql conductor -c "
SELECT id, title, created_at FROM plan_knowledge
WHERE plan_id = (SELECT id FROM project_plans WHERE slug='ib_bot' AND status IN ('executing','approved') ORDER BY created_at DESC LIMIT 1)
AND kind = 'decision'
ORDER BY created_at DESC LIMIT 3"
```

Esperado: pelo menos 1 linha nova com a resposta do José registada
(licenciar / não licenciar / adiar).

**Rollback:** não aplicável — este passo é entrega de informação, não
muda sistemas.

**Gotchas:** o audit v4 (26-maio-2026) já fez a análise de mercado
completa (Quiver, Unusual Whales, Autopilot, dub) — reutilizar esses
números, não repetir a pesquisa do zero. Ver
`~/.claude/projects/-home-servidor/memory/project_ib_bot_audit.md`.

## Se a resposta do José for "matar o projeto"

Não executar este passo aqui — seguir para o plano
`docs/plans/2026-07-20_futuro_hardening_sunset.md`, que só arranca
exatamente nesse cenário.
