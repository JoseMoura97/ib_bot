# Audit Profundo — IB Bot (2026-10-05, ART / manhã em Portugal WEST)

> Sessão de auditoria: `/home/servidor/agent-workspaces/mega-audit-2026-10-05`.
> Todos os comandos abaixo foram corridos NESTA sessão (ground truth re-verificado, não copiado
> de memória nem de auditorias anteriores). Esta é a **11ª auditoria profunda** deste projeto
> (depois de 2026-07-12, 2026-07-20, 2026-08-10, 2026-08-17, 2026-08-24, 2026-08-31, 2026-09-07,
> 2026-09-14, 2026-09-21 e 2026-09-28 — confirmado com `ls docs/audits/*.md`), sempre no mesmo
> repositório (`/home/servidor/Desktop/cursor-projects/ib_bot`, HEAD de hoje `270aa90`).
>
> **Nota sobre o brief:** o pedido que chegou a este agente descreve o projeto com 3 roots
> (`ib_bot`, `ib_bot-v2`, `ib_bot-altdata-wt`) e memórias `project_ib_bot.md`,
> `project_ib_bot_audit.md`, `project_pead.md`, `project_earnings_vol.md`. Re-verificado agora:
> `ib_bot-altdata-wt` **continua a não existir** (10ª vez a confirmar isto); os ficheiros de
> memória com esses nomes exatos **já não existem** — foram consolidados em
> `MEMORY-trading.md` + ficheiros `reference_ib_bot_*.md`/`reference_ibkr_*.md` dentro de
> `/home/servidor/.claude/projects/-home-servidor/memory/`, mais dois ficheiros à parte em
> `/home/servidor/.claude/projects/-home-servidor-Desktop-cursor-projects-conductor/memory/`
> (`project_ib_bot_a1_altdata_b2b_timegate_wake.md`,
> `project_ib_bot_h3_frozen_gtc_unsatisfiable_journal_rotated.md`). O conteúdo histórico que o
> brief resume (dormência seletiva, NANC ETF, estudo 0006, PEAD rejeitado) está correto — só os
> nomes de ficheiro mudaram. Isto é tratado como achado BAIXO (ver secção d).
>
> Esta auditoria também herda o estilo e os números das 10 anteriores e, em vez de repetir tudo
> do zero, foca-se no que **mudou** desde a de 2026-09-28 — que é mais do que o habitual: houve
> uma correção real de um bug crítico de 45 dias, uma nova falha operacional (e a sua correção,
> ambas na madrugada de hoje) e o desmantelamento completo de um dos dois frontends duplicados.

## (a) O que é este projeto (para um miúdo de 12 anos)

O **IB Bot** é um robô de computador que devia comprar e vender ações sozinho, usando a conta de
trading do José na **Interactive Brokers (IB — a corretora, a empresa que executa as ordens de
compra/venda na bolsa)**. A ideia era copiar o que "gente esperta" faz — políticos dos EUA quando
compram ações, fundos famosos (como o de Warren Buffett) quando publicam os seus relatórios
trimestrais (um **13F**, o documento que esses fundos são obrigados a publicar), gestores que
apostam contra empresas (Michael Burry) — e ver se copiar essas jogadas dá dinheiro.

O robô testou **56 ideias diferentes** ("estratégias") em dados históricos com um motor de
**backtest** (simular "se eu tivesse seguido esta regra no passado, ganhava ou perdia?"). Um
estudo interno rigoroso de maio de 2026 (o **Deflated Sharpe Ratio** — um teste estatístico que
pune ter experimentado muitas ideias, porque quanto mais tentas, maior a hipótese de uma parecer
boa só por sorte) concluiu que **nenhuma das 56** tem ganho real acima do que se esperaria por
sorte. O projeto foi **pausado** nessa altura ao nível de decisão de negócio.

Tem quatro peças vivas hoje:
1. **Motor de backtest** — testa ideias no passado, de graça, sem risco. Corre sozinho todas as
   semanas (domingo de madrugada).
2. **Motor de execução real** — a peça que manda ordens verdadeiras para a IB. Está **desligada**
   desde final de agosto de 2026 por decisão do José ("dormência seletiva"), e continua desligada
   hoje.
3. **Arquivo "ponto-no-tempo" (PIT — point-in-time)** — desde 13 de julho de 2026, o robô tira uma
   "fotografia" todos os dias de 11 fontes de dados públicas e guarda-a para sempre, mesmo que a
   fonte original mude depois.
