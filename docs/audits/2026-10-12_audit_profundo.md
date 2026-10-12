# Audit Profundo — IB Bot (2026-10-12, ART / manhã em Portugal WEST)

> Sessão de auditoria: `/home/servidor/agent-workspaces/mega-audit-2026-10-12`.
> Todos os comandos abaixo foram corridos NESTA sessão (ground truth re-verificado, não copiado
> de memória nem de auditorias anteriores). Esta é a **12ª auditoria profunda** deste projeto
> (depois de 2026-07-12, 07-20, 08-10, 08-17, 08-24, 08-31, 09-07, 09-14, 09-21, 09-28 e 10-05 —
> confirmado com `ls docs/audits/*.md` → 12 ficheiros incluindo este). Mesmo repositório
> (`/home/servidor/Desktop/cursor-projects/ib_bot`, HEAD de hoje `def1896`, 353 commits em `main`).

> **Nota sobre o brief:** o pedido descreve 3 roots (`ib_bot`, `ib_bot-v2`, `ib_bot-altdata-wt`) e
> memórias `project_ib_bot.md`/`project_ib_bot_audit.md`/`project_pead.md`/`project_earnings_vol.md`.
> Re-verificado agora (12ª vez): `ib_bot-altdata-wt` **continua a não existir** no disco;
> `ib_bot-v2` é um **git worktree** do mesmo repositório (não um projeto separado) apontando para
> a branch `frontend-v2` — confirmado com `git worktree list`. Os nomes de memória do brief foram
> consolidados há meses em `MEMORY-trading.md` + `reference_ib_bot_*.md` (ver achado BAIXO #9). O
> conteúdo (dormência seletiva, NANC ETF, estudo 0006, PEAD rejeitado) está correto — só os nomes
> de ficheiro mudaram. A lista de timers do brief (`historical-backfill`, `execution-metrics`,
> `cost-recalibration`) **NÃO pertence ao ib_bot** — ver secção (c), re-confirmado com
> `systemctl cat` nesta sessão.

> **Esta auditoria foca-se no que mudou desde 2026-10-05** (a 11ª auditoria, muito detalhada, em
> `docs/audits/2026-10-05_audit_profundo.md`) em vez de repetir tudo do zero. Resumo da semana:
> **nada de código mudou** — os únicos 14 commits desde então são os jobs diários automáticos de
> alt-data (backup + QA). Nenhum plano Conductor novo. O bug crítico já identificado há 2 semanas
> (conta paper 2, `insufficient cash`) continua **sem correção**, agora com 14 dias seguidos em vez
> de 7.

## (a) O que é este projeto (para um miúdo de 12 anos)

O **IB Bot** é um robô de computador que devia comprar e vender ações sozinho, usando a conta de
trading do José na **Interactive Brokers (IB — a corretora, a empresa que executa ordens de
compra/venda na bolsa por ti)**. A ideia era copiar o que "gente esperta" faz — políticos dos EUA
quando compram ações, fundos famosos (como o de Warren Buffett) quando publicam os seus relatórios
trimestrais (um **13F**, documento que esses fundos são obrigados a publicar), gestores que apostam
contra empresas (Michael Burry) — e ver se copiar essas jogadas dá dinheiro.

O robô testou **56 ideias diferentes** ("estratégias") em dados históricos com um motor de
**backtest** (simular "se eu tivesse seguido esta regra no passado, ganhava ou perdia?"). Um estudo
interno rigoroso de maio de 2026 (o **Deflated Sharpe Ratio** — um teste estatístico que pune ter
experimentado muitas ideias, porque quanto mais tentas, maior a hipótese de uma parecer boa só por
sorte) concluiu que **nenhuma das 56** tem ganho real acima do que se esperaria por sorte. O projeto
foi **pausado** nessa altura ao nível de decisão de negócio — e continua pausado hoje, 12ª semana
a confirmar isto.

Tem quatro peças vivas hoje (inalteradas desde a auditoria anterior):
1. **Motor de backtest** — testa as 56 ideias no passado, de graça, sem risco. Corre sozinho todas
   as semanas (domingo de madrugada). Última corrida: 2026-10-11, 56/56 sucesso.
2. **Motor de execução real** — a peça que manda ordens verdadeiras para a IB. Está **desligada**
   desde 2026-08-27 por decisão do José ("dormência seletiva"), e continua desligada hoje (46 dias).
3. **Arquivo "ponto-no-tempo" (PIT — point-in-time)** — desde 13 de julho de 2026, o robô tira uma
   "fotografia" todos os dias de 11 fontes de dados públicas e guarda-a para sempre, mesmo que a
   fonte original mude depois. Hoje tem 92 dias/1009 linhas (era 85 dias/932 linhas há uma semana).
4. **"Paper trading" (fingir que compra/vende ações com dinheiro que não existe, para testar o
   sistema sem risco)** — corre todos os dias sozinho, duas contas fictícias. Conta 1 fez o seu
   primeiro (e até agora único) rebalanceamento real em 28-set; conta 2 continua a falhar com
   "dinheiro insuficiente" todos os dias desde então, sem correção.

O projeto está marcado como **PAUSED (pausado)** no sistema de gestão de projetos do José (o
**Conductor**), o que significa "não se decide o próximo grande passo de negócio" — não significa
"desligado". Há vários processos automáticos a correr todos os dias sozinhos (ver secção c).

## (b) Evolução até hoje (timeline, com datas verificadas)

Fonte: `git log main --oneline` (353 commits) + as 11 auditorias anteriores no mesmo diretório +
`psql -U servidor -d conductor` + memórias em
`/home/servidor/.claude/projects/-home-servidor/memory/`.

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repositório. |
| 2026-01 a 2026-04 | Construção inicial: motor de backtest, catálogo de 56 estratégias, execução IB, frontend. |
| 2026-05 | Auditoria de investibilidade v1→v4 (Deflated Sharpe Ratio): v1 descobre que o "alfa" de várias estratégias era beta de mercado disfarçado; v3 mede decaimento de sinal desde que ETFs públicos como a NANC (que copia publicamente o mesmo truque de "seguir políticos") começaram a competir em 2023 (Congress Buys Sharpe 1,03→0,21); v4 (AUTORITATIVA) aplica Deflated Sharpe e reprova as 56. Recomendação: licenciar o motor de dados, não vender "alfa"; ação nº1 = arquivar PIT. |
| 2026-05-09 | **Última linha nova em `paper_trades` da conta 2 até hoje** — confirmado de novo (`max(timestamp)=2026-05-09`, inalterado há mais de 5 meses). |
| 2026-07-12/13 | Decisão de negócio do José: **dormência seletiva** (plano Conductor `e36e04ec`). Arranca o arquivo diário PIT. Estudo 0006 (iron-fly earnings-vol, no repo-irmão `trading`) autopsiado: a suposta PF intraday 1,42–1,78 era artefacto de 559/3264 eventos com `max_risk≈0`; recalculada honestamente dá 0,109 — pior que o EOD (0,06–0,37 todos os anos). |
| 2026-07-16 | **Estudo 0006: veredito final pré-registado KILL**, com forward-test de 36 eventos reais confirmando (PF@mid 0,776, PF@touch 0,256 — o custo de execução, por si só, transforma "quase neutro" em "perdedor claro"). Decisão: zero gasto, manter o timer de vigia de graça. |
| 2026-08-05 a 08-20 | Plano Conductor `04bf8af8` "Alt-data PIT archive hardening" fecha `done`. |
| 2026-08-11 | Gate calendário do arquivo PIT fecha (30 dias). One-pager de licenciamento B2B fica pronto; decisão de José sobre avançar com outreach comercial **ainda pendente hoje** (mais de 2 meses depois). |
| 2026-08-14 a 09-27 | A tarefa diária `paper_rebalance_daily_task` falha silenciosamente todos os dias, para as duas contas, com `tuple index out of range` (45 dias corridos). |
| 2026-08-27 20:54 | `ibgateway.service`/`xvfb-ibgw.service` parados (continuam parados hoje, 46 dias) — decisão deliberada de dormência. |
| 2026-08-30 – 09-15 | Duas rondas de hardening de segurança do caminho de execução real (planos Conductor `8e1fa5aa` e `4c48535c`) fecham `done`. Zero ordens reais em qualquer momento. |
| 2026-09-28 | Bug dos 45 dias corrigido (commit `1391c6f`): a tarefa Celery chamava diretamente uma rota FastAPI protegida por rate-limiter sem passar o objeto `Request` esperado — rebentava dentro do próprio SlowAPI e aparecia disfarçado de `tuple index out of range`. **Mesmo dia**: conta 1 executa o 1º rebalanceamento real em 126 medições (32 ordens, caixa $100.000→$91.957,47); conta 2 passa a falhar com um erro NOVO, `HTTPException 400: insufficient cash`. Também nesse dia: `ib_bot-v2` (2º frontend, porta 3001) é desmantelado por completo, sem registo de quem/quando. |
| 2026-10-05 (11ª auditoria) | Confirma a conta 2 ainda sem corrigir (7 dias seguidos de `insufficient cash`); imagens Docker reclamáveis quase duplicam (31,5→61,1 GB); corrige no próprio dia um recibo de backtest versionado por engano. |
| **2026-10-06 a 10-11** | **Nada de código muda.** 14 commits, todos jobs automáticos (`qa(altdata)`/`backup(altdata)`). `ib-backtests.service` corre normalmente a 11-10 (56/56). `paper_rebalance_daily_task` da conta 2 continua a falhar com `insufficient cash` **todos os 7 dias** (05 a 11-10), sem exceção. |
| **2026-10-12 (hoje)** | Este audit (12º). `insufficient cash` já leva **14 dias seguidos** (09-28 a 10-11) sem diagnóstico nem correção. |

## (c) Estado concreto HOJE (verificado nesta sessão)

### Repositórios e worktrees
```
git worktree list
/home/servidor/Desktop/cursor-projects/ib_bot     def1896 [main]
/home/servidor/Desktop/cursor-projects/ib_bot-v2  25f7a6a [frontend-v2]
/home/servidor/ib-altdata-guard-20260924          486b6e3 [fix/altdata-backup-main-20260924]
/home/servidor/ib-backtest-receipt-20261005       1668947 [fix/weekly-backtest-receipt-cache-20261005]
```
`ib_bot-v2` é um *worktree* do mesmo repositório (não um projeto separado) — a sua stack Docker e
serviço de frontend já não existem (confirmado abaixo); só o checkout de ficheiros continua no
disco. `ib_bot-altdata-wt` (citado no brief) **continua a não existir**.

`git status --porcelain` no checkout principal: **vazio** (limpo).

### Serviços systemd (comando: `systemctl status`/`systemctl cat` corridos nesta sessão)
| Unit | Estado | Nota |
|---|---|---|
| `ibgateway.service` | `inactive (dead)`, `disabled` | Parado desde 2026-08-27 20:54 WEST (46 dias), inalterado. Sem listener nas portas 4001-4004. |
| `xvfb-ibgw.service` | `inactive (dead)`, `disabled` | Idem (display virtual que o gateway usaria). |
| `ib-bot-v2-frontend.service` (porta 3001) | **já não existe como unidade** | `systemctl status` → "could not be found" (confirmado de novo). |
| `ib-bot-v2-frontend-public.service` (porta 3002) | `inactive (dead)`, `disabled` | Nunca ligada nesta janela. |
| `ib-altdata-backup.timer`/`.service` | timer `active (waiting)`; serviço `inactive (dead)` última corrida **SUCCESS** | Correu hoje 04:33:52 WEST, `code=exited, status=0/SUCCESS`. O resíduo "failed" visto na auditoria anterior (10-05) recuperou-se sozinho como previsto, sem intervenção. |
| `ib-altdata-qa.timer`/`.service` | `active (waiting)` / última corrida (hoje 08:00) **SUCCESS** | Recibo diário publicado, hash-chain OK, 92 dias cobertos. |
| `ib-backtests.timer`/`.service` | `active (waiting)` / última corrida (2026-10-11 05:16-05:44) **SUCCESS** | 56/56 estratégias, dentro de `runjob --mem 4G --cpu 4` (contido corretamente, ver `journalctl -u ib-backtests.service`). |
| `theta-terminal.service` + 5 timers (`theta-learned`, `paper-ironfly`, `historical-backfill`, `execution-metrics`, `cost-recalibration`) | Todos `active` | **Re-confirmado com `systemctl cat` nesta sessão: NENHUM pertence ao ib_bot.** 4 apontam para `/home/servidor/Desktop/cursor-projects/polytrader-bot-master` (as suas próprias descrições dizem literalmente "Polymarket" — um mercado de apostas/previsões, nada a ver com a bolsa). `paper-ironfly` aponta para `/home/servidor/Desktop/cursor-projects/trading` (o bot-irmão de opções, dono do estudo 0006). O nome "theta" aqui refere-se a modelos de decaimento de probabilidade do Polymarket, não a opções financeiras do ib_bot — coincidência de nome que confunde à primeira vista. **Isto corrige uma suposição do brief original desta própria auditoria**, que listava estes timers como "a confirmar se pertencem ao ib_bot" — não pertencem, confirmado pela 12ª vez consecutiva. |
| `lifeos-ib-refresh.timer`/`.service` | `active (waiting)` | Do projeto `lifeos`, não do `ib_bot` — lê o saldo real da **conta pessoal** do José via MCP IBKR (não é a conta do bot). Hoje 03:15:40 WEST: `net_liq=30.276,98`, 9 posições. |

### Stack Docker (`docker ps -a --filter name=ib_bot`, `docker system df`)
```
ib_bot-worker-1   Up 13 dias
ib_bot-api-1      Up 13 dias   0.0.0.0:8001->8000/tcp
ib_bot-beat-1     Up 13 dias
ib_bot-db-1       Up 2 meses   5432/tcp (não exposta ao host)
ib_bot-redis-1    Up 2 meses   6379/tcp
ib_bot-web-1      Up 2 meses   3000/tcp
ib_bot-nginx-1    Up 2 meses   0.0.0.0:8090->80/tcp
```
`docker system df`:
```
Images          20    20    48.72GB   48.72GB (100%)
Build Cache     17    0     23.6GB    0B
```
**Melhorou desde 10-05** (imagens: 61,09→48,72 GB; build cache: 35,97→23,6 GB) — mas **sem nenhum
commit ou registo de memória** a explicar quem correu `docker image prune`/`builder prune`, ou se
foi uma limpeza automática do próprio Docker. Não é possível atribuir esta melhoria a uma ação
específica — regista-se como observação, não como ação concluída de forma auditável (ver achado
BAIXO #11). Disco raiz: `df -h /` → 1,8 TB total, **87% usado, 240 GB livres** (era 89%/204 GB há
uma semana — também melhorou). `docker images | grep ib_bot` mostra apenas 4 imagens "vivas"
(`worker`/`beat`/`api` a 8,47 GB cada, `web` a 1,3 GB = ~26,7 GB) — o resto dos 48,72 GB são
camadas intermédias/imagens antigas sem tag.

### Tarefas internas do bot (celery beat/worker)
- `altdata_snapshot_daily_task` — saudável todos os dias.
- **`paper_rebalance_daily_task` (15:00 WEST diário) — CRÍTICO, inalterado desde 09-28:**
  - **Conta 1** (`portfolio=7095ae3e...`): frequência `quarterly` — próxima execução só dentro de
    meses; `not due` todos os dias desde 09-28 é o comportamento **correto e esperado**.
  - **Conta 2** (`portfolio=d2e87bea...`): `ERROR: HTTPException 400: insufficient cash` **todos
    os dias, sem exceção, de 09-28 a 10-11 (14 dias seguidos)**. Confirmado na BD:
    ```
    docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
      "SELECT account_id, status, n_orders, timestamp, details->>'error' FROM paper_rebalance_logs
       WHERE timestamp >= '2026-10-04' ORDER BY timestamp DESC LIMIT 20;"
    ```
    devolve 8 linhas `account_id=2|ERROR|0|<data>|HTTPException: 400: insufficient cash` para
    04 a 11-10 (mais as 7 já vistas na auditoria anterior, 05 a 11-10 sobrepõe-se — total
    confirmado: nenhuma mudança em nenhum dia). Nenhum ficheiro relevante
    (`backend/app/api/routes/paper.py`) foi tocado desde o commit de 09-28.

### Base de dados (Postgres dentro de `ib_bot-db-1`)
- `ib_orders` = **0**, `ib_trades` = **0**, `live_execution_requests` = **0** — zero ordens reais
  desde sempre, inalterado.
- `altdata_snapshots` = **1009 linhas**, **92 dias** distintos (13-jul a hoje), última captura
  `2026-10-12 06:00:41` — cresceu 77 linhas (932→1009) e 7 dias (85→92) desde 10-05, ritmo de
  ~11/dia mantido, consistente.
  ```
  docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
    "SELECT count(*), count(distinct captured_at::date), max(captured_at) FROM altdata_snapshots;"
  ```
- `paper_snapshots` (query completa, 2026-05-26 a 2026-10-11, 139 dias únicos por conta):
  - **Conta 1**: caixa fixa em **$91.957,47** desde 28-set (sem novo rebalance, esperado); equity a
    oscilar $99.789–$100.003 (reavaliação de mercado). Retorno total do período: **0,00%**
    (arredondado — a conta nunca saiu, em termos de equity líquido, de perto de $100.000).
  - **Conta 2**: caixa **fixa em $36.892,07** desde 25-set (confirma zero ordens reais há mais de 2
    semanas); equity em **$181.424,50** a 11-out (último registo), **+2,19%** desde 26-mai. Isto é
    puramente reavaliação a preço de mercado de uma carteira comprada em maio — `paper_trades`
    (conta 2) continua em 138 registos, inalterado desde `max(timestamp)=2026-05-09` (mais de 5
    meses sem um trade novo).
  - **Métricas recalculadas nesta sessão** (ver `metrics.json` desta auditoria, fonte = query acima
    sobre `paper_snapshots`, 139 pontos diários por conta):
    | | Conta 1 | Conta 2 |
    |---|---|---|
    | Retorno total (26mai→11out) | 0,00% | +2,19% |
    | Máxima queda (drawdown) | −0,21% / −$211 | −5,24% / −$9.577 (queda de julho, inalterada) |
    | Sharpe anualizado | 0,025 | 0,525 |
    | Sortino anualizado | 0,017 | 0,754 |
    | Dias com ganho (dos dias com variação) | 4,3% | 38,4% |
    | VaR 95% diário | 0,00% | −0,81% |

  Isto é dinheiro **FICTÍCIO** (paper), não real. A conta 1 quase não varia porque, fora do
  rebalance de 28-set, está parada a fazer HOLD; a conta 2 é 100% reavaliação de mercado de uma
  carteira parada desde maio — nenhuma das duas curvas demonstra "o sistema de rebalanceamento
  automático funciona", porque nenhuma executa ordens novas rotineiramente.

### Estudo 0006 (earnings-vol iron-fly) — repo-irmão `trading`, não `ib_bot`
Verificado hoje em `/home/servidor/Desktop/cursor-projects/trading/studies/0006-earnings-vol/`:
**veredito final `forward_30events.md` = KILL, 2026-07-16**, com forward-test real de 36 eventos
(PF@mid 0,776, PF@touch 0,256) — fechado, sem contradição pendente na prosa.

**Achado novo desta sessão (ver secção d, BAIXO #12):** o ficheiro de estado **máquina-legível**
`phase-status.json` (mtime 2026-07-17, 1 dia DEPOIS do veredito final) ainda tem
`"status": "reopened_wide_wing_ironfly_survivor"` e um campo `"decision"` que fala de "REOPENED...
OOS-consistent defined-risk candidate" — isto é uma fase intermédia (25-27 de maio) anterior ao
forward-test final, nunca atualizada para refletir o KILL de 16-07. Um script ou agente que leia
só este JSON (em vez da prosa em `forward_30events.md`) concluiria erradamente que o estudo está
"reaberto e a sobreviver", quando na realidade está morto desde julho. Isto é do repo `trading`,
não do `ib_bot` — fora do âmbito de correção direta desta auditoria, mas registado porque o brief
pede números do estudo 0006.

### Conta real na Interactive Brokers (via timer `lifeos-ib-refresh`, conta pessoal `jose`)
O conector MCP `Interactive Brokers (IBKR)` **não está autorizado nesta sessão headless**
(confirmado pelo aviso do próprio ambiente). Em vez de inventar o saldo, usou-se o registo mais
recente do timer `lifeos-ib-refresh.service`:
```
journalctl -u lifeos-ib-refresh.service --since "2026-10-01"
```
→ progressão diária: 05-out `26.968,15` → 06-out `27.246,51` → 07-out `27.651,07` → 08-out
`29.045,04` → 09-out `30.784,68` → 10-out `30.545,17` → 11-out `30.555,72` → 12-out `30.276,98`
(9 posições). Isto é a **conta pessoal do José**, gerida manualmente por ele fora deste bot — não
é do `ib_bot` (`ib_orders=0` continua exatamente igual). Registado só para manter o estado da conta
atualizado; não é um achado do bot.

### Planos do Conductor (`psql -U servidor -d conductor`)
| Plano | Slug | Status | Nota |
|---|---|---|---|
| `3702771c` — ib_bot → Alt-Data Product | `ib_bot` | `superseded` | Sem alterações. |
| `e36e04ec` — pós-triagem 2026-07-12 | `ib_bot` | `superseded` | Sem alterações. |
| `04bf8af8` — Alt-data PIT archive hardening | `ib_bot` | `done` | Sem alterações. |
| `4c48535c` — IB bot money-path hardening | `ib_bot` | `done` (fechado 2026-09-15) | Sem alterações. |

**Nenhum plano novo, aberto ou `executing`, para o slug `ib_bot` desde 2026-09-15 (27 dias)** —
confirmado de novo. O `insufficient cash` de 14 dias não tem nenhum plano a dar-lhe dono.

## (d) Findings, ordenados por gravidade

### CRÍTICO

**#0 (PIORA — 14 dias sem dono, era 7) — A conta paper 2 continua a falhar `insufficient cash`
todos os dias desde 2026-09-28, sem diagnóstico nem correção.** Evidência: 14 linhas idênticas em
`paper_rebalance_logs` (09-28 a 10-11), `backend/app/api/routes/paper.py` sem alterações desde
09-28, `paper_snapshots` da conta 2 com caixa fixo em $36.892,07 há mais de 2 semanas. Risco
monetário: **zero** (dinheiro fictício, `ENABLE_LIVE_TRADING=false` confirmado em `.env`, sem
plano Conductor que mexa em dinheiro real). Risco real: qualquer decisão futura (incluindo pelo
próprio José) que olhe para a curva de equity da conta 2 como "prova de que o motor de
rebalanceamento funciona" estaria enganada — a curva é só reavaliação de mercado desde maio. Causa
provável (não confirmada nesta sessão, ver achado e código citado na auditoria de 10-05): o cálculo
de pesos combinados da conta 2 tenta gastar mais caixa do que tem disponível, sem validação prévia.

### ALTO

**#1 — Decisão de negócio sobre o arquivo PIT continua pendente, agora há mais de 2 meses.**
`altdata_snapshots` cresceu para 1009 linhas / 92 dias, tudo engenharia e armazenamento sem decisão
de uso (vender/arquivar/continuar) desde o gate ter fechado em 2026-08-11. One-pager de
licenciamento B2B já pronto (`docs/altdata_b2b_one_pager_draft.md`) — falta só a palavra do José.

**#2 — Nenhuma das 56 estratégias de investimento tem edge robusto (inalterado desde maio); o único
candidato fora do catálogo (estudo 0006) está morto desde julho.** Não há nenhum candidato vivo a
investigar sem gerar novas ideias do zero — ver plano futuro de decisão estratégica.

**#3 — Imagens Docker ainda em 48,72 GB reclamáveis (melhorou de 61 GB, mas sem ação auditável
atribuível).** Ninguém documentou correr `docker image prune`/`builder prune`; a melhoria pode ser
coincidência (outro processo no host, ou GC automático do Docker) — não é seguro assumir que o
padrão "ninguém limpa isto a não ser pedido" mudou. Disco raiz a 87% (240 GB livres) — ainda
confortável.

### MÉDIO

**#4 — Resíduo de documentação desatualizada dentro do próprio repositório: `docs/audits/ib_bot/
metrics.json` e `section.json` (escritos pela 1ª auditoria em 07-12) continuam a descrever o
estudo 0006 como "por reconciliar"** — já reconciliado e fechado (KILL) desde 07-16, há quase 3
meses. 3ª auditoria consecutiva a repetir esta recomendação sem ninguém a corrigir ou remover.

**#5 — Risco de coordenação entre `ib_bot` (dormente) e `trading_manager` (ativo) sobre o mesmo
código de execução IB, sinalizado em 09-28, continua sem incidente novo** — apenas a monitorizar,
não é uma ação deste projeto.

### BAIXO

**#6 — Os nomes de ficheiro de memória citados no brief original (`project_ib_bot.md`,
`project_ib_bot_audit.md`, `project_pead.md`, `project_earnings_vol.md`) continuam a não existir**
sob esses nomes exatos — consolidados em `MEMORY-trading.md` e `reference_ib_bot_*.md`. Risco: um
agente futuro que procure pelo nome antigo exato não encontra nada.

**#7 — O ficheiro `phase-status.json` do estudo 0006 (repo `trading`) tem um campo `status`/
`decision` desatualizado** que descreve uma fase intermédia (REOPENED, 25-27 maio) em vez do
veredito final (KILL, 16-07) — ver secção (c). Fora do repo `ib_bot`, registado por completude.

**#8 — A melhoria de 12 GB nas imagens Docker e 12 GB no build cache desde 10-05 não tem nenhuma
ação atribuível (commit, log, ou registo de memória).** Pode repetir-se ou pode não se repetir;
não convém assumir que o problema #3 se vai resolver por si.

### INFORMATIVO / POSITIVO

**#A — `ib-altdata-backup.service` recuperou-se sozinho no disparo seguinte, exatamente como a
auditoria de 10-05 previu** — sem intervenção manual, confirma que o resíduo "failed" era mesmo
cosmético.

**#B — Todos os jobs automáticos (`ib-altdata-backup`, `ib-altdata-qa`, `ib-backtests`) correram
com sucesso nos 7 dias desde a última auditoria, sem falhas novas.**

**#C — As 4+ camadas de bloqueio a ordens reais continuam intactas e re-confirmadas**:
`ibgateway.service` parado, `ENABLE_LIVE_TRADING=false` em `.env`, `ib_orders=0`/`ib_trades=0`,
guarda de pré-voo de ordens e gate atómico de colocação (planos `4c48535c`, `done`).

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Diagnosticar e corrigir o `insufficient cash` da conta 2 (achado CRÍTICO #0)** — é o único
   problema crítico, agora com 14 dias sem dono; risco zero de dinheiro real, mas cada dia que
   passa é mais um dia de curva de equity sem sentido. Ver plano de fixes, passo 1.
2. **Resolver a decisão de negócio do arquivo PIT (#1)** — a única decisão deste projeto que
   depende só do José, não de engenharia; mais de 2 meses pendente.
3. **Remover/atualizar `docs/audits/ib_bot/metrics.json`/`section.json` desatualizados (#4)** —
   cosmético mas barato, evita confundir a próxima auditoria pela 4ª vez.
4. **Decidir (e documentar) uma rotina de limpeza Docker, já que a melhoria observada não é
   atribuível (#3/#8)** — ou automatizar com um timer semanal `docker image prune -af
   --filter until=720h`, ou aceitar explicitamente que não é prioridade enquanto há 240 GB livres.
5. **Registar em memória os novos caminhos dos ficheiros consolidados (#6)** — cosmético, baixo
   esforço.
6. **(Fora do ib_bot, mas sinalizar ao dono do repo `trading`) corrigir `phase-status.json` do
   estudo 0006 (#7)** — não é ação deste plano de fixes, só uma nota a passar.

## (f) Riscos se nada for feito

- **Nenhum risco de perda de dinheiro real hoje.** Trading ao vivo está travado em 4+ camadas
  (`ibgateway` desligado há 46 dias, `ENABLE_LIVE_TRADING=false`, guarda de pré-voo, gate atómico).
  `ib_orders=0`/`ib_trades=0` confirmado de novo.
- **Risco confirmado e a continuar: a curva de equity "paper" da conta 2 continua sem significado
  real**, agora há 14 dias, sem diagnóstico. Quanto mais tempo sem correção, mais naturalizado fica
  o erro no log — risco de alguém assumir "é assim mesmo" em vez de investigar.
- **Risco de decisão por omissão sobre o arquivo PIT** — quanto mais tempo sem decisão, mais dados
  acumulados sem destino claro (1009 linhas e a crescer ~11/dia), mais difícil fica justificar
  continuar a gastar engenharia/armazenamento nisto sem um objetivo de negócio.
- **Risco de disco Docker voltar a crescer sem aviso** — a melhoria desta semana não é atribuível a
  nenhuma ação; sem uma rotina programada, o padrão "ninguém limpa a não ser que seja pedido" (visto
  em 7 auditorias anteriores) pode voltar.
- **Risco de fadiga de auditoria** — esta é a 12ª auditoria semanal consecutiva do mesmo projeto
  pausado, com o mesmo achado crítico a repetir-se sem dono há 2 semanas. Sem um plano Conductor
  formal com dono, estas auditorias vão continuar a documentar o mesmo problema sem o resolver.

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
- **ETF (Exchange-Traded Fund)** — um "fundo" que se compra e vende na bolsa como se fosse uma
  ação normal, mas que por dentro é uma cesta de várias ações (ex.: a NANC segue as compras de
  políticos dos EUA).
- **Celery beat/worker** — um "relógio" (beat) que dispara tarefas periódicas dentro da própria
  aplicação, e um "trabalhador" (worker) que as executa de facto.
- **systemd timer / service** — o despertador do próprio computador Linux (timer) que dispara uma
  tarefa a uma hora marcada (o service), fora de qualquer aplicação.
- **Docker / container / imagem** — uma "caixa" isolada onde um programa corre com tudo o que
  precisa; a "imagem" é o molde de onde a caixa é criada, e pode ficar guardada em disco mesmo
  depois da caixa parar.
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
