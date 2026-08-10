# Audit profundo — IB Bot (PAUSADO) — 2026-08-10

Auditor: agente Fable (modo ultracode), sessão `mega-audit-2026-08-10`.
Timezone de leitura: ART (UTC-3, Buenos Aires). Timestamps do sistema capturados
em WEST/UTC (fuso do servidor) e convertidos onde relevante.

Este é o **terceiro** audit profundo deste projeto. O primeiro foi
`docs/audits/2026-07-12_audit_profundo.md`, o segundo
`docs/audits/2026-07-20_audit_profundo.md`. Este documento **re-verifica tudo do
zero** (não assume que nada aguentou) contra o estado real do servidor a
2026-08-10, e regista: o que continua bom, o que regrediu, o que ainda não foi
corrigido de auditorias anteriores, e o que é genuinamente novo.

---

## (a) O que é este projeto — para miúdos

O **IB Bot** é um robô de investimento automático ligado à **Interactive
Brokers (IB)** — uma corretora (empresa que compra e vende ações por nós) —
através de um programa chamado **IB Gateway**. A ideia era copiar as
compras/vendas de gente "esperta": políticos americanos (que têm de declarar as
suas transações em bolsa por lei), fundos famosos (como o de Warren Buffett ou
Michael Burry, que têm de reportar trimestralmente à SEC — o regulador do
mercado dos EUA — num documento chamado **13F**), e outros sinais
"alternativos" (ex.: quantas pessoas falam de uma ação no Reddit).

O sistema tem três partes:
1. **Backtests** — simulações: "se eu tivesse seguido esta regra nos últimos
   anos, quanto teria ganho?" (56 receitas/estratégias diferentes).
2. **Paper trading** — negociar com dinheiro a fingir, para testar sem risco.
3. **Execução real** — a parte que compraria/venderia ações verdadeiras —
   construída, mas **nunca ligada a sério** (zero ordens reais desde sempre).

Um audit interno rigoroso de 26 de maio de 2026 (o "v4", ver glossário)
concluiu que **nenhuma das 56 estratégias tem uma vantagem real** acima do que
se explicaria por sorte (testar 56 coisas e escolher a melhor no fim quase
sempre parece boa por acaso). Por isso o projeto foi **pausado**: não foi
apagado, mas ninguém está a decidir trades com ele. Um estudo irmão, "0006 /
Iron Wing" (vender opções caras à volta dos resultados trimestrais das
empresas), correu num repositório vizinho (`trading`) e também **morreu** em
2026-07-16, com dados reais a confirmar que perde dinheiro.

---

## (b) Evolução até hoje (timeline)

