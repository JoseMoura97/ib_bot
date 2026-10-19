# Audit Profundo — IB Bot (2026-10-19, ART / manhã em Portugal WEST)

> Sessão de auditoria: `/home/servidor/agent-workspaces/mega-audit-2026-10-19`.
> Todos os comandos abaixo foram corridos NESTA sessão (ground truth re-verificado, não copiado
> de memória nem de auditorias anteriores). Esta é a **13ª auditoria profunda** deste projeto
> (depois de 2026-07-12, 07-20, 08-10, 08-17, 08-24, 08-31, 09-07, 09-14, 09-21, 09-28, 10-05 e
> 10-12 — confirmado com `ls docs/audits/*.md`). Mesmo repositório
> (`/home/servidor/Desktop/cursor-projects/ib_bot`, HEAD de hoje `911ffdf`, 428 commits em `main`).

> **Nota sobre o brief:** o pedido descreve 3 roots (`ib_bot`, `ib_bot-v2`, `ib_bot-altdata-wt`) e
> timers a confirmar (`historical-backfill`, `execution-metrics`, `cost-recalibration`,
> `theta-learned`, `paper-ironfly`). Re-verificado agora (13ª vez consecutiva, `systemctl cat` +
> `git worktree list` corridos nesta sessão): `ib_bot-altdata-wt` **continua a não existir** no
> disco; `ib_bot-v2` é um **git worktree** do mesmo repositório (branch `frontend-v2`), não um
> projeto separado. Dos 5 timers citados no brief, **nenhum pertence ao `ib_bot`**: 4 são do
> projeto Polymarket (`polytrader-bot-master` — as suas próprias descrições systemd dizem
> literalmente "Polymarket"), e `paper-ironfly` pertence ao repo-irmão `/home/servidor/Desktop/
> cursor-projects/trading` (o bot de opções, dono do estudo 0006 de earnings-vol). Isto confirma,
> pela 13ª vez, a correção já feita na 1ª auditoria desta série.

> **Esta auditoria foca-se no que mudou desde 2026-10-12** (a 12ª auditoria, em
> `docs/audits/2026-10-12_audit_profundo.md`) em vez de repetir tudo do zero. Resumo da semana:
> **o bug crítico de 14 dias foi finalmente corrigido** (10-14); um novo timer de limpeza Docker
> foi criado mas **não funciona** (reporta sempre "0B reclaimed"); a decisão de negócio sobre o
> arquivo de dados PIT continua pendente, agora há 99 dias; e ainda não há nenhum dono formal no
> Conductor para este projeto, há 34 dias.

## (a) O que é este projeto (para um miúdo de 12 anos)

O **IB Bot** é um robô de computador que devia comprar e vender ações sozinho, usando a conta de
trading do José na **Interactive Brokers (IB — a corretora, a empresa que executa ordens de
compra/venda na bolsa por ti)**. A ideia era copiar o que "gente esperta" faz: políticos dos EUA
quando compram ações (que são obrigados por lei a publicar, no **STOCK Act**), fundos famosos
(como o de Warren Buffett) quando publicam os seus relatórios trimestrais (um **13F**, documento
que esses fundos são obrigados a publicar), ou gestores que apostam contra empresas (como Michael
Burry) — e ver se copiar essas jogadas dá dinheiro.

O robô testou **56 ideias diferentes** ("estratégias") em dados históricos com um motor de
**backtest** (simular "se eu tivesse seguido esta regra no passado, ganhava ou perdia?"). Um estudo
interno rigoroso de maio de 2026 (o **Deflated Sharpe Ratio** — um teste estatístico que pune ter
experimentado muitas ideias, porque quanto mais tentas, maior a hipótese de uma parecer boa só por
sorte) concluiu que **nenhuma das 56** tem ganho real acima do que se esperaria por sorte. O
projeto foi **pausado** nessa altura ao nível de decisão de negócio — e continua pausado hoje, 13ª
semana seguida a confirmar isto.

Tem quatro peças vivas hoje:
1. **Motor de backtest** — testa as 56 ideias no passado, de graça, sem risco. Corre sozinho todas
   as semanas (domingo de madrugada).
2. **Motor de execução real** — a peça que mandaria ordens verdadeiras para a IB. Está **desligada**
   desde 2026-08-27 por decisão do José ("dormência seletiva"), e continua desligada hoje.