4. **"Paper trading" (fingir que compra/vende ações com dinheiro que não existe, para testar o
   sistema sem risco)** — corre todos os dias sozinho. **Novidade de hoje:** a parte deste motor
   que estava quebrada há 45 dias corridos foi corrigida na passada segunda-feira (09-28), MAS
   apareceu de imediato um segundo problema diferente numa das duas contas fictícias (ver secção
   d, achado CRÍTICO #0).

O projeto está marcado como **PAUSED (pausado)** no sistema de gestão de projetos do José (o
**Conductor** — o painel onde ele vê o trabalho dos seus agentes de IA), o que significa "não se
decide o próximo grande passo de negócio" — não significa "desligado". Há vários processos
automáticos a correr todos os dias sozinhos (ver secção c).

## (b) Evolução até hoje (timeline, com datas verificadas)

Fonte: `git log --all` completo do repositório (336 commits) + as 10 auditorias anteriores no
mesmo diretório + `psql -U servidor -d conductor` (4 planos e ~110 linhas de `plan_knowledge`
ligadas ao slug `ib_bot`) + memórias em `/home/servidor/.claude/projects/-home-servidor/memory/`
e em `.../-home-servidor-Desktop-cursor-projects-conductor/memory/`.

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repositório. |
| 2026-01 a 2026-04 | Construção inicial: motor de backtest, catálogo de 56 estratégias, execução IB, frontend. |
| 2026-05 | Auditoria de investibilidade v1→v4 (Deflated Sharpe Ratio): v1 descobre que o "alfa" de várias estratégias era beta de mercado disfarçado; v3 mede decaimento de sinal desde que ETFs públicos como a NANC (que copiam publicamente o mesmo truque de "seguir políticos") começaram a competir em 2023 (Congress Buys Sharpe 1,03→0,21); v4 (AUTORITATIVA) aplica Deflated Sharpe e reprova as 56. Recomendação: licenciar o motor de dados, não vender "alfa"; ação nº1 = arquivar PIT. |
| 2026-05-09 | **Última linha nova em `paper_trades` da conta 2 até hoje** — confirmado de novo nesta sessão (`max(timestamp)=2026-05-09`, inalterado há quase 5 meses). |
| 2026-07-12/13 | Decisão de negócio do José: **dormência seletiva** (plano Conductor `e36e04ec`). Arranca o arquivo diário PIT. Estudo 0006 (iron-fly earnings-vol) autopsiado: a suposta PF intraday 1,42–1,78 era artefacto de 559/3264 eventos com `max_risk≈0`; recalculada honestamente dá 0,109 — pior que o EOD (0,06–0,37 todos os anos). |
| 2026-07-16 | **Estudo 0006: veredito final pré-registado KILL**, com forward-test de 36 eventos reais confirmando (PF@mid 0,776, PF@touch 0,256 — o custo de execução, por si só, transforma "quase neutro" em "perdedor claro"). Decisão: zero gasto (não renovar ThetaData pago), manter o timer de vigia de graça. Não há contradição por reconciliar — está fechado desde este dia. |
| 2026-08-05 a 08-20 | Plano Conductor `04bf8af8` "Alt-data PIT archive hardening" fecha `done` (replicação offsite, separação de dono da BD — bloqueada por limitação real do Postgres, timer QA soak de 3 dias). |
| 2026-08-11 | Gate calendário do arquivo PIT fecha (30 dias/328 linhas). One-pager de licenciamento B2B fica pronto; decisão de José sobre avançar com outreach comercial **ainda pendente hoje** (quase 2 meses depois). |
| 2026-08-14 a 09-27 | **A tarefa diária `paper_rebalance_daily_task` falha silenciosamente todos os dias, para as duas contas, com `tuple index out of range`.** Descoberta na auditoria de 2026-09-07; confirmada repetidamente até **45 dias corridos sem interrupção** (auditoria de 09-28). |
| 2026-08-27 20:54 | `ibgateway.service`/`xvfb-ibgw.service` parados (continuam parados hoje) — gateway tinha `ReadonlyLogin=yes` e ligava à conta errada (`U23842862`, não à pessoal `U15721390`); confirmado no mesmo dia que isto é uma decisão deliberada de dormência, não um acidente. |
| 2026-08-30 – 2026-09-15 | Duas rondas de hardening de segurança do caminho de execução real (planos Conductor `8e1fa5aa` e `4c48535c`) fecham `done`: gateway fail-closed, parsers IB rejeitam payloads malformados, guarda partilhada em todos os caminhos de ordem. 291-317 testes passam. Zero ordens reais em qualquer momento. |
| 2026-09-20/24 | `trading_manager` (outro dono) publica 2 commits neste repo (`f86848f`, `486b6e3`) para reutilizar o adaptador de execução IB só-leitura numa investigação de futuros E-mini, e adiciona uma guarda (`require_main()`) ao script de backup noturno contra publicar trabalho de laboratório por engano. |
| 2026-09-28 (10ª auditoria) | Confirma o bug crítico do paper rebalance a 45 dias; recomenda pela 7ª vez a mesma limpeza (dois frontends, 31,5 GB de imagens Docker, resíduos no root). **Mesmo dia, horas depois, outro operador (Antonio Manuel) corrige o bug** (commit `1391c6f`, 15:50 WEST): a causa real era chamar a rota FastAPI decorada com rate-limit (`paper_rebalance_execute`) diretamente do Celery sem um `Request` HTTP — isso rebentava dentro do SlowAPI *antes* de qualquer lógica de rebalanceamento correr, e aparecia como `tuple index out of range`. O mesmo commit também arruma os 4 ficheiros `undefined_*.md`/residuais do root citados nas 7 auditorias anteriores. |
| **2026-09-28 15:00 WEST (mesmo dia, após o fix)** | A conta paper 1 executa rebalanceamento **pela primeira vez em 126 medições** (32 ordens reais contra a carteira fictícia) — equity cai de $100.000 para $91.957 de caixa. A conta 2, porém, passa a falhar com um erro **diferente e novo**: `HTTPException 400: insufficient cash`, todos os dias desde então (7 dias seguidos até hoje, 09-28 a 10-04) — ver achado CRÍTICO #0 revisado nesta auditoria. |
| 2026-09-?? (sem commit, não documentado) | `/home/servidor/Desktop/cursor-projects/ib_bot-v2` (Docker Compose completo + `ib-bot-v2-frontend.service`, porta 3001) **deixa de existir por completo** — confirmado hoje: zero containers `ib_bot-v2`/`ibbotv2`, a unidade systemd `ib-bot-v2-frontend.service` já nem está instalada (`systemctl status` → "could not be found"). Isto fecha o achado ALTO #2 repetido em 7 auditorias seguidas ("dois frontends vivos"), mas sem registo de quem/quando o fez. |
| **2026-10-04 05:16–05:45 WEST** | Execução semanal `ib-backtests.service` corre normalmente (56/56, `runjob --mem 4G --cpu 4`), mas escreve o recibo em `reports/weekly_backtest_receipt.json` — um caminho **versionado** (não ignorado pelo git) — deixando o checkout principal sujo. |
| **2026-10-05 04:34:25 WEST** | `ib-altdata-backup.service` **falha** (`exit 2`, `Result=exit-code`) com a mensagem `refusing to run: working tree is dirty` — a guarda `require_main()` adicionada em 09-24 (ver linha acima) funcionou exatamente como desenhada: recusou publicar o backup noturno com o checkout sujo, em vez de publicar por engano. |
| **2026-10-05 04:38–04:39 WEST (4 min depois)** | O mesmo operador (Antonio Manuel) corrige a causa raiz (`1668947`, "keep weekly receipt in runtime cache": move o recibo para `.cache/weekly_backtest_receipt.json`, já ignorado pelo git) e corre o backup manualmente, publicando-o (`270aa90`). `git status` hoje está limpo. A unidade systemd `ib-altdata-backup.service` continua a mostrar `Active: failed` porque não voltou a disparar desde essa falha (próximo disparo normal: amanhã ~04:3x WEST) — é um resíduo cosmético de estado, não um problema a continuar. |
| **2026-10-05 (hoje)** | Este audit (11º). |

## (c) Estado concreto HOJE (verificado nesta sessão)

### Repositórios e worktrees
```
git worktree list
/home/servidor/Desktop/cursor-projects/ib_bot     270aa90 [main]
/home/servidor/Desktop/cursor-projects/ib_bot-v2  25f7a6a [frontend-v2]
/home/servidor/ib-altdata-guard-20260924          486b6e3 [fix/altdata-backup-main-20260924]
/home/servidor/ib-backtest-receipt-20261005       1668947 [fix/weekly-backtest-receipt-cache-20261005]
```
`ib_bot-v2` continua a ser um *worktree git* do mesmo repositório (não um projeto separado,
apesar do nome) — mas, como visto em (b), a sua stack Docker e o seu serviço de frontend
deixaram de existir; só o checkout de ficheiros continua no disco. `ib_bot-altdata-wt` (citado no
brief) **continua a não existir**. Há um worktree novo desde ontem (`ib-backtest-receipt-20261005`)
que parece ser o workspace onde o fix do recibo semanal (`1668947`) foi desenvolvido antes de ser
publicado em `main` — consistente com a regra do `AGENTS.md` de nunca trabalhar diretamente no
checkout principal.

`git status --porcelain` no checkout principal: **vazio** (limpo).

### Serviços systemd (comando: `systemctl status <unit>` / `systemctl cat` corridos nesta sessão)
| Unit | Estado | Nota |
|---|---|---|
| `ibgateway.service` | `inactive (dead)`, `disabled` | Parado desde 2026-08-27 20:54 WEST, inalterado. Sem listener em `:4001`. |
| `xvfb-ibgw.service` | `inactive (dead)`, `disabled` | Idem. |
| `ibgw-watchdog.service` / `ibeam-session-manager.service` / `ib-socat.service` | `inactive (dead)`, `disabled` | Acessórios do gateway, todos parados. |
| `ib-bot-v2-frontend.service` (porta 3001) | **já não existe como unidade** | Confirmado `systemctl status` → "could not be found". Em 09-28 estava `active` há 1 mês+. |
| `ib-bot-v2-frontend-public.service` (porta 3002) | `inactive (dead)`, `disabled` | Nunca foi ligada nesta janela. |
| `ib-altdata-backup.timer` / `.service` | timer `enabled`/`active (waiting)`; serviço `failed` (última corrida) | Ver timeline 10-05 04:34. Vai recuperar no próximo disparo normal; a causa raiz já está corrigida. |
| `ib-altdata-qa.timer` / `.service` | `enabled` / `active (waiting)` | Última corrida (04-10 08:00) `success`; receita 84→85 dias verificados, hash-chain OK. |
| `ib-backtests.timer` / `.service` | `enabled` / `active (waiting)` | Última corrida (04-10 05:16-05:45) `success`, 56/56, dentro de `runjob --mem 4G --cpu 4`. |
| `theta-terminal.service` + 5 timers (`theta-learned`, `paper-ironfly`, `historical-backfill`, `execution-metrics`, `cost-recalibration`) | Todos `active` | **Re-confirmado com `systemctl cat` nesta sessão: NENHUM pertence ao ib_bot.** 4 apontam para `/home/servidor/Desktop/cursor-projects/polytrader-bot-master` (descrições dizem literalmente "Polymarket"); `paper-ironfly` aponta para `/home/servidor/Desktop/cursor-projects/trading` (o bot-irmão de opções, dono do estudo 0006 — ver secção (b) 2026-07-16). "theta" aqui é sobre modelos de decaimento de probabilidade do Polymarket, não sobre opções financeiras do ib_bot — coincidência de nome que confunde à primeira vista; 11ª auditoria a confirmar a mesma distinção. |
| `lifeos-ib-refresh.timer` / `.service` | `enabled` / `active (waiting)` | Do projeto `lifeos`, não do `ib_bot` — lê o saldo real da conta pessoal do José via MCP, hoje às 03:15 WEST: `net_liq=26968.15`. |

### Stack Docker (`docker ps -a --filter name=ib_bot`, `docker system df`)
```
ib_bot-worker-1   Up 6 days
ib_bot-api-1      Up 6 days    0.0.0.0:8001->8000/tcp
ib_bot-beat-1     Up 6 days
ib_bot-db-1       Up 7 weeks   5432/tcp (não exposta ao host)
ib_bot-redis-1    Up 7 weeks   6379/tcp
ib_bot-web-1      Up 7 weeks   3000/tcp
ib_bot-nginx-1    Up 7 weeks   0.0.0.0:8090->80/tcp
```
`curl localhost:8001/health` → `200`. `curl localhost:8090` → `200`. `curl localhost:3001` e
`curl localhost:3002` → sem resposta (nada a escutar, confirma o frontend duplicado desligado).
**Agora só UMA interface web viva** (porta 8090) — achado ALTO #2 das 7 auditorias anteriores
está **resolvido** (ver secção d, achado positivo).

`docker system df`:
```
Images          20    20    61.09GB   61.09GB (100%)
Build Cache     26     0     35.97GB   12.37GB
```
**Piorou desde 09-28** (31,51 GB → 61,09 GB de imagens 100% reclamáveis, mais 36 GB de build
cache). Disco raiz: `df -h /` → 1,8 TB total, **89% usado, 204 GB livres**. Ainda não é uma
emergência, mas a tendência é a errada para um projeto pausado (ver achado ALTO #6 revisado).

### Tarefas internas do bot (celery beat/worker — `docker logs ib_bot-worker-1`)
- `altdata_snapshot_daily_task` — saudável todos os dias (confirmado pela tabela, ver abaixo).
- **`paper_rebalance_daily_task` (15:00 WEST diário) — PARCIALMENTE CORRIGIDA, achado CRÍTICO #0
  revisado:**
  - **Conta 1** (`portfolio=7095ae3e...`): `tuple index out of range` todos os dias até 09-27;
    **09-28 `SUCCESS`, 32 ordens** (primeira execução real de sempre); 09-29 a 10-04 `not due`
    (frequência `quarterly`, próxima devida só dentro de meses) — **comportamento correto e
    esperado**, não é um novo problema.
  - **Conta 2** (`portfolio=d2e87bea...`): `tuple index out of range` todos os dias até 09-27;
    **09-28 a 10-04 (7 dias seguidos, SEM excepção) `ERROR: HTTPException 400: insufficient
    cash`** — um erro NOVO e DIFERENTE, agora capturado com `logger.exception` + traceback
    completo (o próprio fix de 09-28 já corrigiu esse ponto), mas ainda sem correção da causa.
    Confirmado em `paper_rebalance_logs` (tabela da BD, não só nos logs do container):
    ```
    docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
      "SELECT account_id, status, n_orders, timestamp, details->>'error' FROM paper_rebalance_logs
       WHERE timestamp >= '2026-09-27' ORDER BY timestamp DESC LIMIT 20;"
    ```
    devolve 7 linhas `account_id=2|ERROR|0|<data>|HTTPException: 400: insufficient cash`
    seguidas, mais as 2 últimas `tuple index out of range` (09-27) e a `SUCCESS|32` (09-28, conta 1).

### Base de dados (Postgres dentro de `ib_bot-db-1`)
- `ib_orders` = **0**, `ib_trades` = **0**, `live_execution_requests` = **0** — zero ordens reais
  desde sempre, inalterado.
- `altdata_snapshots` = **932 linhas**, `count(distinct captured_at::date)` = **85 dias**
  (13-jul a hoje 05-out, última captura `2026-10-05 06:00:39`) — cresceu 77 linhas desde 09-28
  (855→932), ritmo de ~11/dia mantido, consistente.
- `paper_snapshots` (query `SELECT account_id, timestamp::date, equity, cash FROM paper_snapshots
  WHERE timestamp >= '2026-09-25'...`):
  - **Conta 1**: $100.000,00 fixo em 09-25/26/27 → cai para **$91.957,47 de caixa** em 09-28 (o
    rebalanceamento real de 32 ordens) e mantém-se nesse caixa desde então (equity a oscilar
    $99.789–$99.922 por reavaliação de mercado das posições compradas).
  - **Conta 2**: caixa **fixo em $36.892,07** desde 09-25 até hoje (confirma que o
    rebalanceamento continua a não executar nenhuma ordem nesta conta); equity de
    **US$179.680,45** hoje (04-out, último registo), descendo de US$181.210,62 em 25-set (−0,84%
    na semana, dentro do ruído normal de reavaliação a preço de mercado — sem trade novo).
  - `paper_trades` (conta 2): continua em **138 registos**, inalterado desde
    `max(timestamp)=2026-05-09` — quase 5 meses sem um trade novo, confirmando que a curva da
    conta 2 é só reavaliação a preço de mercado de uma carteira comprada em maio.
  - **Curva completa (26-mai a 04-out, 132 dias únicos) recalculada nesta sessão** (ver `metrics.json`
    desta auditoria): retorno total **+0,96%**, máxima queda (drawdown) **−5,24% / −US$9.577**
    (ainda a mesma queda de julho), Sharpe anualizado **0,26**, Sortino **0,38**, taxa de dias
    positivos **38%**. Isto é dinheiro FICTÍCIO (paper), não real.

### Estudo 0006 (earnings-vol iron-fly) — repo-irmão `trading`, não `ib_bot`
Verificado hoje em `/home/servidor/Desktop/cursor-projects/trading/studies/0006-earnings-vol/`:
**veredito KILL, fechado desde 2026-07-16**, sem contradição pendente (ver timeline). O ficheiro
`docs/audits/ib_bot/metrics.json`, deixado dentro deste repositório pela auditoria original de
07-12 (antes da reconciliação), ainda descreve a versão desatualizada "por reconciliar" — achado
BAIXO nesta auditoria (ver secção d).

### Conta real na Interactive Brokers (via timer `lifeos-ib-refresh`, que usa o MCP IBKR na conta `jose`)
O conector MCP `Interactive Brokers (IBKR)` **não está autorizado nesta sessão headless**
(confirmado pelo aviso do próprio ambiente — ferramentas MCP requerem OAuth interativo que este
agente não pode completar). Em vez de inventar o saldo, usou-se o registo mais recente do
timer `lifeos-ib-refresh.service` (que corre esse mesmo MCP, na conta `jose`, 1x/dia):
`journalctl -u lifeos-ib-refresh.service` → **hoje 03:15:24 WEST: `net_liq=26968.15`, 6
posições**. Isto é a **conta pessoal do José**, gerida manualmente por ele — **não é do bot**
(`ib_orders=0` continua exatamente igual). Registado aqui só para manter o estado da conta
atualizado, consistente com as 10 auditorias anteriores; não é um achado do bot.

### Planos do Conductor (`psql -U servidor -d conductor`)
| Plano | Slug | Status | Nota |
|---|---|---|---|
| `3702771c` — ib_bot → Alt-Data Product | `ib_bot` | `superseded` | Sem alterações. |
| `e36e04ec` — pós-triagem 2026-07-12 | `ib_bot` | `superseded` | Sem alterações. |
| `04bf8af8` — Alt-data PIT archive hardening | `ib_bot` | `done` | Sem alterações. |
| `4c48535c` — IB bot money-path hardening | `ib_bot` | `done` (fechado 2026-09-15) | Sem alterações. |

**Nenhum plano novo, aberto ou `executing`, para o slug `ib_bot` desde 2026-09-15** — confirmado
de novo nesta sessão. O fix do bug crítico (09-28) e o fix do recibo do backtest (hoje) foram
feitos **fora** de qualquer plano Conductor formal, por um operador humano direto (Antonio
Manuel), não por um agente despachado por um plano — isso é consistente com o projeto estar
`PAUSED` (sem dono de plano ativo), mas significa que estas correções não deixaram nenhum rasto em
`plan_knowledge` para a próxima auditoria encontrar automaticamente; só o `git log` revela.

## (d) Findings, ordenados por gravidade

### CRÍTICO

**#0 (REVISADO — metade corrigida, metade é um problema novo) — O bug de 45 dias
(`tuple index out of range`) FOI corrigido em 2026-09-28 (commit `1391c6f`), horas depois da
auditoria anterior o sinalizar. A causa raiz era um bug de engenharia claro: a tarefa diária do
Celery chamava diretamente a função da rota FastAPI `paper_rebalance_execute` — que tem o
decorador `@limiter.limit("10/minute")` do SlowAPI e espera um objeto `Request` HTTP — passando
`request=None`; isso rebentava dentro do próprio SlowAPI antes de qualquer lógica de
rebalanceamento correr, e a excepção genérica aparecia disfarçada como `tuple index out of
range`. O fix extraiu a lógica real para `paper_rebalance_execute_core(body, db)` e o Celery passou
a chamar essa função diretamente. Prova: conta 1 executou pela primeira vez em 126 medições (32
ordens reais, equity caiu de $100.000 para $91.957 de caixa).**

**MAS: a conta 2 passou a falhar com um erro NOVO e DIFERENTE desde o mesmo instante do fix —
`HTTPException 400: insufficient cash`, 7 dias seguidos sem excepção (09-28 a 10-04), caixa
fixo em $36.892,07.** Isto significa que o motor de rebalanceamento da conta 2 nunca, em nenhum
dia desde o fix, concluiu uma única ordem real — a curva de equity desta conta continua a ser só
reavaliação de preço de mercado, exatamente como antes do fix, só que agora por um motivo
diferente e mais fácil de explicar: o cálculo de pesos combinados da conta 2 está a tentar gastar
mais caixa do que ela tem disponível. Evidência: `paper_rebalance_logs` na BD (query na secção c),
e código em `backend/app/api/routes/paper.py:264-414` (constrói pesos combinados por estratégia,
chama `place_market_order` por perna — nenhuma validação de caixa disponível ANTES de tentar
colocar as ordens, só depois, a meio, quando uma falha com `400`). **Nenhum destes ficheiros foi
tocado desde o commit do dia 09-28** — ou seja, o novo erro já tem 7 dias sem diagnóstico.

**#1 (RESOLVIDO sem registo formal — ver secção INFORMATIVO/POSITIVO) — As recomendações de
limpeza repetidas em 7 auditorias seguidas (dois frontends, resíduos no root, ficheiros
`undefined_*`) foram, na sua maioria, silenciosamente corrigidas** entre 09-28 e hoje. **Mas uma
peça do mesmo problema PIOROU**: as imagens Docker reclamáveis quase duplicaram (31,5 GB → 61,1
GB) — ver achado ALTO #6 revisado.

### ALTO

**#2 (RESOLVIDO) — Os dois frontends web duplicados (repetido em 7 auditorias desde 08-17) já não
existem em paralelo.** `ib_bot-v2` (porta 3001, stack Docker Compose completa) foi desmantelado
por completo — zero containers, zero unidade systemd — algures entre 09-28 e hoje, sem commit nem
registo de memória a dizer quem/quando. Confirma-se de novo que uma limpeza recomendada
repetidamente SÓ acontece quando alguém a prioriza manualmente (mesmo padrão já visto com o
`.worktree-quarantine/` em 09-21→09-28). Resta só a stack original (porta 8090 + API 8001).

**#3 — Nenhuma das 56 estratégias de investimento tem edge robusto, confirmado repetidamente
(inalterado desde maio).** Deflated Sharpe Ratio reprova as 56. Estudo 0006 (a única candidata
"interessante" fora do catálogo das 56) está KILL definitivo desde 07-16 (ver secção b/c) — não
há mais nenhum candidato vivo a investigar.

**#4 — Decisão de negócio sobre o arquivo PIT continua pendente.** `altdata_snapshots` cresceu
para 932 linhas / 85 dias, tudo engenharia e armazenamento sem decisão de uso (vender/arquivar/
continuar) desde o gate ter fechado em 2026-08-11 — **quase 2 meses sem resposta registada do
José**, apesar do one-pager de licenciamento já estar pronto e escalado ao Manager.

**#6 (REVISADO, PIOROU) — Imagens Docker reclamáveis quase duplicaram: 31,51 GB (09-28) → 61,09
GB (hoje), mais 35,97 GB de build cache (12,37 GB reclamável).** Ninguém correu `docker image
prune`/`docker builder prune` nas 6 semanas seguintes à primeira recomendação (08-24). Disco raiz
a 89% de uso (204 GB livres de 1,8 TB) — ainda confortável, mas a crescer na direção errada para
um projeto pausado.

### MÉDIO

**#5 — A conta 2 do paper rebalance continua, de facto, sem executar uma única ordem desde o
início dos registos (138 trades, nenhuma desde 09-mai) — agora por "insufficient cash" em vez de
por crash do engine.** Risco informativo, não monetário: qualquer decisão futura que use a curva
de equity da conta 2 como "prova de que o sistema de rebalanceamento funciona" estaria errada.

**#7 — Risco de coordenação entre `ib_bot` (dormente) e `trading_manager` (ativo) sobre o mesmo
código de execução IB, sinalizado em 09-28, continua sem incidente novo** — apenas a monitorizar,
não é uma ação deste projeto.

**#8 (NOVO, já resolvido no mesmo turno em que apareceu) — O recibo semanal do backtest
(`reports/weekly_backtest_receipt.json`) era escrito num caminho versionado pelo git, o que deixou
o checkout principal sujo depois da corrida de 04-10 e bloqueou (corretamente) o backup noturno
PIT de hoje de madrugada (`ib-altdata-backup.service` → `refusing to run: working tree is dirty`,
04:34 WEST). O mesmo operador corrigiu a causa 4 minutos depois (commit `1668947`, move o recibo
para `.cache/`, já ignorado pelo git) e publicou manualmente o backup do dia (commit `270aa90`).
**Resíduo cosmético:** `systemctl status ib-altdata-backup.service` ainda mostra `Active: failed`
da corrida falhada, porque a unidade só volta a correr no próximo disparo normal (amanhã); não
precisa de intervenção, mas fica registado para a próxima auditoria confirmar que limpou por si
só.**

### BAIXO

**#9 — Os nomes de ficheiro de memória citados no brief original desta auditoria
(`project_ib_bot.md`, `project_ib_bot_audit.md`, `project_pead.md`, `project_earnings_vol.md`)
já não existem** — foram consolidados em `MEMORY-trading.md` e vários `reference_*.md` dentro de
`/home/servidor/.claude/projects/-home-servidor/memory/`, mais 2 ficheiros num diretório de
memória diferente (`.../-home-servidor-Desktop-cursor-projects-conductor/memory/`). O conteúdo
sobrevive; só a localização mudou. Risco: um agente futuro que procure pelo nome antigo exato não
encontra nada e pode concluir erradamente que a informação se perdeu.

**#10 — `docs/audits/ib_bot/metrics.json` e `docs/audits/ib_bot/section.json`, deixados dentro
deste repositório pela 1ª auditoria (07-12), nunca foram atualizados** e descrevem o estudo 0006
como "por reconciliar" — já reconciliado e fechado (KILL) desde 07-16, 2 dias depois desses
ficheiros terem sido escritos. Esta auditoria escreve os seus próprios `metrics.json`/`section.json`
no caminho correto fora do repositório (`/home/servidor/agent-workspaces/mega-audit-2026-10-05/...`),
não dentro do repo — para não repetir este problema.

### INFORMATIVO / POSITIVO

**#A — O achado crítico #0 da auditoria anterior foi corrigido no mesmo dia em que foi
reportado** (09-28, poucas horas depois) por um operador humano direto, com diagnóstico correto e
teste de regressão (`test_paper_rebalance_cycles.py` ganhou 30 linhas novas). É a primeira vez em
11 auditorias que uma recomendação CRÍTICA é endereçada no mesmo dia.

**#B — Os dois frontends duplicados, pedidos há 7 auditorias, foram desmantelados.**

**#C — Os resíduos no root (`$LOG`, `alembic_validation.db`, `backtest_results_*.json`,
`docker-compose.prod.yml.bak.*`) e os 4 ficheiros `undefined_*.md` em `docs/plans/` já não
existem** — confirmado com `find` nesta sessão.

**#D — A guarda `require_main()` (instalada 09-24 pelo `trading_manager` para proteger o backup
noturno de trabalho de laboratório não revisto) funcionou hoje exatamente como desenhada**,
contra um cenário diferente do que a motivou (recibo de backtest sujo, não branch de laboratório)
— prova de que uma guarda bem desenhada generaliza.

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Diagnosticar e corrigir o novo erro `insufficient cash` da conta 2 (achado CRÍTICO #0,
   parte 2)** — é o único problema crítico genuinamente NOVO e NÃO corrigido; baixo risco (não
   mexe em dinheiro real), mas cada dia que passa é mais um dia de curva de equity sem sentido
   para a conta 2.