Fonte: `git log` dos 3 repositórios, memórias do agente
(`~/.claude/projects/-home-servidor/memory/project_ib_bot*.md`,
`project_pead.md`, `project_earnings_vol.md`), e os 2 audits anteriores.

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repo `ib_bot` — sistema base de trading IB |
| 2026-02-19 → 05-09 | Conta paper "Main Paper" (conta 2) criada com $100.000; 138 trades executadas (só nesta janela — **nunca mais houve uma trade paper bem-sucedida**, ver finding CRÍTICO C1) |
| 2026-05 (início) | Preparação para "go-live": fractional shares, conta real `U23842862` aberta com ~€1.000, API deixada **read-only** |
| 2026-05-23 | Estudo irmão **PEAD** (repo `trading`) **REJEITADO/FECHADO** — era beta de mercado disfarçado de skill |
| 2026-05-26 | **Audit v4 AUTHORITATIVE**: nenhuma das 56 estratégias sobrevive a Deflated Sharpe + fora-da-amostra; recomendação nº1 = arquivar snapshots diários point-in-time (só começou 7 semanas depois) |
| 2026-06 (última 3ª semana) | Último commit de produto novo (fase alt-data / stack v2); projeto entra formalmente em pausa |
| 2026-07-12 | **1º audit profundo**: CRÍTICO — VNC do IB Gateway aberto sem password para toda a rede; várias sessões live diárias desnecessárias |
| 2026-07-13 | Triagem do José: projeto entra em **dormência seletiva** (gateway/ibeam/VNC OFF; lifeos mantém-se via MCP); plano `e36e04ec` aprovado |
| 2026-07-13 → 07-19 | Plano `e36e04ec` executa `f1`(dormência) `f2`(backtest+alerta) `f3`(reconciliação paper ledger) `f4`(merge para main) `f5`(arquivo alt-data) `x1`(reconcilia contradição estudo 0006) `x2`(mata estudo 0006 com 36 eventos forward) — todos fecham `done` |
| 2026-07-16 | Estudo **0006 KILLED** — PF@mid 0,776, PF@touch 0,256 em 36 eventos forward reais |
| 2026-07-20 | **2º audit profundo**: 0 CRÍTICOs, 2 ALTOs novos (A1 disparo automático do backtest ainda não provado; A2 endpoint de funding do paper sem ledger de auditoria), 3 MÉDIOs (M1 sem data de decisão estratégica; M2 cache de disco sem limpeza; M3 sem teste de regressão às 56 estratégias) |
| 2026-07-20 → 08-09 | `qa(altdata): daily receipt` — 21 commits diários automáticos a documentar o arquivo alt-data a crescer; nenhum outro trabalho de produto |
| 2026-07-26 | ETA do gate de 14 dias do arquivo alt-data (fase `a1_altdata_b2b`) — **cumprido** silenciosamente, sem decisão do José associada (ver M1 → agora ALTO, finding A2 abaixo) |
| **2026-08-10 (hoje)** | Este audit — re-verificação completa; ver secção (c). Descoberto: `paper_rebalance_daily_task` falha **100% das vezes desde 2026-05-27** (75 dias, 150/150 erros) — nenhuma auditoria anterior tinha caracterizado isto como falha ativa contínua |

---

## (c) Estado concreto HOJE (2026-08-10, verificado nesta sessão)

### Dinheiro real (conta ligada via MCP — Model Context Protocol, a "ponte" que
liga este agente à conta real da Interactive Brokers do José)

- `get_account_summary` (chamado nesta sessão): **net liquidation €28.302,82**,
  leverage 1,11, moeda base EUR (subiu de €26.784 em 07-20 e €26.981 em 07-13 —
  variação de mercado, não de trading do bot).
- `get_account_positions`: **1 posição** — 70 ações **BRK B** (Berkshire
  Hathaway classe B), preço $525,85, valor $36.809,50, PnL não-realizado
  +$2.442,35. **Esta posição NÃO é do ib_bot** — é uma posição manual do José,
  não gerida por nenhum código deste projeto (confirmado: nunca houve uma
  ordem do bot para BRK B).
- Base de dados do próprio bot (`ib_bot-db-1`, Postgres 16, utilizador
  `ibbot`, DB `ibbot`, 21 tabelas): `ib_orders=0`, `ib_trades=0`,
  `live_execution_requests=0`. **Zero ordens reais desde sempre**, confirmado
  hoje por `SELECT count(*)` direto às tabelas.
- `live_rebalance_audit=25` linhas — todas dry-run/preview antigas (9-22 maio),
  nunca uma execução real.

### Serviços e processos (systemd + Docker, verificado com `systemctl`,
`docker ps`, `ss -tlnp`, `journalctl`, ficheiros de log)