3. **Arquivo "ponto-no-tempo" (PIT — point-in-time)** — desde 13 de julho de 2026, o robô tira uma
   "fotografia" todos os dias de 11 fontes de dados públicas e guarda-a para sempre, mesmo que a
   fonte original mude depois. Hoje tem 99 dias / 1086 linhas.
4. **"Paper trading"** (fingir que compra/vende ações com dinheiro que não existe, para testar o
   sistema sem risco) — corre todos os dias sozinho, duas contas fictícias. **Esta semana, o bug
   que travava uma das duas contas há 14 dias foi finalmente corrigido.**

O projeto está marcado como **PAUSED (pausado)** no sistema de gestão de projetos do José (o
**Conductor**), o que significa "não se decide o próximo grande passo de negócio" — não significa
"desligado". Há vários processos automáticos a correr todos os dias sozinhos (ver secção c).

Além do `ib_bot`, há um **robô-irmão chamado "trading"** (projeto diferente, repositório
diferente) que testou uma estratégia de opções sobre resultados trimestrais ("iron-fly
earnings-vol", estudo interno nº 0006) — essa estratégia também morreu num teste real em julho de
2026. É mencionada aqui porque o brief original pede os números desse estudo, mas **não faz parte
do `ib_bot`**.

## (b) Evolução até hoje (timeline, com datas verificadas)

Fonte: `git log main --oneline` (428 commits) + as 12 auditorias anteriores no mesmo diretório +
`psql -U servidor -d conductor` + memórias em
`/home/servidor/.claude/projects/-home-servidor/memory/`.

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repositório. |
| 2026-01 a 2026-04 | Construção inicial: motor de backtest, catálogo de 56 estratégias, execução IB, frontend. |
| 2026-05 | Auditoria de investibilidade v1→v4 (Deflated Sharpe Ratio): v1 descobre que o "alfa" de várias estratégias era beta de mercado disfarçado; v3 mede decaimento de sinal desde que ETFs públicos como a NANC (que copia publicamente o mesmo truque de "seguir políticos") começaram a competir em 2023 (Congress Buys Sharpe 1,03→0,21); v4 (AUTORITATIVA) aplica Deflated Sharpe e reprova as 56. Recomendação: licenciar o motor de dados, não vender "alfa"; ação nº1 = arquivar PIT. |
| 2026-07-12/13 | Decisão de negócio do José: **dormência seletiva** (plano Conductor `e36e04ec`). Arranca o arquivo diário PIT. Estudo 0006 (iron-fly earnings-vol, no repo-irmão `trading`) autopsiado: a suposta PF intraday 1,42–1,78 era artefacto de 559/3264 eventos com `max_risk≈0`; recalculada honestamente dá 0,109 — pior que o EOD (0,06–0,37 todos os anos). |
| 2026-07-16 | **Estudo 0006: veredito final pré-registado KILL**, com forward-test de 36 eventos reais confirmando (PF@mid 0,776, PF@touch 0,256 — o custo de execução, por si só, transforma "quase neutro" em "perdedor claro"). |
| 2026-08-05 a 08-20 | Plano Conductor `04bf8af8` "Alt-data PIT archive hardening" fecha `done`. |
| 2026-08-11 | Gate calendário do arquivo PIT fecha (30 dias). One-pager de licenciamento B2B fica pronto; decisão de José sobre avançar com outreach comercial **ainda pendente hoje**. |
| 2026-08-14 a 09-27 | A tarefa diária `paper_rebalance_daily_task` falha silenciosamente todos os dias, para as duas contas, com `tuple index out of range` (45 dias corridos). |
| 2026-08-27 20:54 | `ibgateway.service`/`xvfb-ibgw.service` parados — decisão deliberada de dormência (o jornal do systemd já não cobre esta data, por rotação; nenhuma auditoria desde então, incluindo esta, viu o gateway ligado). |
| 2026-08-30 – 09-15 | Duas rondas de hardening de segurança do caminho de execução real (planos Conductor `8e1fa5aa` e `4c48535c`) fecham `done`. Zero ordens reais em qualquer momento. |
| 2026-09-28 | Bug dos 45 dias corrigido: a tarefa Celery chamava diretamente uma rota FastAPI protegida por rate-limiter sem passar o objeto `Request` esperado. **Mesmo dia**: conta 1 executa o 1º rebalanceamento real em 126 medições (32 ordens, caixa $100.000→$91.957,47); conta 2 passa a falhar com um erro NOVO, `HTTPException 400: insufficient cash`. |
| 2026-10-05 a 10-12 | 11ª e 12ª auditorias confirmam a conta 2 sem corrigir (7 e depois 14 dias seguidos de `insufficient cash`); imagens Docker reclamáveis quase duplicam (31,5→61,1 GB, depois caem para 48,7GB sem ação atribuível). |
| **2026-10-13/14** | Robustez da QA/backup de alt-data (buracos de feriados SEC, re-pin de imagem). **Bug `insufficient cash` corrigido** (commits `3ea8fb0`/`57e5033`: valida e escala as ordens de compra à caixa disponível antes de as enviar). **Mesmo dia**: criado um timer semanal (`ib-docker-prune.timer`) para limpar imagens Docker antigas (achado #3/#8 das auditorias anteriores). |
| 2026-10-14 15:00 UTC | Primeiro rebalanceamento da conta 2 desde 28-set: **SUCCESS, 49 ordens** (com aviso "scaled buy orders by 0.8376" — a validação funcionou como esperado, escalando as ordens para caberem na caixa disponível). |
| 2026-10-15 a 10-18 | Conta 2 corretamente "not due" todos os dias (frequência semanal, último rebalance 14-out); conta 1 continua "not due" (frequência trimestral, último rebalance 28-set). `ib-docker-prune.service` corre de novo a 18-out: **"Total reclaimed space: 0B"**, outra vez. |
| **2026-10-19 (hoje, 13ª auditoria)** | Confirma o fix de 10-14 em produção (sem recorrência do erro); confirma que a limpeza Docker não funciona (imagens reclamáveis sobem de 48,72GB para 65,13GB numa semana, apesar do timer novo); decisão PIT chega a 99 dias pendente; ainda sem plano Conductor novo desde 15-set (34 dias). |

## (c) Estado concreto HOJE (verificado nesta sessão)

### Repositórios e worktrees
```
git worktree list
/home/servidor/Desktop/cursor-projects/ib_bot     911ffdf [main]
/home/servidor/Desktop/cursor-projects/ib_bot-v2  25f7a6a [frontend-v2]
/home/servidor/ib-altdata-guard-20260924          486b6e3 [fix/altdata-backup-main-20260924]
/home/servidor/ib-backtest-receipt-20261005       1668947 [fix/weekly-backtest-receipt-cache-20261005]
/home/servidor/ib-sec-holiday-index-20261013      14fc73b [fix/sec-holiday-index-20261013]
```
`git status --porcelain` no checkout principal: **vazio** (limpo). `ib_bot-v2` é um worktree do
mesmo repositório, não um projeto separado (`.conductor/context.md` tem uma alteração não
comitada, sem impacto — não é tocado por este audit). `ib_bot-altdata-wt` (citado no brief)
**continua a não existir**.

### Serviços systemd (comando: `systemctl cat`/`list-units`/`list-timers` corridos nesta sessão)
| Unit | Estado | Nota |
|---|---|---|
| `ibgateway.service` | `inactive (dead)`, `disabled` | Sem listener nas portas 4001-4004; mantido parado desde a decisão deliberada de 2026-08-27 (ver nota na timeline). |
| `xvfb-ibgw.service` | `inactive (dead)`, `disabled` | Idem (display virtual que o gateway usaria). |
| `ib-altdata-backup.timer`/`.service` | timer `active (waiting)`; última corrida hoje 04:33 WEST **SUCCESS** | Backup offsite diário das fotografias PIT. |
| `ib-altdata-qa.timer`/`.service` | `active (waiting)`; última corrida hoje 08:00 WEST **SUCCESS** | Recibo diário publicado, hash-chain OK, 99 dias cobertos. |
| `ib-backtests.timer`/`.service` | `active (waiting)`; próxima corrida domingo 25-out | Corre com `PRICE_SOURCE=yfinance` forçado (drop-in `10-price-source.conf`), nunca toca IB ao vivo. |
| `ib-docker-prune.timer`/`.service` | `active (waiting)`; última corrida 18-out **SUCCESS mas "Total reclaimed space: 0B"** | **Não está a funcionar** — ver achado MÉDIO #2. |
| `theta-terminal.service` + 5 timers (`theta-learned`, `paper-ironfly`, `historical-backfill`, `execution-metrics`, `cost-recalibration`) | Todos `active` | **Re-confirmado com `systemctl cat` nesta sessão: NENHUM pertence ao ib_bot.** 4 apontam para `/home/servidor/Desktop/cursor-projects/polytrader-bot-master` (Polymarket — mercado de apostas/previsões). `paper-ironfly` aponta para `/home/servidor/Desktop/cursor-projects/trading` (o bot-irmão de opções). |
| `lifeos-ib-refresh.timer`/`.service` | `active (waiting)` | Projeto `lifeos`, não `ib_bot` — lê o saldo real da **conta pessoal** do José via MCP IBKR. Hoje 03:15 WEST: `net_liq=41.724,54` (9→7 posições desde a última auditoria), a subir de ~30.277 há 1 semana. Mencionado só para completude; não é do bot (`ib_orders=0` continua exatamente igual). |

### Stack Docker (`docker ps -a`, `docker system df`, `docker stats --no-stream`)
```
ibeam-primary      Up 3 dias   127.0.0.1:5055->5000/tcp   (IB Gateway via IBeam, AUTENTICADO)
ib_bot-worker-1    Up 3 dias
ib_bot-beat-1      Up 3 dias
ib_bot-api-1       Up 3 dias   0.0.0.0:8001->8000/tcp
ib_bot-db-1        Up 3 dias   5432/tcp (não exposta ao host)
ib_bot-redis-1     Up 3 dias   6379/tcp
ib_bot-web-1       Up 3 dias   3000/tcp
ib_bot-nginx-1     Up 3 dias   0.0.0.0:8090->80/tcp
```
**Achado novo desta sessão:** `ibeam-primary` é um **IB Gateway alternativo, via Docker/IBeam**,
distinto do `ibgateway.service` (via IBC) que está parado. Os logs confirmam
`"Gateway running and authenticated, session id: 02eb1bf3..."` a cada minuto, sessão ativa há 3+
dias — ou seja, **há sim uma ligação ativa à conta real da IB**, mas usada apenas para pedir
preços de mercado (`PRICE_SOURCE=ib` no ambiente do container `api`), nunca para ordens: `.env`
confirma `ENABLE_LIVE_TRADING=false`/`LIVE_DRY_RUN=true`, e a tarefa horária
`live_rebalance_scheduled_task` auto-salta todos os dias com a mensagem exata
`"live_rebalance_scheduled: LIVE_AUTO_REBALANCE off, skipping"` (confirmado nos logs do worker,
10-17 a 10-18, todas as horas). Consumo de recursos de toda a stack: **<0,5% CPU, <400MB RAM no
total** (`docker stats --no-stream`) — insignificante.

`docker system df` hoje:
```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          22        21        65.13GB   56.37GB (86%)
Build Cache     22        0         26.85GB   0B
```
**Piorou desde 10-12** (imagens reclamáveis: 48,72→65,13 GB) apesar do novo timer de limpeza — ver
achado MÉDIO #2 com a causa raiz identificada. Disco raiz: `df -h /` → 1,8 TB total, **89% usado,
204 GB livres** (era 87%/240GB há 1 semana — a piorar). `docker images` mostra 5 imagens "vivas"
etiquetadas (`api` 8,47GB, `beat` 10GB, `worker:latest` 10GB, `worker:altdata-qa-pin-3ea8fb0`
10GB, `web` 1,3GB ≈ 40GB) — o resto dos 65,13GB são camadas intermédias "dangling" que o Docker
não consegue remover porque ainda estão referenciadas pelos containers antigos em execução.

### Tarefas internas do bot (celery beat/worker — `backend/app/worker/celery_app.py`)
8 tarefas agendadas: `refresh_plot_data_nightly` (diário 02:00 UTC), `refresh_validation_weekly`
(domingo 03:00), `shadow_preview_daily` (06:00), `paper_rebalance_daily` (15:00),
`live_rebalance_hourly` (hora em hora, 14h-21h UTC, **auto-skip confirmado**),
`paper_snapshot_daily` (21:30), `altdata_snapshot_daily` (06:00),
`reconcile_stuck_executions`/`reconcile_stuck_runs` (cada 5/10 min).

- **`paper_rebalance_daily_task` (15:00 UTC diário) — RESOLVIDO esta semana:**
  ```
  docker logs ib_bot-worker-1 2>&1 | grep -i paper_rebalance | tail -20
  ```
  → `2026-10-14 15:00:40: WARNING: paper_rebalance account=2: total buy notional 62923.62 exceeds
  available cash 52756.66, scaled buy orders by 0.8376` seguido de
  `paper_rebalance_daily: account=2 ... freq=weekly orders=49` e `succeeded`. Dias seguintes
  (15, 16, 17, 18-out): `account=2 ... not due (freq=weekly, last=2026-10-14 15:00:40), skipping` —
  comportamento correto e esperado (só rebalanceia 1x/semana).
- **`altdata_snapshot_daily_task`** — saudável todos os dias; log de hoje mostra
  `'mode': 'research_only_non_trading', 'ib_requests': 0, 'orders_placed': 0'` — confirma por
  desenho que esta tarefa nunca manda ordens nem gasta chamadas IB.

### Base de dados (Postgres dentro de `ib_bot-db-1`, user `ibbot_app`, db `ibbot`, 88MB)
```
docker exec ib_bot-db-1 psql -U ibbot_app -d ibbot -c "SELECT count(*) FROM ib_orders;"   -- 0
docker exec ib_bot-db-1 psql -U ibbot_app -d ibbot -c "SELECT count(*) FROM ib_trades;"   -- 0
docker exec ib_bot-db-1 psql -U ibbot_app -d ibbot -c "SELECT count(*) FROM live_execution_requests;" -- 0
```
- **Zero ordens reais desde sempre** (`ib_orders`, `ib_trades`, `live_execution_requests` todos
  0) — re-confirmado pela 13ª vez.
- `altdata_snapshots` = **1086 linhas**, **99 dias** distintos (13-jul a hoje), última captura
  `2026-10-19 06:00:40` — cresceu 77 linhas e 7 dias desde 10-12, ritmo de ~11/dia mantido.
- `live_rebalance_audit` = 25 linhas, todas `action IN ('preview','dry_run')`, nunca `execute` —
  confirma que o caminho de execução real nunca foi disparado de verdade, só testado em modo
  seguro (6 das 25 são `preview`/`ERROR`, a investigar se sobrar tempo, mas sem risco monetário
  porque nenhuma chega a `execute`).
- `paper_cash`: conta 1 "A — Hedge Fund Mirror" (caixa $91.957,47, parada desde 28-set); conta 2
  "V1 Core" (caixa $1.290,66 — quase 100% investida).
- `paper_rebalance_logs`: 266 linhas totais, última `2026-10-14 15:00:40 SUCCESS n_orders=49`
  (confirma o fecho do bug, nenhuma linha `ERROR` depois dessa data).
- **`paper_snapshots`** (query completa, 2026-05-26 a 2026-10-18, 146 dias únicos por conta — ver
  `metrics.json` desta auditoria para a série completa e metodologia):

  | | Conta 1 (Hedge Fund Mirror) | Conta 2 (V1 Core, produção) |
  |---|---|---|
  | Retorno total (26-mai→18-out) | **+0,04%** | **−0,92%** |
  | Máxima queda (drawdown) | −0,21% / −$211 | −5,43% / −$10.133 |
  | Sharpe anualizado | 0,23 | **−0,14** |
  | Sortino anualizado | 0,35 | **−0,19** |
  | Dias com ganho (dos dias com variação) | 6,2% | 37,9% |
  | VaR 95% diário | −0,04% | −1,08% |

  Isto é dinheiro **FICTÍCIO** (paper), não real (`ENABLE_LIVE_TRADING=false` confirmado). A
  conta 1 quase não varia (está em HOLD desde o único rebalance de 28-set); a conta 2 é a única com
  atividade real de rebalanceamento (219 trades no total entre as duas, 187 na conta 2) e está
  **em território negativo com Sharpe/Sortino negativos** — consistente com o veredito de maio de
  2026 de que nenhuma das 56 estratégias tem edge real.

### Estudo 0006 (earnings-vol iron-fly) — repo-irmão `trading`, não `ib_bot`
Verificado hoje em `/home/servidor/Desktop/cursor-projects/trading/studies/0006-earnings-vol/`:
**veredito final `forward_30events.md` = KILL, 2026-07-16**, com forward-test real de 36 eventos
(PF@mid 0,776, PF@touch 0,256) — inalterado e fechado. O ledger de paper-ironfly do repo `trading`
(`data/options_cache/paper_ironfly_ledger.parquet`) continua a crescer todos os dias (829 eventos
hoje, era 36 no forward-test original) — é monitorização de graça pós-KILL, não uma estratégia
viva. `phase-status.json` nesse repo **continua desatualizado** (campo `status` ainda diz
`"reopened_wide_wing_ironfly_survivor"`, de 25-mai, antes do veredito final de 16-jul) — fora do
`ib_bot`, registado só porque o brief pede os números deste estudo.

### Conta real na Interactive Brokers (via timer `lifeos-ib-refresh`, conta pessoal do José)
```
journalctl -u lifeos-ib-refresh.service --since "2026-10-13" | grep pushed
```
→ progressão: 13-out `30.276,98` (9 posições) → ... → 18-out `41.695,87` (7 posições) → 19-out
(hoje, 03:15) `41.724,54` (7 posições). **Esta é a conta pessoal do José**, gerida manualmente por
ele fora deste bot — não é do `ib_bot` (`ib_orders=0` continua exatamente igual). Registado só
para manter o estado da conta atualizado; não é um achado do bot. (O conector MCP `Interactive
Brokers (IBKR)` está disponível nesta sessão, mas usar o registo já verificado do timer evita
qualquer leitura adicional não essencial contra a conta real.)

### Planos do Conductor (`psql -U servidor -d conductor`)
| Plano | Slug | Status | Nota |
|---|---|---|---|
| `3702771c` — ib_bot → Alt-Data Product | `ib_bot` | `superseded` | Sem alterações. |
| `e36e04ec` — pós-triagem 2026-07-12 | `ib_bot` | `superseded` | Sem alterações. |
| `04bf8af8` — Alt-data PIT archive hardening | `ib_bot` | `done` | Sem alterações. |
| `4c48535c` — IB bot money-path hardening | `ib_bot` | `done` (fechado 2026-09-15) | Sem alterações. |

**Nenhum plano novo, aberto ou `executing`, para o slug `ib_bot` desde 2026-09-15 (34 dias)** —
confirmado de novo. O fix do `insufficient cash` (10-14) aconteceu **sem nenhum plano Conductor a
dar-lhe dono** — alguém (provavelmente outro agente ou o próprio José) corrigiu-o fora do sistema
de gestão de trabalho, o que é bom para o resultado mas mau para a rastreabilidade.

## (d) Findings, ordenados por gravidade

### CRÍTICO
Nenhum achado crítico nesta auditoria — o único crítico das 12 auditorias anteriores
(`insufficient cash`, 14 dias) foi corrigido em 2026-10-14 e está confirmado estável em produção
(ver secção c e achado INFORMATIVO abaixo).

### ALTO

**#1 — Decisão de negócio sobre o arquivo PIT continua pendente, agora há 99 dias (desde
2026-08-11).** `altdata_snapshots` cresceu para 1086 linhas / 99 dias, tudo engenharia e
armazenamento sem decisão de uso (vender/arquivar/continuar). One-pager de licenciamento B2B já
pronto (`docs/altdata_b2b_one_pager_draft.md`) — falta só a palavra do José. Ver plano futuro de
decisão estratégica.

**#2 — Nenhuma das 56 estratégias de investimento tem edge robusto (inalterado desde maio); a
nova métrica da conta 2 (Sharpe/Sortino negativos no período paper) reforça a conclusão.** O único
candidato fora do catálogo (estudo 0006) está morto desde julho. Não há nenhum candidato vivo a
investigar sem gerar novas ideias do zero.

### MÉDIO

**#3 — A limpeza automática de Docker criada na semana passada (achado da 12ª auditoria) não
funciona: reporta "0B reclaimed" nas duas corridas até hoje, e o espaço reclamável VOLTOU A SUBIR
(48,72→65,13 GB numa semana).** Causa raiz identificada nesta sessão: `docker_prune_weekly.sh`
só remove imagens `dangling` (sem container a usá-las); como os containers `ib_bot-worker-1`/
`ib_bot-beat-1`/`ib_bot-api-1` nunca são reiniciados depois de uma nova imagem ser construída
(cada fix de código gera uma imagem nova com a mesma tag `latest`), as imagens antigas continuam
"agarradas" aos containers em execução e nunca ficam verdadeiramente `dangling` de forma
removível. Ver plano de fixes, passo 1, para a correção.

**#4 — Projeto sem dono formal no Conductor há 34 dias (desde 2026-09-15).** O bug crítico
`insufficient cash` ficou 16 dias sem correção (28-set a 14-out) sem nenhum plano a dar-lhe dono
formal — foi corrigido por iniciativa externa ao sistema de gestão de trabalho. Isto é um padrão
de risco: o próximo problema pode não ter a mesma sorte.

### BAIXO

**#5 — O pedido da 12ª auditoria para registar em memória os nomes de ficheiro consolidados
nunca foi executado.** `grep` confirma que a linha pedida não existe em `MEMORY-trading.md`.
Baixo esforço, ainda pendente.

**#6 — `live_rebalance_audit` tem 6 linhas `preview`/`ERROR` (de 25 totais) nunca investigadas.**
Sem risco monetário (nenhuma chega a `execute`), mas um erro recorrente em modo preview pode
escondiar um bug que só aparece se `ENABLE_LIVE_TRADING` for alguma vez ligado — vale investigar
antes dessa decisão, não depois.

**#7 — `phase-status.json` do estudo 0006 (repo `trading`) continua desatualizado** (campo
`status` de 25-mai, antes do veredito final KILL de 16-jul). Fora do repo `ib_bot`, registado por
completude.

