# Plano futuro — Reconciliar e decidir o estudo 0006 (iron-fly de earnings) — 2026-07-12

**GATE DE ARRANQUE**: só começa quando o Passo 5 do plano de fixes estiver verde (forward
test corrigido OU conscientemente parado) E o Passo 4 (paper ledger) fechado. Verificar com:
`journalctl -u paper-ironfly.service -n 5 | grep -E 'logged [0-9]+'` (deve existir output
recente, ou o timer estar `inactive` por decisão registada).

## Contexto para o executor

- **O estudo**: 0006-earnings-vol, no repo `/home/servidor/Desktop/cursor-projects/trading`
  (branch `pead-stage0`). Tese: as opções (contratos que apostam no tamanho do movimento de
  uma ação) estão sistematicamente caras antes dos resultados trimestrais → vender essa
  "volatilidade implícita" ganha em média. Forma deployável: **iron-fly de asas largas a 10%**
  (vender call+put no preço atual, comprar proteções 10% acima/abaixo, segurar até ao fecho
  do dia da reação).
- **O conflito por resolver** (finding A2 do audit de 2026-07-12): o sweep INTRADAY com dados
  reais ThetaData (2026-05-27) deu held-out PF 1.42-1.78; o run multi-regime EOD
  (2026-05-28) deu **PF 0.06-0.37 em TODOS os anos**. Um dos dois está errado e ninguém
  investigou. Ficheiros: `trading/backtests/reports/0006_earnings_vol/
  {events_multiregime.parquet, peryear_multiregime.txt, intraday_events.parquet,
  intraday_report.html}` — TUDO já está no disco; a reconciliação é offline, custo zero.
- **Dados**: ThetaData está em FREE tier (o plano pago $80/mês caducou — confirmar no
  journal do `theta-terminal.service` a linha "Bundle:"). Não re-subscrever antes do gate
  do passo 3 abaixo.
- **Regras**: heavy compute via `runjob`; commits no mesmo turno; NENHUMA ordem real (se o
  estudo um dia for a live, é gated via `request_user_approval` — fora deste plano).

### Passo 1 — Autópsia da contradição EOD vs intraday

**Objetivo**: explicar, com números, por que o mesmo trade (iron-fly 10% asas, slip 0.25)
dá PF 1.42 num engine e PF 0.10 no outro.

**Comandos**:
```bash
cd /home/servidor/Desktop/cursor-projects/trading
python3 - <<'EOF'
import pandas as pd
eod = pd.read_parquet('backtests/reports/0006_earnings_vol/events_multiregime.parquet')
intr = pd.read_parquet('backtests/reports/0006_earnings_vol/intraday_events.parquet')
comum = set(zip(eod.symbol, eod.reaction_date.astype(str))) & set(zip(intr.symbol, intr.reaction_date.astype(str)))
print('eventos em comum:', len(comum))
# comparar, evento a evento, créditos/débitos de entrada, larguras de spread das asas e P&L
EOF
```
Adaptar nomes de colunas ao que existir (`df.columns`). Medir nos eventos em comum:
(1) crédito de entrada EOD vs intraday; (2) spread % das asas OTM em cada fonte; (3) P&L.
A hipótese principal: quotes EOD das asas 10%-OTM têm spreads enormes → slip 0.25 nelas
destrói o trade, enquanto intraday os spreads reais são 1.6-3.5%.

**Oracle de aceitação**: documento `studies/0006-earnings-vol/reconciliacao_eod_intraday.md`
commitado, com uma tabela nos eventos em comum que atribui a diferença de PF a componentes
(entrada/asas/saída) e um veredito de UMA linha: "o engine fiável é X porque Y".

**Rollback**: n/a (análise offline).

**Gotchas**: se os dois engines usam janelas de eventos diferentes (o EOD tem 3692 eventos
2019-2026, o intraday 2328 held-out), comparar SÓ a interseção; não concluir a partir de
médias agregadas de amostras diferentes.

### Passo 2 — Repor o forward test a produzir dados e defini-lo como juiz

**Objetivo**: com o universo corrigido (fix do plano de fixes), acumular ≥30 eventos
forward com preços mid e touch reais, e comparar com o backtest.

**Comandos**: acompanhar semanalmente:
```bash
python3 -c "import pandas as pd; df=pd.read_parquet('/home/servidor/Desktop/cursor-projects/trading/data/options_cache/paper_ironfly_ledger.parquet'); print(len(df)); print(df.tail())"
```

**Oracle de aceitação**: n≥30 eventos no ledger; relatório de 1 página (PF@mid, PF@touch,
gap mid-vs-touch) commitado em `studies/0006-earnings-vol/forward_30events.md`.

**Rollback**: n/a.

**Gotchas**: earnings vêm por época (temporadas de resultados jan/abr/jul/out) — 30 eventos
podem demorar 4-8 semanas; não desligar os timers no meio.

### Passo 3 — Decisão go/kill (gated)

**Objetivo**: com o Passo 1 (qual engine é fiável) + Passo 2 (forward real), decidir:
- **KILL** se o engine fiável disser PF<1 ou o forward mostrar gap mid-vs-fill que coma o edge.
- **CONTINUAR** (re-subscrever ThetaData $80/mês para CPCV completo + auditoria de caudas
  >10%) apenas se ambos forem positivos. Gastar dinheiro = decisão do José (propor via canal
  normal com os números; não subscrever por conta própria).

**Oracle de aceitação**: `phase-status.json` do estudo atualizado com o veredito e a memória
`project_earnings_vol.md` atualizada no mesmo turno.

**Rollback**: n/a (decisão documental).

**Gotchas**: lembrar a lição registada do próprio estudo: "não matar com um só conjunto de
parâmetros" — mas também não manter vivo um zombie: o critério de decisão fica escrito ANTES
de olhar para os dados do forward (pre-registration).