| Processo | Tipo | Pertence a | Estado hoje | Nota |
|---|---|---|---|---|
| `ibgateway.service` | service | ib_bot | inactive/dead | Dormência confirmada, mantém-se |
| `xvfb-ibgw.service` | service | ib_bot | inactive/dead | Dormência confirmada |
| `ibeam` (Client Portal) | docker | ib_bot | **não existe container** | Removido |
| Stack Docker `ib_bot` v1 (db/redis/api/worker/beat/web/nginx) | 7 containers | ib_bot | **ok, a correr** | api/worker/beat up 2 semanas (porta 8001); db/redis up ~2 meses; web+nginx (porta 8090) up 5 semanas |
| `ib_bot-v2` stack (`:8092`) | — | ib_bot-v2 | **não existe nenhum container nem porta aberta** | Continua desligada |
| `ib-bot-v2-frontend.service` (`:3001`) | service | ib_bot | **active/running** | Painel que o José usa, fala com API v1 :8001 |
| `ib-backtests.timer`/`.service` | timer semanal (dom 04:15 UTC) | ib_bot | **ok** | Última corrida 2026-08-09 05:16-06:08 WEST (aprox), `56/56 estratégias`, `BACKTEST_COMPLETION status=success`, log confirmado linha a linha. Próximo disparo: dom 2026-08-16 |
| `ib-backtests-alert.service` | OnFailure | ib_bot | armado | Não disparou desde 07-19 (não precisou) |
| `lifeos-ib-refresh.timer` | timer diário 05:15 UTC | lifeos (externo) | **ok** | Último disparo 05:15 WEST hoje, 1h48min atrás no momento da verificação |
| `theta-terminal.service` | service | repo `trading` (não é ib_bot) | active, plano FREE | Usado pelo estudo 0006 (já morto) para o monitor passivo |
| `paper-ironfly.timer` (repo `trading`) | timer diário | repo `trading` (não é ib_bot) | **ok, vigília passiva** | Ledger com 646 linhas (era 44 em 07-13, 12 em 07-14); estudo morto, José decidiu manter como monitor de custo zero. PF@touch pós-kill (619 eventos desde 07-16): **0,031** — continua a confirmar a decisão KILL, não é um erro |
| `theta-learned`, `historical-backfill`, `execution-metrics`, `cost-recalibration` | services/timers | **Polymarket, projeto diferente** | ativos | Confirmado hoje via `systemctl cat`: `WorkingDirectory=.../polytrader-bot-master`. **Não tocar neste projeto** |

### Backtest semanal — estado detalhado