### INFORMATIVO / POSITIVO

**#A — O bug crítico de 14+ dias (`insufficient cash`, conta paper 2) foi corrigido em
2026-10-14 e está confirmado estável em produção** — 1 rebalanceamento SUCCESS (49 ordens,
escalado corretamente a 83,76% do pedido original para caber na caixa disponível), seguido de 4
dias consecutivos de "not due" corretos, sem recorrência do erro.

**#B — Todas as 4+ camadas de bloqueio a ordens reais continuam intactas e re-confirmadas**:
`ibgateway.service` parado, `ENABLE_LIVE_TRADING=false` em `.env`, `ib_orders=0`/`ib_trades=0`,
`live_rebalance_scheduled_task` auto-skip confirmado em produção todas as horas, guarda de
pré-voo de ordens e gate atómico de colocação (planos `4c48535c`, `done`).

**#C — Todos os jobs automáticos (`ib-altdata-backup`, `ib-altdata-qa`, `ib-backtests`) correram
com sucesso nos 7 dias desde a última auditoria, sem falhas novas.**

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Corrigir a limpeza Docker ineficaz (achado MÉDIO #3)** — é um problema puramente técnico,
   de baixo risco, com causa raiz já identificada; sem isto o disco raiz (89% usado hoje) vai
   continuar a apertar. Ver plano de fixes, passo 1.
2. **Dar dono formal no Conductor a este projeto (achado MÉDIO #4)** — mesmo pausado, um plano
   leve de "vigilância" evita que o próximo bug fique 16 dias sem dono como aconteceu com o
   `insufficient cash`. Ver plano de fixes, passo 2.
3. **Resolver a decisão de negócio do arquivo PIT (#1)** — a única decisão deste projeto que
   depende só do José, não de engenharia; mais de 3 meses pendente. Ver plano futuro de decisão
   estratégica.
4. **Decidir formalmente o futuro do motor de investimento (#2)** — reativar com investigação de
   novas ideias, manter dormente indefinidamente, ou encerrar ordenadamente. Ver plano futuro.
5. **Registar em memória os caminhos consolidados (#5)** — cosmético, baixo esforço. Ver plano de
   fixes, passo 3.
6. **Investigar as 6 linhas `preview`/`ERROR` em `live_rebalance_audit` (#6)** — baixa prioridade
   mas vale fazer antes de qualquer decisão futura de reativar execução real.

## (f) Riscos se nada for feito

- **Nenhum risco de perda de dinheiro real hoje.** Trading ao vivo está travado em 4+ camadas
  (`ibgateway` desligado, `ENABLE_LIVE_TRADING=false`, `live_rebalance_scheduled_task` auto-skip
  confirmado em produção, guarda de pré-voo, gate atómico). `ib_orders=0`/`ib_trades=0` confirmado
  de novo.
- **Risco de disco a continuar a apertar.** 89% usado hoje (204GB livres), a subir de 87% há 1
  semana; a limpeza automática criada para resolver isto não funciona (0B reclaimados nas duas
  corridas) — sem correção, o padrão de crescimento de imagens Docker (48→65GB numa semana) pode
  continuar até o disco ficar criticamente apertado.
- **Risco de decisão por omissão sobre o arquivo PIT** — quanto mais tempo sem decisão (99 dias e
  a contar), mais dados acumulados sem destino claro, mais difícil fica justificar continuar a
  gastar engenharia/armazenamento nisto sem um objetivo de negócio.
- **Risco de problemas futuros ficarem sem dono** — o `insufficient cash` ficou 16 dias sem
  correção porque não havia nenhum plano Conductor a vigiar este projeto pausado; o próximo bug
  pode não ser corrigido por sorte da próxima vez.
- **Risco de fadiga de auditoria** — esta é a 13ª auditoria semanal consecutiva do mesmo projeto
  pausado. A boa notícia desta semana (bug corrigido) mostra que o processo de auditoria tem
  valor real — mas sem um plano Conductor formal, continuará a ser a única rede de segurança.

## (g) Glossário

- **API (Application Programming Interface)** — a "porta" por onde dois programas trocam
  informação (pedidos e respostas), sem um humano no meio.
- **MCP (Model Context Protocol)** — ligação que permite a um assistente de IA falar diretamente
  com um serviço externo; aqui usada para ler saldo/posições reais da conta pessoal do José na IB.
- **Backtest** — simular "se eu tivesse seguido esta estratégia no passado, ganhava ou perdia
  dinheiro?", sem risco real, usando preços históricos já conhecidos.
- **Paper trading** — fingir que compras e vendes ações com dinheiro que não existe, para testar
  o sistema sem arriscar dinheiro real.
- **PIT (point-in-time)** — guardar uma "fotografia" dos dados exatamente como estavam num certo
  dia, para nunca se poder fazer batota usando informação que só existiu depois.
- **Alfa vs Beta** — alfa é ganho por competência real (bater o mercado); beta é ganho só porque
  o mercado em geral subiu (qualquer pessoa ganharia igual, sem skill nenhum).
- **Deflated Sharpe Ratio** — teste estatístico que pune ter experimentado muitas estratégias
  diferentes antes de escolher a "melhor" — corrige o facto de que, testando 56 ideias ao calhas,
  é natural que uma ou duas pareçam boas só por sorte.
- **Profit Factor (PF)** — soma de todos os ganhos a dividir pela soma de todas as perdas (em
  valor absoluto); PF>1 significa "ganhou mais do que perdeu no total", PF<1 significa o contrário.
- **13F** — relatório trimestral obrigatório nos EUA em que grandes fundos de investimento (como
  o de Warren Buffett) revelam o que compraram/venderam.
- **STOCK Act** — lei dos EUA que obriga políticos a declarar publicamente as suas transações de
  ações, dentro de um prazo curto.
- **ETF (Exchange-Traded Fund)** — um "fundo" que se compra e vende na bolsa como se fosse uma
  ação normal, mas que por dentro é uma cesta de várias ações (ex.: a NANC segue as compras de
  políticos dos EUA).
- **Celery beat/worker** — um "relógio" (beat) que dispara tarefas periódicas dentro da própria
  aplicação, e um "trabalhador" (worker) que as executa de facto.
- **systemd timer / service** — o despertador do próprio computador Linux (timer) que dispara uma
  tarefa a uma hora marcada (o service), fora de qualquer aplicação.
- **Docker / container / imagem** — uma "caixa" isolada onde um programa corre com tudo o que
  precisa; a "imagem" é o molde de onde a caixa é criada, e pode ficar guardada em disco mesmo
  depois da caixa parar. Uma imagem "dangling" é uma imagem antiga sem etiqueta (tag), geralmente
  substituída por uma mais recente com o mesmo nome.
- **Rate limiter (SlowAPI)** — um guarda que limita quantos pedidos por minuto uma rota web pode
  receber; foi a causa escondida do bug de 45 dias de setembro.
- **Conductor / Domain Manager / plano / fase** — o sistema que o José usa para gerir trabalho
  longo de agentes de IA; um "gestor de domínio" pode ter autoridade sobre vários repositórios.
- **runjob** — a ferramenta do José para correr trabalho pesado (CPU/RAM/disco) dentro de limites
  seguros, para não travar a máquina inteira.
- **worktree (do git)** — uma segunda cópia de trabalho do mesmo repositório, útil para um agente
  trabalhar numa alteração sem interferir com o código principal.
- **VaR (Value at Risk)** — estimativa de "pior perda esperada num dia mau", olhando para o
  histórico de retornos e descartando apenas os 5% piores dias.
- **Sharpe / Sortino Ratio** — medidas de "ganho por unidade de risco" (Sharpe usa toda a
  variação; Sortino só pune as quedas, ignorando a variação positiva).
- **IBeam** — um programa de código aberto que mantém a sessão de login na IB ativa dentro de um
  container Docker, sem precisar de um ecrã gráfico como o `ibgateway.service` tradicional usa.