2. **Resolver a decisão de negócio do arquivo PIT (#4)** — quase 2 meses pendente, one-pager já
   pronto; é a única decisão deste projeto que depende só do José, não de engenharia.
3. **Limpar o disco Docker (#6)** — grátis, sem risco, recupera >60 GB; piorou desde a última vez
   que foi pedido.
4. **Confirmar que `ib-altdata-backup.service` recupera sozinho no disparo de amanhã (#8)** —
   verificação rápida, sem risco, para fechar o resíduo cosmético.
5. **Atualizar/remover `docs/audits/ib_bot/metrics.json`/`section.json` desatualizados dentro do
   repo (#10)** — cosmético mas evita confundir a próxima auditoria ou um agente externo.
6. **Registar em memória os novos caminhos dos ficheiros consolidados (#9)** — cosmético, baixo
   esforço, evita busca às escuras no futuro.

## (f) Riscos se nada for feito

- **Nenhum risco de perda de dinheiro real hoje.** Trading ao vivo está travado em 4+ camadas
  (`ibgateway` desligado, guarda de pré-voo de ordens, gate atómico de colocação, hardening
  completo do plano `4c48535c`). `ib_orders=0`/`ib_trades=0` confirmado de novo. Nenhum listener
  em `:4001`-`:4004`.
- **Risco confirmado e a continuar: a curva de equity "paper" da conta 2 continua sem significado
  real** — agora por um motivo diferente (`insufficient cash`) do que antes (`tuple index out of
  range`), mas o efeito prático para quem olhar os números é o mesmo: nenhuma ordem real é
  executada.
- **Risco de disco a crescer sem necessidade** — 61 GB de imagens Docker reclamáveis + 36 GB de
  build cache, numa máquina a 89% de uso, para um projeto pausado.
- **Risco de decisão por omissão sobre o arquivo PIT** — quanto mais tempo sem decisão, mais dados
  acumulados sem destino claro (932 linhas e a crescer ~11/dia), e mais difícil fica justificar
  continuar a gastar engenharia nisto sem um objetivo de negócio.
- **Risco de fadiga de auditoria, mas com um contraponto novo e positivo:** depois de 7 ciclos
  seguidos com a mesma recomendação de limpeza ignorada, esta é a primeira auditoria em que a
  maior parte dessa lista foi mesmo resolvida (frontends, resíduos no root) — o padrão "auditoria
  escreve, ninguém decide" não é absoluto, só lento.

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
  dia, para nunca se poder fazer batota usando informação que só existiu depois (ex.: usar hoje um
  dado que só foi publicado a semana passada, fingindo que já o sabias ontem).
- **Alfa vs Beta** — alfa é ganho por competência real (bater o mercado); beta é ganho só porque
  o mercado em geral subiu (qualquer pessoa ganharia igual, sem skill nenhum).
- **Deflated Sharpe Ratio** — teste estatístico que pune ter experimentado muitas estratégias
  diferentes antes de escolher a "melhor" — corrige o facto de que, testando 56 ideias ao calhas,
  é natural que uma ou duas pareçam boas só por sorte.
- **Profit Factor (PF)** — soma de todos os ganhos a dividir pela soma de todas as perdas (em
  valor absoluto); PF>1 significa "ganhou mais do que perdeu no total", PF<1 significa o
  contrário.
- **13F** — relatório trimestral obrigatório nos EUA em que grandes fundos de investimento (como
  o de Warren Buffett) revelam o que compraram/venderam.
- **ETF (Exchange-Traded Fund)** — um "fundo" que se compra e vende na bolsa como se fosse uma
  ação normal, mas que por dentro é uma cesta de várias ações (ex.: a NANC segue as compras de
  políticos dos EUA, tal como o ib_bot tentava copiar).
- **Celery beat/worker** — um "relógio" (beat) que dispara tarefas periódicas dentro da própria
  aplicação, e um "trabalhador" (worker) que as executa de facto.
- **systemd timer / service** — o despertador do próprio computador Linux (timer) que dispara uma
  tarefa a uma hora marcada (o service), fora de qualquer aplicação.
- **Docker / container / imagem** — uma "caixa" isolada onde um programa corre com tudo o que
  precisa; a "imagem" é o molde de onde a caixa é criada, e pode ficar guardada em disco mesmo
  depois da caixa parar — é isso que se está a acumular (61 GB).
- **Rate limiter (SlowAPI)** — um guarda que limita quantos pedidos por minuto uma rota web pode
  receber, para proteger o servidor; aqui foi a causa escondida do bug de 45 dias, porque uma
  tarefa automática chamou a rota sem passar pela "porta de entrada" normal (o pedido HTTP) que
  esse guarda espera encontrar.
- **Conductor / Domain Manager (gestor de domínio) / plano / fase** — o sistema que o José usa
  para gerir trabalho longo de agentes de IA; um "gestor de domínio" (ex.: `trading_manager`) pode
  ter autoridade sobre vários repositórios ao mesmo tempo, incluindo o `ib_bot`.
- **TOTP (Time-based One-Time Password)** — o código de 6 dígitos que muda a cada 30 segundos,
  usado como segundo fator de autenticação (2FA).
- **E-mini (ES/NQ)** — contratos "futuros" (promessas de compra/venda a um preço fixado, para uma
  data futura) sobre os índices bolsistas S&P 500 (ES) e Nasdaq-100 (NQ).
- **Sharpe Ratio / Sortino Ratio / Drawdown / VaR (Value at Risk)** — medidas de "ganho por
  risco", "ganho por risco de perdas (só contando quedas)", "maior queda pico-a-vale", e "pior
  perda esperada num dia mau", respetivamente.
- **runjob** — a ferramenta do José para correr trabalho pesado (CPU/RAM/disco) dentro de limites
  seguros, para não travar a máquina inteira.
- **worktree (do git)** — uma segunda cópia de trabalho do mesmo repositório, útil para um agente
  trabalhar numa alteração sem interferir com o código principal; deve ser removida depois de
  fundida com o principal.