- Última corrida (timer normal, não assistida): início ~2026-08-09 05:16 WEST,
  log `/var/log/ib-backtests.log` linha 45507-45520 confirma
  `Generated plot data for 56/56 strategies` e
  `BACKTEST_COMPLETION status=success strategies=56/56 price_source=yfinance`.
  Isto **fecha definitivamente o finding A1 do audit de 07-20** ("o disparo
  automático nunca foi provado sem intervenção manual") — já foram várias
  corridas semanais consecutivas 100% automáticas e verdes desde então.
- `.cache/yf_prices/` (cache de preços em disco): **487 MB, 2.756 ficheiros**
  hoje (era 473 MB/2.752 em 07-20) — continua a crescer ~1 MB/semana, sem
  política de retenção (finding M2 de 07-20, **ainda não corrigido**, ver (d)).

### Paper trading — curva de equity E automação de rebalanceamento

- 2 contas paper na DB: conta 1 ("Main Paper") **sempre em $100.000,00 flat**
  — nunca teve trades, conta de controlo.
- Conta 2 é a "real": 88 posições, 138 trades históricas (fev→mai 2026, e
  nunca mais desde então).
- **Reconciliação de contabilidade (já feita em
  `docs/audits/2026-07-12_paper_ledger_reconciliacao.md`, re-confirmada hoje
  por SQL direto):** o saldo só fecha aritmeticamente com um **crédito de
  $70.000,00 sem lançamento de auditoria** (endpoint `POST
  /paper/accounts/{id}/fund` altera `paper_cash.balance` diretamente, sem
  gravar quem/quando/porquê). **A curva anterior a 2026-05-26 continua marcada
  como não-evidência.**
- **NOVO nesta sessão — a automação diária de rebalanceamento está 100%
  quebrada há 75 dias e ninguém tinha caracterizado isto como uma falha ativa
  contínua:** a tarefa `paper_rebalance_daily_task` (Celery, corre todos os
  dias às 15:00 UTC) tenta rebalancear as 2 contas paper e **falha sempre**
  com `IndexError: tuple index out of range`, desde `2026-05-27 15:00:00` até
  hoje `2026-08-09 15:00:00` — **150 de 150 tentativas registadas em
  `paper_rebalance_logs` são `ERROR`, zero são `SUCCESS`, em toda a história
  da tabela.** Ver finding CRÍTICO C1 abaixo — é por isto que não há trades
  novas desde 9 de maio, apesar do sistema "parecer" estar a funcionar (a
  tarefa é marcada `succeeded` no Celery porque o erro é apanhado e só gera um
  log `WARNING`, nunca propaga falha).
- Enquanto isso, uma tarefa DIFERENTE e independente (`paper_snapshot_daily_task`,
  21:30 UTC) continua a gravar snapshots diários de equity da carteira
  **congelada** (sem rebalanceamentos desde 9-mai), mark-to-market pelos
  preços de mercado atuais. **77 pontos diários** de 2026-05-26 a 2026-08-09.
  Isto faz o número de equity subir e descer só por deriva de preço das 88
  posições originais — não é performance de estratégia nenhuma, é uma
  carteira "compra e esquece" com dados de conta contaminados pelo crédito de
  $70.000. Ver `metrics.json` para a série completa e métricas calculadas.
- Total do período medido (26-mai → 09-ago, 76 pontos): **+$4.805,15
  (+2,70%)**, `maxDD` **-$9.577,09 (-5,24%)**, Sharpe anualizado **1,05**
  (Sortino 1,57), win-rate diário 42,7%. **Estes números não são prova de
  skill de nenhuma estratégia** — são a deriva de mercado de uma carteira
  fixa de 88 ações + ETFs escolhida uma vez em fevereiro, com o alerta
  aritmético dos $70.000 ainda por explicar.

### Arquivo alt-data point-in-time (`altdata_snapshots`)

- Recomendação nº1 do audit v4 (26-mai): "a coisa de maior ROI é começar a
  guardar snapshots datados". Está a funcionar de forma estável desde
  2026-07-13.
- Hoje: **29 dias distintos** de vintages (`captured_at`), 11 linhas/dia
  consistentes, até 2026-08-10 inclusive. O gate de tempo mínimo de 14 dias
  (fase `a1_altdata_b2b`) foi ultrapassado há 2 semanas.
- **Mas a fase continua `blocked` no Conductor** — não por falta de dados na
  DB, mas porque o **export empacotado** (worktree
  `.worktrees/phase-a1_altdata_b2b-2ac2`, `exports/congress_pit/`) só tem
  **16 partições** (2026-07-13 → 07-28) — o passo de export não acompanhou o
  crescimento da tabela fonte (que já tem 29 dias). O gate técnico real é
  `>= 30 partições exportadas`, não `>= 14 dias na DB`. Há uma entrada de
  `plan_knowledge` que já regista isto e agenda um reentrada em
  **2026-08-12** para re-exportar. **Não é uma decisão pendente do José** — é
  um passo técnico por terminar.

### Repositórios e worktrees

- `ib_bot` (principal): branch `main`, `git status` **limpo**, 15 commits à
  frente de `origin/main` (nunca fez `git push` desde então — ver finding
  BAIXO).
- `ib_bot-v2`: worktree `frontend-v2` (decomissionada), 2 ficheiros
  modificados (`.conductor/context.md`, `frontend/next-env.d.ts`) e um
  diretório `.verify/` não rastreado — resíduo irrelevante.
- `ib_bot-altdata-wt`: worktree `alt-data-consolidation`, limpo.
- Worktrees extra ainda no disco: `.worktrees/phase-f5_altdata_arquivo-6090`
  (fase `f5`, `done` desde 07-14 — **ainda não removido, mesmo residual do
  audit de 07-20, finding BAIXO B1 continua aberto**) e
  `.worktrees/phase-a1_altdata_b2b-2ac2` (fase `a1`, ainda ativa, este
  correto manter).

### Estado do Conductor (orquestrador da frota de agentes)

- Plano `ib_bot` (post-triagem 2026-07-12): **7 de 8 fases `done`**
  (`f1`…`f5`, `x1`, `x2`); `a1_altdata_b2b` **`blocked`** (gate técnico de
  30 partições, ver acima — auto-desbloqueia, sem ação humana pendente).
- Não existe nenhum plano novo do Conductor a cobrir os findings A1/A2/M1-M3
  do audit de 2026-07-20 — foram corrigidos manualmente por commits diretos
  em alguns casos (A1 sim, via as corridas semanais verdes) mas **não** no
  caso do endpoint de funding (A2) nem do cache de disco (M2) nem do teste de
  regressão (M3) — ver secção (d).

---

## (d) Findings ordenados por gravidade

### CRÍTICO

**C1 — A automação diária de rebalanceamento do paper trading está 100%
quebrada há 75 dias, silenciosamente, e continua a correr todos os dias sem
que ninguém tenha reparado.**
`paper_rebalance_daily_task` (Celery beat, `crontab(hour=15, minute=0)` UTC,
`backend/app/worker/celery_app.py:41-44`) tenta rebalancear as 2 alocações
paper (contas 1 e 2) todos os dias. Desde **2026-05-27 15:00:00** até
**2026-08-09 15:00:00** — **150 execuções, 150 erros, 0 sucessos** — falha
sempre com `IndexError: tuple index out of range`
(`backend/app/worker/tasks.py:559-570`). O código apanha a exceção, grava uma
linha `ERROR` em `paper_rebalance_logs` e continua — a tarefa Celery em si é
reportada como `succeeded` no log do worker (`docker logs ib_bot-worker-1`
mostra `Task paper_rebalance_daily_task[...] succeeded in 0.15s: None`
imediatamente a seguir aos 2 `WARNING` de erro). **Isto significa que
qualquer pessoa a olhar só para o journal/Celery vê "tudo bem" quando na
realidade a funcionalidade central do paper trading está morta desde maio.**
Não é dinheiro real (ambas as contas são paper), mas é exatamente o padrão de
falha silenciosa que os audits anteriores (07-12, 07-20) andaram à procura —
e não encontraram, porque nenhum tinha lido `paper_rebalance_logs` além de
"existem 47 erros" (citado no relatório de reconciliação de 07-13 só como
limite à prova histórica, não como bug ativo a corrigir).
**Evidência:** `docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT
status, count(*), min(timestamp), max(timestamp) FROM paper_rebalance_logs
GROUP BY status"` → `ERROR | 150 | 2026-05-27 15:00:00.297759 | 2026-08-09
15:00:00.150554` (zero linhas `SUCCESS` em toda a tabela);
`docker logs ib_bot-worker-1 --since 48h | grep paper_rebalance` →
`paper_rebalance_daily: account=1 portfolio=... error=tuple index out of
range` e o mesmo para `account=2`, todos os dias.

### ALTO

**A1 — O endpoint de funding do paper trading continua sem ledger de
auditoria (finding A2 do audit de 07-20, NÃO CORRIGIDO 3 semanas depois).**
`POST /paper/accounts/{account_id}/fund`
(`backend/app/api/routes/paper.py:95-102`) continua a fazer
`acct.balance = float(acct.balance) + float(body.amount); db.commit()` sem
escrever em nenhuma tabela de auditoria. O plano de fixes de 07-20 (passo 2)
já tinha o desenho completo (migração Alembic, tabela
`paper_funding_ledger`, exigir `reason`/`actor`) mas **nunca foi aplicado** —
confirmado hoje: `SELECT to_regclass('public.paper_funding_ledger')` devolve
vazio (a tabela não existe). Não é dinheiro real, mas é o mesmo padrão
perigoso identificado há 3 semanas, ainda vivo no código.
**Evidência:** `grep -n "def fund_paper_account" -A 8
backend/app/api/routes/paper.py` (mostra a escrita direta); `docker exec
ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT to_regclass('public.paper_funding_ledger')"`
→ vazio.

**A2 — A decisão estratégica do José (B2B / retomar pessoal / matar) continua
por marcar, agora 3+ semanas depois do gate técnico ter ficado pronto
(finding M1 do audit de 07-20, ESCALADO de MÉDIO para ALTO por antiguidade).**
O arquivo alt-data está a crescer de forma saudável há quase um mês (29 dias
distintos hoje). O trabalho técnico de preparação (dormência, backtest com
alerta, reconciliação do paper ledger, arquivo alt-data) está praticamente
todo feito. Falta só um passo comercial (export final + one-pager) e uma
decisão do José. Sem essa decisão, o projeto fica **"pausado para sempre" por
inércia** — 21 commits automáticos consecutivos de `qa(altdata): daily
receipt` desde 07-20 mostram que a frota está a manter o sistema vivo em
piloto automático, mas ninguém está a converter isso em ação.
**Evidência:** `conductor plan show ib_bot -v` → fase `a1_altdata_b2b`
`blocked` desde `2026-07-12`, sem nenhuma entrada `plan_knowledge kind=decision`
associada; `git log --oneline --since=2026-07-20 -- .` → 21/26 commits são
`qa(altdata): daily receipt`, zero commits de produto/decisão.

### MÉDIO

**M1 — Cache de preços em disco continua sem retenção (finding M2 de 07-20,
NÃO CORRIGIDO).**
`.cache/yf_prices/` tem **487 MB, 2.756 ficheiros** hoje (era 473 MB/2.752 em
07-20 — crescimento de ~3%/3 semanas). O script `scripts/prune_yf_cache.py`
recomendado no plano de fixes de 07-20 não existe (`find . -iname
"*prune_yf_cache*"` → vazio), e não há timer `prune-yf-cache.timer`. Não é
urgente (487 MB é pequeno face aos 232 GB livres no disco — 87% ocupado no
total do servidor, mas isso é outros projetos), mas continua sem política.

**M2 — Sem teste de regressão real às 56 estratégias (finding M3 de 07-20,
parcialmente enganoso — existe um teste, mas não cobre o que foi pedido).**
`backend/tests/test_backtest_regression.py` existe, mas é de **2026-04-30**
(anterior ao próprio finding M3 de 07-20) e testa tolerância de
CAGR/Sharpe/drawdown por estratégia a partir do `plot_data.json` já gerado —
**não** verifica `len(strategies) >= 54` nem falha se `plot_data.json`
contiver menos estratégias do que o esperado nem grepa "No tickers found" no
log mais recente, que era o desenho pedido no plano de 07-20. Continua a não
existir um teste automático que apanhe uma estratégia a desaparecer
silenciosamente do catálogo.

**M3 — Repo local 15 commits à frente de `origin/main`, nunca `git push`
desde 07-20.**
`git status` está limpo e `main` está atualizado localmente, mas
`origin/main` no GitHub está 15 commits atrás (todos os `qa(altdata): daily
receipt` + os fixes de dormência do finding f1). Não é um risco imediato
(o servidor é a única máquina que executa o projeto), mas é um ponto único de
falha para o histórico — um disco corrompido no servidor perderia 3 semanas
de trabalho não publicado.

### BAIXO

**B1 — Resíduo de worktree da fase `f5` (já `done` desde 07-14) ainda no
disco, mesmo finding do audit de 07-20, ainda não limpo.**
`ib_bot/.worktrees/phase-f5_altdata_arquivo-6090` continua presente.
Inofensivo, só desarruma.

**B2 — Artefactos de audit anteriores (`section.json`, `metrics.json`) ficaram
parados na fotografia de 2026-07-12, nunca atualizados no audit de 07-20.**
Isto significa que qualquer painel/consumidor automático que leia
`docs/audits/ib_bot/section.json` estava a mostrar dados de 4 semanas atrás
(status "vermelho" com o VNC sem password, já corrigido há um mês) até esta
sessão os substituir. Recomenda-se atualizar estes 2 ficheiros em **todo**
audit futuro, não só o `.md`.

---

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Corrigir `paper_rebalance_daily_task` (C1)** — é o único CRÍTICO, está
   ativo AGORA (corre todos os dias), e é a causa raiz de "porque não há
   trades paper novas desde maio" que 2 audits anteriores não tinham
   identificado. Baixo esforço: capturar o traceback completo primeiro
   (a mensagem atual não tem linha nenhuma), depois corrigir ou, no mínimo,
   desativar a tarefa explicitamente enquanto o projeto está pausado (uma
   tarefa que falha 100% das vezes há 75 dias não deve continuar a correr
   sem decisão). Ver plano de fixes passo 1.
2. **Fechar o buraco do endpoint de funding paper (A1, era A2 em 07-20)** —
   o desenho já existe no plano de 07-20, só falta aplicá-lo. Ver plano de
   fixes passo 2.
3. **Forçar a decisão estratégica (A2, era M1 em 07-20)** — 3+ semanas de
   atraso sobre um gate que já está pronto; sem isto, todo o resto é
   manutenção de um projeto que nunca converte em ação. Ver plano futuro
   "decisão estratégica" (atualizado).
4. Adicionar retenção ao cache de disco (M1) e um teste de regressão real às
   56 estratégias que verifique contagem + "No tickers found" (M2) — baixo
   risco, baixo esforço.
5. `git push` do `main` local para `origin/main` (M3) — 1 comando, zero
   risco, fecha um ponto único de falha.
6. Limpar o worktree residual da fase `f5` (B1) e atualizar
   `section.json`/`metrics.json` em cada audit futuro (B2) — 1 minuto, zero
   risco.

---

## (f) Riscos se nada for feito

- **Financeiro direto: baixo.** Zero ordens reais desde sempre, gateway live
  desligado, API read-only na conta real do bot, ThetaData nunca comprado.
  O único dinheiro real ligado a esta família de contas é a posição pessoal
  do José (BRK B) — não gerida por código deste projeto.
- **Risco de confiança nos dados: real, mas contido.** Se algum dia alguém
  (José ou um agente) olhar para a curva de equity paper e achar que mostra
  "o sistema a funcionar", está enganado em dois níveis: (1) o nível
  absoluto já está contaminado pelos $70.000 sem ledger; (2) a FORMA da
  curva desde 26-mai também não representa nenhuma estratégia ativa — é
  deriva de mercado de uma carteira congelada, porque o rebalanceamento
  diário falha sempre. Isto já é hoje um finding auditado (C1), mas se
  ninguém corrigir, continuará a acumular "falsos dias de dados" que
  parecem uma track record e não são.
- **Risco operacional: baixo.** O backtest semanal está estável há 3
  corridas consecutivas automáticas verdes; o alerta `OnFailure` está
  armado e testado (6 disparos reais em 07-19).
- **Risco de oportunidade: crescente.** O arquivo point-in-time (o único
  ativo que "ganha valor sozinho", segundo o audit v4) está pronto há 2
  semanas para o passo comercial, mas continua parado por falta de decisão.
  Cada semana que passa sem decisão é uma semana de manutenção de infra
  (7 containers, 2 timers, ~465 MB RAM) que não converte em nada — nem
  receita, nem aprendizagem nova, nem encerramento limpo.
- **Risco de deriva silenciosa: confirmado, não hipotético.** Este é o 3º
  audit em 4 semanas e cada um encontrou pelo menos 1 finding novo que os
  anteriores não tinham visto (07-12: VNC sem password; 07-20: funding sem
  ledger; 08-10: rebalanceamento paper 100% quebrado há 75 dias). Um projeto
  pausado com automação ativa (timers, Celery beat) continua a gerar
  superfície de bugs silenciosos mesmo sem ninguém a trabalhar nele
  ativamente — a única defesa real é auditoria periódica ou desligar de
  vez (ver plano futuro de sunset).

---

## (g) Glossário

| Termo | Explicação |
|---|---|
| IB / Interactive Brokers | A corretora — empresa através da qual se compram/vendem ações. O "IB Gateway" é o programa dela que dá acesso à conta a partir de código. |
| MCP (Model Context Protocol) | Um conjunto de regras combinadas que permite a este agente de IA falar diretamente com sistemas externos (aqui, a conta IB do José) de forma segura, sem ver passwords. |
| API (Application Programming Interface) | A "porta" por onde dois programas falam um com o outro. |
| Backtest | Simulação histórica: "quanto teria ganho se tivesse seguido esta regra nos últimos anos". |
| Paper trading | Negociar com dinheiro a fingir para testar o sistema sem risco. |
| 13F | Relatório trimestral que os grandes fundos americanos são obrigados a entregar ao regulador (SEC) a listar as ações que têm — é público, e o bot usa-o para os imitar. |
| Alpha vs beta | Alpha é o ganho que vem de habilidade/informação real; beta é o ganho que qualquer pessoa teria só por estar no mercado (ex.: o índice sobe, tudo sobe). |
| Deflated Sharpe | Medida de "ganho por risco" corrigida pelo número de tentativas: se testas 56 estratégias, a melhor parece boa por pura sorte; esta correção desconta isso. |
| Sharpe / Sortino | Medidas de "ganho por unidade de risco": Sharpe usa toda a volatilidade, Sortino só a volatilidade dos dias maus (mais justa para estratégias que só "sofrem" em quedas). |
| Iron-fly | Aposta com opções em que se ganha se a ação mexer POUCO no dia dos resultados: vende-se o "seguro" caro no preço atual e compram-se proteções mais afastadas para limitar a perda máxima. |
| PF (Profit Factor) | Soma de tudo o que se ganhou a dividir pela soma de tudo o que se perdeu; acima de 1 é lucrativo. |
| Point-in-time / vintage | Guardar os dados exatamente como eram naquele dia. Sem isto, os backtests fazem batota sem querer (usam informação que só apareceu depois). |
| Celery / Celery beat | O "sistema de tarefas agendadas" do código do bot (dentro dos containers Docker) — como o systemd timer, mas por dentro da aplicação, não do sistema operativo. |
| IndexError / traceback | Um erro de programação em Python quando se tenta aceder a uma posição de uma lista/tupla que não existe; o "traceback" é o registo de onde exatamente no código isso aconteceu — sem ele, é muito mais difícil corrigir o bug. |
| Ledger de auditoria | Uma tabela que regista TODAS as alterações a um saldo (quem, quando, porquê) para que se possa sempre reconstruir a história — sem isto, um saldo "aparece" sem explicação. |
| systemd timer | O "despertador" do Linux: liga um programa automaticamente a horas certas. |
| Worktree (git) | Uma cópia paralela do mesmo repositório numa pasta diferente, ligada a uma branch diferente — usada para trabalhar em várias coisas ao mesmo tempo sem misturar. |
| Gate / time-gate | Uma condição que só se cumpre com o passar do tempo (aqui: esperar N dias de dados). |
| Drawdown (maxDD) | A maior queda desde um pico até ao fundo seguinte — mede o pior momento para quem tivesse entrado no topo. |
