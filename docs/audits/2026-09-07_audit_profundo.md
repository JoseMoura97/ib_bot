# Audit Profundo — IB Bot (2026-09-07, ART / manhã em Portugal WEST)

> Sessão de auditoria: `/home/servidor/agent-workspaces/mega-audit-2026-09-07`.
> Todos os comandos abaixo foram corridos NESTA sessão (ground truth re-verificado, não copiado
> de memória nem de auditorias anteriores). Esta é a **5ª auditoria profunda** deste projeto
> (depois de 2026-07-12, 2026-07-20/2026-08-10, 2026-08-17, 2026-08-24 e 2026-08-31) — sempre no
> mesmo repositório (`/home/servidor/Desktop/cursor-projects/ib_bot`, commit `483a8ef`, HEAD de
> hoje), sempre no mesmo formato.

## (a) O que é este projeto (para um miúdo de 12 anos)

O **IB Bot** é um robô de computador que devia comprar e vender ações sozinho, usando a conta de
trading do José na **Interactive Brokers (IB — a corretora, a empresa que executa as ordens de
compra/venda na bolsa)**. A ideia era copiar o que "gente esperta" faz — políticos dos EUA quando
compram ações, fundos famosos (como o de Warren Buffett) quando publicam os seus relatórios
trimestrais, gestores que apostam contra empresas (Michael Burry) — e ver se copiar essas jogadas
dá dinheiro.

O robô testou **56 ideias diferentes** ("estratégias") em dados históricos com um motor de
**backtest** (simular "se eu tivesse seguido esta regra no passado, ganhava ou perdia?"). Tem
quatro peças vivas hoje:
1. **Motor de backtest** — testa ideias no passado, de graça, sem risco. Corre sozinho todas as
   semanas (domingo de madrugada).
2. **Motor de execução real** — a peça que manda ordens verdadeiras para a IB. Está **desligada**
   desde julho de 2026 por decisão do José ("dormência seletiva"), mas continua a receber
   trabalho de engenharia defensivo (ver secção (b), commits de 2 de setembro).
3. **Arquivo "ponto-no-tempo" (PIT — point-in-time)** — desde 13 de julho de 2026, o robô tira uma
   "fotografia" todos os dias de 11 fontes de dados públicas e guarda-a para sempre, mesmo que a
   fonte original mude depois.
4. **"Paper trading" (fingir que compra/vende ações com dinheiro que não existe, para testar o
   sistema sem risco)** — corre todos os dias sozinho, mas **está silenciosamente quebrado desde
   pelo menos 14 de agosto** (ver Finding CRÍTICO #0, novo nesta auditoria): a tarefa diária
   "sucede" no sistema de tarefas, mas a lógica interna de rebalanceamento falha sempre com o
   mesmo erro, para as duas contas de paper, todos os dias.

O projeto está marcado como **PAUSED (pausado)** no sistema de gestão de projetos do José (o
Conductor), o que significa "não se decide o próximo grande passo de negócio" — não significa
"desligado". Há vários processos automáticos a correr todos os dias sozinhos (ver secção (c)), e
há também trabalho de engenharia ATIVO a corrigir um bug de segurança no caminho de execução real
mesmo com o robô parado (ver timeline) — isto é uma boa notícia: alguém (a frota de agentes de IA
do José, através do gestor de domínio "trading") está a manter o código seguro para o caso de o
robô voltar a ser ligado um dia, mesmo sem decisão de negócio tomada.

## (b) Evolução até hoje (timeline, com datas verificadas)

Fonte: `git log` completo do repositório (`git log --oneline | wc -l` = **243 commits**, corrido
nesta sessão) + as 5 auditorias anteriores no mesmo diretório + `psql conductor` (planos e fases)
+ memórias em `/home/servidor/.claude/projects/-home-servidor/memory/`.

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repositório. |
| 2026-01 a 2026-04 | Construção inicial: motor de backtest, catálogo de estratégias, execução IB, frontend. |
| 2026-05 | Auditoria de investibilidade v1→v4 (memória `project_ib_bot_audit.md`): v4 (AUTORITATIVA, Deflated Sharpe Ratio) reprova as 56 estratégias. Recomendação: vender o motor de dados, não o "alfa". |
| 2026-05-09 | **Última linha em `paper_trades` até hoje** — confirmado nesta sessão (`max(timestamp)=2026-05-09`, inalterado desde a 1ª auditoria a medir isto). |
| 2026-05-23/26 | Estudo irmão PEAD rejeitado (mesmo padrão: beta, não alfa). Início dos `paper_snapshots` das duas contas de paper trading. |
| 2026-07-12/13 | Decisão de negócio do José: **dormência seletiva**. Gateway IB desligado. Arranca o arquivo diário PIT. |
| 2026-07-16 | Estudo irmão earnings-vol (0006) morto: profit factor <1 em 36 eventos forward. |
| 2026-08-05 a 08-20 | Plano Conductor `04bf8af8` "Alt-data PIT archive hardening" fecha `done`: backup noturno offsite, separação de dono na DB, guarda de pré-voo de ordens. |
| 2026-08-17, 08-24, 08-31 | Três auditorias seguidas recomendam o **mesmo plano de 5 passos de limpeza/decisão**; nenhum é executado (achado CRÍTICO repetido). |
| **2026-08-30 14:00** | **Novo plano Conductor `8e1fa5aa` — "Trading roadmap top-3 (proposta `8f2e018b`): kill authority, observable placement, stale broker state"**, dono **`trading_manager`** (não `ib_bot` — é um gestor de domínio mais lato que cobre vários repos de trading do José). Alcança o `ib_bot` porque a fase `p3-stale-broker-state` aponta diretamente para `system/execution/order_preflight.py` e para o caminho de colocação de ordens do backend. Confirmado por `psql conductor`. |
| 2026-09-02 12:30–16:19 WEST | **Fase `p3-stale-broker-state` executada e revista 3 vezes por um revisor independente (ECC) antes de passar.** Ronda 1 (commit `fd45fea`): reprovada — uma tarefa já enfileirada sobrevivia ao timeout do chamador e colocava a ordem na mesma depois. Ronda 2 (`8124f0b`): reprovada — corrida clássica TOCTOU (Time-Of-Check to Time-Of-Use) entre verificar cancelamento e chamar `placeOrder`. Ronda 3 (`cace802`, "atomic commit gate"): **aprovada** — abandono e colocação passaram a disputar o mesmo *lock*, testado nos dois lados da corrida (9/9 testes focados, 60/60 na regressão). Ver Finding INFORMATIVO/POSITIVO #A abaixo — é um bug real de segurança encontrado e corrigido, sem que nenhuma ordem real tenha sido colocada em qualquer momento (gateway desligado o tempo todo, 0 sockets IB abertos, confirmado no recibo `backend/tests/receipts/stale_broker_state_8f2e018b.md` e nos ganchos do plano). |
| 2026-09-02 | Correção sistémica em Conductor (`reference_conductor_ecc_cross_repo_review_20260902.md`): o roteamento do revisor independente (ECC) passou a resolver corretamente checkouts Git fora da raiz do projeto executor — relevante porque este plano é dono `ib_bot` mas evidência vivia em `trading`. |
| 2026-09-01 | Plano antigo `e36e04ec` (pós-triagem 07-12) passa de `paused` para `status=superseded` na DB do Conductor — housekeeping, sem mudança de conteúdo (`updated_at` 2026-09-01 19:48). |
| 2026-08-31 a 2026-09-07 (últimos 7 dias) | Repositório recebeu **20 commits**: 6 de engenharia real (a hardening `p3-stale-broker-state` acima) + 14 100% automáticos (7× backup noturno PIT, 7× recibo QA diária). Arquivo PIT cresceu de 548→**625 linhas** (50→**57 dias distintos**). |
| **08-14 a 09-07 (contínuo, achado NOVO desta sessão)** | **A tarefa diária `paper_rebalance_daily_task` falha silenciosamente todos os dias, para as duas contas (1 e 2), com o mesmo erro `tuple index out of range`.** Confirmado em `docker logs ib_bot-worker-1`, primeira ocorrência visível no buffer de logs a 2026-08-14 15:00 WEST (o buffer não vai mais atrás — pode ser mais antigo), última hoje 2026-09-06 15:00 WEST (ainda não disparou hoje à hora da auditoria). As 4 auditorias anteriores não detetaram isto (a de 08-31 escreveu literalmente "Não há tarefa `paper_rebalance_daily_task` visível nos últimos logs de 24-48h analisados" — estava enganada, a tarefa corre e falha todos os dias às 15:00 WEST, mas com nível `WARNING`, não `ERROR`/`FAILED`, por isso não aparecia em greps por falhas óbvias). Ver Finding CRÍTICO #0. |
| **2026-09-07 (hoje)** | Este audit — a curva de equity da conta paper 2, que auditorias anteriores tratavam como "resultado de um paper trading ativo", é na realidade **uma carteira congelada desde 9 de maio a ser só reavaliada a preços de mercado** — nunca mais rebalanceada de facto. |

## (c) Estado concreto HOJE (verificado nesta sessão)

### Repositórios
- `/home/servidor/Desktop/cursor-projects/ib_bot` — repo git ativo, branch `main`, HEAD
  `483a8ef` (2026-09-07 04:33 WEST), **243 commits** (`git log --oneline | wc -l`), working tree
  limpo (`git status --porcelain` vazio). **20 commits desde a auditoria de 08-31**: 6 reais
  (hardening de segurança na colocação de ordens) + 14 automáticos (backup/QA do arquivo PIT).
- `/home/servidor/Desktop/cursor-projects/ib_bot-v2` — segundo worktree do mesmo repositório
  (`git worktree list` confirma), branch `frontend-v2`, serve `ib-bot-v2-frontend.service`.
  Tem alterações locais não commitadas em `.conductor/context.md` e `frontend/next-env.d.ts` —
  ficheiros de metadados/tipos, não código de negócio; fora do escopo de escrita deste audit
  (regra READ-ONLY — não tocado).
- `ib_bot-altdata-wt` (citado no brief) **continua a não existir** — confirmado de novo.
- Branches de quarentena visíveis (`git branch -a`): `quarantine/20260902T*-phase-p1-kill-authority-*`,
  `...-phase-p2-placement-observability-*`, `...-phase-p3-stale-broker-state-*` — resíduo normal
  do processo de revisão independente (ECC) do Conductor para o plano `8e1fa5aa`, já fundido em
  `main` por fast-forward.

### Serviços systemd (comando: `systemctl status <unit>` corrido nesta sessão)
| Unit | Estado | Nota |
|---|---|---|
| `ibgateway.service` | `inactive (dead)`, `disabled` | Parado desde 2026-08-27 20:54 WEST (teste manual autorizado, já documentado em 08-31; sem alterações desde então). |
| `xvfb-ibgw.service` | `inactive (dead)`, `disabled` | Idem. |
| `ib-bot-v2-frontend.service` | `active (running)` há 3 semanas 6 dias | Porta 3001, fala com API v1 real (:8001). `curl` → `307`. |
| `ib-altdata-qa.timer`/`.service` | `active (waiting)`, último disparo 06-09 08:00, sucesso | QA diária do arquivo PIT. Próximo: hoje 08:00 WEST. |
| `ib-altdata-backup.timer`/`.service` | `active (waiting)`, último disparo hoje 04:33 WEST, sucesso | Backup offsite noturno. Próximo: amanhã 04:30. |
| `ib-backtests.timer`/`.service` | `active (waiting)`, último disparo 06-09 05:16 WEST, sucesso | Backtest semanal completo. Próximo: 13-09 05:16 WEST. |
| `theta-terminal.service` | `active (running)` | Do projeto Polymarket — não é do ib_bot (confirmado de novo). |
| `execution-metrics.timer`, `cost-recalibration.timer`, `historical-backfill.timer`, `paper-ironfly.timer`, `theta-learned.timer` | `active (waiting)` | **Confirmado de novo, nenhum é do ib_bot** — Polymarket e projeto irmão `trading`. |
| `lifeos-ib-refresh.timer`/`.service` | `active (waiting)`, dispara de 2h em 2h | Do projeto `lifeos`, só lê a conta IB pessoal do José, não escreve em nada do ib_bot. |

Confirma-se de novo: **3 timers são do ib_bot** (`ib-altdata-qa`, `ib-altdata-backup`,
`ib-backtests`).

### Stack Docker (`docker ps -a --filter name=ib_bot`, `docker system df`)
```
ib_bot-api-1        Up 3 weeks   0.0.0.0:8001->8000/tcp
ib_bot-beat-1       Up 3 weeks
ib_bot-worker-1     Up 3 weeks
ib_bot-db-1         Up 3 weeks   5432/tcp (não exposta ao host)
ib_bot-redis-1      Up 3 weeks
ib_bot-web-1        Up 3 weeks   3000/tcp
ib_bot-nginx-1      Up 3 weeks   0.0.0.0:8090->80/tcp
ib_bot-web-lint-1   Exited (0) 2 months ago
```
`curl localhost:8001/health` → `200`. `curl localhost:8090` → `200`. `curl localhost:3001` →
`307`. **Continuam dois frontends vivos ao mesmo tempo** — 4ª auditoria seguida a repetir o
mesmo achado.

`docker system df`: **32,36 GB de imagens, 100% reclamáveis** (21 imagens) — número
byte-a-byte idêntico ao medido em 08-24 e 08-31. Ninguém correu `docker image prune`.

### Tarefas internas do bot (celery beat/worker — `docker logs ib_bot-beat-1`/`-worker-1`, últimas 48h e histórico disponível)
- `reconcile_stuck_runs_task`/`reconcile_stuck_executions_task` — housekeeping interno de 5/10 em
  10 min, sem efeito externo, sem erros.
- `altdata_snapshot_daily_task` (06:00 UTC diário) — **saudável**: log de hoje (07-09) e de ontem
  confirmam `overall_status: ok`, `successful_sources: 11/11`, `orders_placed: 0`,
  `ib_requests: 0`. `quiver_congress_trades` continua excluído (precisa de acesso pago).
- `shadow_preview_task` (06:00 UTC diário) — pré-visualização "sombra", não executa nada real.
- **`paper_rebalance_daily_task` (15:00 UTC/WEST diário) — QUEBRADA, achado NOVO desta auditoria.**
  A tarefa Celery em si "sucede" (`Task ... succeeded in 0.1-0.3s: None`), mas dentro dela, para
  **cada uma das duas contas** (`account=1 portfolio=7095ae3e...`, `account=2
  portfolio=d2e87bea...`), o rebalanceamento real levanta a exceção
  `tuple index out of range`, é apanhada, e só regista um `logger.warning(...)` — nunca aparece
  como falha no systemd nem dispara nenhum alerta. Confirmado todos os dias desde 2026-08-14 (o
  mais antigo visível no buffer de logs do container) até 2026-09-06 inclusive, sem uma única
  exceção. Raiz provável identificada por leitura do código nesta sessão:
  `backend/app/api/routes/paper.py:paper_rebalance_execute` chama
  `paper_rebalance_preview`, que (com `QUIVER_API_KEY` configurada — confirmado
  `settings.quiver_api_key == True` dentro do container) usa
  `RebalancingBacktestEngine._generate_rebalance_events()` (repo root
  `rebalancing_backtest_engine.py`) para gerar os pesos-alvo de **cada uma das 9 estratégias**
  usadas pelas duas contas (conta 1: Ackman/Burry/Howard Marks; conta 2: Congress
  Buys/Meuser/Pelosi/Lobbying/Sector-Weighted-DC-Insider/Insider-Purchases — confirmado via
  `portfolio_strategies`). Falha de forma **idêntica para as 9**, o que aponta para um bug
  sistémico no motor (não um problema de uma fonte de dados só), mas o código de produção só
  regista a mensagem da exceção, não o *traceback* completo — não dá para apontar a linha exata
  sem reproduzir localmente (ver plano de fixes, passo 1).

### Base de dados (Postgres dentro de `ib_bot-db-1`, `docker exec ib_bot-db-1 psql -U ibbot -d ibbot`)
- `ib_orders` = **0**, `ib_trades` = **0**, `live_execution_requests` = **0** — confirma **zero
  ordens reais desde sempre**, inalterado.
- `altdata_snapshots` = **625 linhas** (era 548 em 08-31), `count(distinct captured_at::date)` =
  **57 dias** (era 50) — cresceu 77 linhas / 7 dias, ritmo de ~11/dia mantido.
- `paper_snapshots`: 2 contas, **105 registos cada** (era 98 em 08-31), 2026-05-26 a **2026-09-06**.
  - Conta 1 (`account_id=1`): sempre `cash=equity=$100.000` nas 105 linhas — confirmado de novo,
    continua sem qualquer movimento (consistente com o achado novo: o rebalanceamento desta conta
    também falha todos os dias).
  - Conta 2 (`account_id=2`): equity **$177.973,30** (26 mai, 1º registo) → **$186.203,09** (6
    set, último registo disponível). Ganho acumulado ao longo de 104 dias-calendário distintos:
    **+US$8.229,79 (+4,62%)**. Ver métricas completas (Sharpe, Sortino, drawdown, VaR) em
    `metrics.json`. **Importante:** confirmado nesta sessão que `paper_trades` (conta 2) continua
    com **138 registos, inalterado desde `max(timestamp)=2026-05-09`** — ou seja, **nenhum trade
    novo entrou nesta conta desde 9 de maio**. Combinado com o achado do rebalanceamento
    quebrado, isto significa que a subida de 4,62% em ~3,5 meses **não é o resultado de uma
    estratégia ativa a ser testada** — é a reavaliação a preço de mercado de uma carteira
    **congelada** desde maio. As auditorias anteriores (07-12 a 08-31) descreveram esta curva como
    "resultado do paper trading" sem verificar se o motor de rebalanceamento estava de facto a
    correr — esta sessão corrige essa lacuna.
- `paper_trades` (conta 2) = 138 registos, inalterado desde maio (confirmado de novo).

### Conta real na Interactive Brokers (via MCP `get_account_summary`/`get_account_positions`, consultado nesta sessão)
- **Valor líquido: EUR 27.612,35** (era EUR 27.248,34 em 08-31 — mais uma subida).
- **Três posições agora, não uma:**
  1. 70 ações **BRK B** (Berkshire Hathaway), valor USD 35.422,10, ganho não realizado
     +USD 1.054,95 — a posição já conhecida das auditorias anteriores.
  2. **300 ações de "8473 @TSEJ"** (SBI Holdings, bolsa de Tóquio), valor JPY 1.010.669,97, ganho
     não realizado +JPY 26.783,97 — **posição NOVA, não vista nas auditorias anteriores.**
  3. **60 unidades de "BCHN @LSEETF"** (ETF cotado em Londres), valor USD 11.686,80, ganho não
     realizado +USD 283,50 — **posição NOVA, não vista nas auditorias anteriores.**
- Estas são **posições pessoais do José, geridas manualmente por ele** (fora do robô) —
  confirmado porque `ib_orders=0`/`ib_trades=0` na base de dados do bot continua exatamente
  igual a antes de estas posições aparecerem. **O robô não tocou na conta** — o José esteve
  simplesmente a negociar por conta própria (provavelmente via TWS/app móvel) desde a última
  auditoria. Registado aqui só para manter o estado da conta atualizado; não é um achado do bot.

### Planos do Conductor (comando: `psql -U servidor -d conductor`)
| Plano | Dono (slug) | Status | Nota |
|---|---|---|---|
| `04bf8af8` — Alt-data PIT archive hardening | `ib_bot` | `done` | Sem alterações desde 08-20. |
| `e36e04ec` — pós-triagem 2026-07-12 | `ib_bot` | `superseded` (era `paused` em 08-31) | Mudança de status só (housekeeping), conteúdo (HOLD do B2B) inalterado. |
| `3702771c` — ib_bot → Alt-Data Product | `ib_bot` | `superseded` | Sem alterações. |
| **`8e1fa5aa` — Trading roadmap top-3 (proposta `8f2e018b`)** | **`trading_manager`** | **`done`** (fechado 2026-09-02 16:52) | **NOVO desde 08-31.** Corrigiu um bug real de segurança no caminho de colocação de ordens do `ib_bot` (fases `p1-kill-authority`, `p2-placement-observability`, `p3-stale-broker-state`), com revisão independente (ECC) obrigatória — ver timeline. Não é dono `ib_bot`, por isso `psql ... WHERE slug='ib_bot'` sozinho não o mostra; é preciso procurar por título/conteúdo. |

Nenhum plano *dono do slug `ib_bot`* foi criado desde a última auditoria — mas isso não significa
que nada aconteceu: o gestor de domínio `trading_manager` (mais lato, cobre vários repositórios
de trading do José) executou trabalho real neste mesmo repositório. **Recomendação para a próxima
auditoria:** procurar sempre por planos com o caminho do repositório no título/fases, não só por
`slug='ib_bot'`, para não perder trabalho como este.

## (d) Findings, ordenados por gravidade

### CRÍTICO

**#0 — NOVO. O motor de paper trading está quebrado há pelo menos 24 dias, silenciosamente, e as
4 auditorias anteriores não detetaram.** A tarefa diária `paper_rebalance_daily_task` corre às
15:00 WEST todos os dias e "sucede" ao nível do sistema de tarefas (Celery), mas dentro dela, para
as DUAS contas de paper trading e para as 9 estratégias configuradas, o rebalanceamento real
levanta sempre `tuple index out of range` e é engolido como `WARNING`. Confirmado em
`docker logs ib_bot-worker-1`: **todos os dias sem exceção de 2026-08-14 a 2026-09-06** (o buffer
de logs não vai mais atrás; pode ser mais antigo). Consequência prática: a conta paper 1 está
congelada em exatamente $100.000 há 105 medições seguidas; a conta paper 2 não recebe um trade
novo desde **2026-05-09** (confirmado `max(paper_trades.timestamp)`) — a subida de +4,62% que
parece "resultado do paper trading" na base de dados é na realidade só reavaliação a preço de
mercado de uma carteira parada há 4 meses. **Isto muda a interpretação de todos os números de
"performance" de paper trading citados em auditorias anteriores** — não são resultado de uma
estratégia sendo testada ativamente, são o preço de mercado de posições antigas a subir ou descer.
Evidência: `docker logs ib_bot-worker-1 --since 200h | grep paper_rebalance_daily` (comando corrido
nesta sessão, ver secção (c)); código em
`backend/app/worker/tasks.py:559-570` (apanha a exceção e só regista aviso);
`backend/app/api/routes/paper.py:paper_rebalance_execute`/`paper_rebalance_preview` (chama
`RebalancingBacktestEngine._generate_rebalance_events`, raiz provável do erro, sem *traceback*
completo nos logs de produção).

**#1 — QUATRO auditorias seguidas (08-17, 08-24, 08-31, e agora confirma-se de novo hoje)
recomendaram o MESMO plano de limpeza de 5 passos; nenhum foi executado.** Verificado
byte-a-byte nesta sessão: os dois frontends continuam ambos vivos, os 32,36 GB de imagens Docker
reclamáveis são o número EXATO de 08-24/08-31, os resíduos na raiz do repositório (`$LOG`,
`alembic_validation.db`, os 3 `backtest_results_*.json`, `docker-compose.prod.yml.bak.*`) têm as
mesmas datas de modificação de janeiro/maio, e a decisão de negócio sobre o destino do arquivo PIT
continua por tomar. **Diferença notável desta vez:** houve trabalho de engenharia real no
repositório desde a última auditoria (o hardening `p3-stale-broker-state`) — mas foi trabalho de
um gestor de domínio diferente (`trading_manager`) a reagir a um item do SEU roadmap, não alguém a
agir sobre as recomendações deste ciclo de auditoria do `ib_bot`. O padrão "auditoria escreve,
ninguém lê/decide os 5 passos de limpeza" continua intacto.

### ALTO

**#2 — Dois frontends web vivos ao mesmo tempo, sem necessidade clara (repetido pela 4ª vez).**
`curl localhost:3001` → `307` (`ib-bot-v2-frontend.service`, fala com a API v1 real :8001).
`curl localhost:8090` → `200` (stack Docker completa própria — API/worker/beat/db/redis/nginx).

**#3 — Nenhuma das 56 estratégias de investimento tem edge robusto, confirmado repetidamente
(inalterado desde maio).** Deflated Sharpe Ratio reprova as 56. Estudos irmãos earnings-vol
(0006) e PEAD morreram por razões independentes convergentes (beta, não alfa).

**#4 — Engenharia continua a ser gasta todos os dias num arquivo de dados sem uso decidido.**
`altdata_snapshots` cresceu de 548→625 linhas (77 em 7 dias) e vai continuar a crescer sozinho;
a decisão de negócio (vender B2B? mais estratégias? arquivar?) continua em HOLD desde julho —
agora **quase 9 semanas** sem decisão.

### MÉDIO

**#5 — `theta-terminal.service` sempre ligado** — não é problema do ib_bot per se (é do
Polymarket), mas o ib_bot não precisa dele; só 2 scripts do estudo Iron Wing já morto o referenciam.

**#6 — 32,36 GB de imagens Docker reclamáveis, 21 imagens (inalterado byte-a-byte há 3
auditorias seguidas).**

**#7 — Container `ib_bot-web-lint-1` parado há ~2 meses, nunca limpo.**

**#8 — `paper_rebalance_daily_task` não emite *traceback* completo no erro, só a mensagem da
exceção.** Consequência direta: o Finding #0 ficou escondido durante semanas porque ninguém
consegue apontar a linha exata da falha sem reproduzir localmente. Corrigir isto ao mesmo tempo
que o Finding #0 (ver plano de fixes).

### BAIXO

**#9 — Resíduos na raiz do repositório, inalterados desde 08-17 (4ª auditoria seguida a
encontrá-los).** `$LOG` (765 KB), `alembic_validation.db` (86 KB), 3× `backtest_results_*.json`
(3,3 MB), `docker-compose.prod.yml.bak.1778273314`.

**#10 — Conta paper 1 (id=1) sempre em $100.000, sem documentação de propósito** — agora
explicada em parte pelo Finding #0 (rebalanceamento também quebrado para esta conta), mas o
propósito original da conta ("porque existe uma conta de controlo parada?") continua sem resposta
documentada.

### INFORMATIVO / POSITIVO

**#A — Um bug real de segurança no caminho de colocação de ordens foi encontrado e corrigido,
com disciplina exemplar, sem que nenhum risco real fosse corrido.** `backend/app/services/ib_worker.py`
tinha uma corrida (*race condition*) TOCTOU: se o chamador de `_IbWorker.call(...)` expirasse por
timeout, a tarefa já enfileirada podia continuar a correr depois e chamar `ib.placeOrder(...)`
mesmo assim — ou seja, uma ordem podia ser colocada DEPOIS do sistema já ter decidido "isto
falhou, não confiar". Isto foi apanhado por um revisor independente (ECC) em 3 rondas sucessivas
(cada ronda achou um defeito real e diferente: closure sobrevivia ao timeout → corrida
TOCTOU → finalmente um *gate* atómico com *lock* partilhado), e só passou na 3ª ronda com prova
testada dos dois lados da corrida (9/9 testes focados, 60/60 na regressão). Em nenhum momento
houve socket aberto para o IB Gateway, ordem colocada, ou serviço reiniciado — o gateway esteve
sempre desligado. **Isto é o comportamento correto de disciplina de money-path**, mesmo com o
projeto pausado — o código de execução real continua a ser mantido seguro para o dia em que
(se) for reativado.

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Investigar e corrigir o Finding CRÍTICO #0 (paper rebalance quebrado)** — é o achado mais
   importante desta auditoria porque muda a interpretação de todos os números de "performance"
   já reportados. Baixo risco (não mexe em dinheiro real), alto valor informativo.
2. **Resolver o Finding CRÍTICO #1 outra vez — decisão explícita do José, não outro plano de
   limpeza idêntico.** Ver plano de fixes passo 0.
3. Consolidar os dois frontends (#2) — baixo risco, reversível.
4. Limpar disco Docker (#6) — grátis, sem risco, recupera >30 GB.
5. Arrumar resíduos no root (#9) — cosmético mas rápido.
6. Findings #5, #7, #10 — baixa prioridade, documentar e não agir sem necessidade.

## (f) Riscos se nada for feito

- **Nenhum risco de perda de dinheiro real hoje.** Trading ao vivo está travado em 4 camadas
  (`ibgateway` desligado, `LIVE_AUTO_REBALANCE` off, guarda de pré-voo de ordens, e agora também
  o *gate* atómico de colocação corrigido em 09-02). `ib_orders=0`/`ib_trades=0` confirmado de
  novo nesta sessão.
- **Risco real e NOVO: decisões futuras baseadas na curva de equity de paper trading estarão
  erradas** se alguém (José ou um agente) usar os números da conta 2 (+4,62% em 104 dias) como
  prova de que "a estratégia Congress/Insider funciona em paper" — na realidade é só o mercado a
  subir sobre posições congeladas desde maio. Quanto mais tempo o bug #0 ficar por corrigir, mais
  esta ilusão se reforça a cada snapshot diário.
- **Risco continuado de desperdício de atenção, disco e confiança no processo de auditoria** —
  mesmo achado de limpeza pela 4ª vez seguida.
- **Risco de "fadiga de auditoria"**: se os relatórios continuarem a ser ignorados, o valor do
  próximo ciclo cai para perto de zero.

## (g) Glossário

- **API (Application Programming Interface)** — a "porta" por onde dois programas trocam
  informação.
- **MCP (Model Context Protocol)** — ligação que permite a um assistente de IA falar diretamente
  com um serviço externo; aqui usada para ler saldo/posições reais da conta IB.
- **Backtest** — simular "se eu tivesse seguido esta estratégia no passado, ganhava ou perdia
  dinheiro?", sem risco real.
- **Paper trading** — fingir que compras e vendes ações com dinheiro que não existe.
- **PIT (point-in-time)** — guardar uma "fotografia" dos dados exatamente como estavam num certo
  dia, para nunca se poder fazer batota usando informação que só existiu depois.
- **Alfa vs Beta** — alfa é ganho por competência real; beta é ganho só porque o mercado subiu.
- **Deflated Sharpe Ratio** — teste estatístico que pune ter experimentado muitas estratégias
  diferentes.
- **TOCTOU (Time-Of-Check to Time-Of-Use)** — um tipo de "corrida" (*race condition*) em que um
  programa verifica uma condição, mas antes de agir sobre ela essa condição já mudou — como
  verificar se uma porta está trancada e, no instante entre olhar e empurrar, alguém a destranca.
- **ECC (aqui: revisor independente do Conductor)** — um segundo agente de IA, separado de quem
  fez o trabalho, que tem de re-verificar de forma independente antes de qualquer fase "difícil"
  (ex.: caminho de dinheiro real) poder ser marcada como concluída.
- **Celery beat/worker** — um "relógio" (beat) que dispara tarefas periódicas dentro da própria
  aplicação, e um "trabalhador" (worker) que as executa.
- **systemd timer** — o despertador do próprio computador Linux que dispara uma tarefa a uma hora
  marcada.
- **Docker / container** — uma "caixa" isolada onde um programa corre com tudo o que precisa.
- **Conductor / Domain Manager (gestor de domínio) / plano / fase** — o sistema que o José usa
  para gerir trabalho longo de agentes de IA; um "gestor de domínio" (ex.: `trading_manager`)
  pode ter autoridade sobre vários repositórios ao mesmo tempo, incluindo o `ib_bot`.
- **13F** — relatório trimestral obrigatório nos EUA em que grandes fundos revelam o que
  compraram/venderam.
- **Sharpe Ratio / Sortino Ratio / Drawdown / VaR** — medidas de "ganho por risco", "ganho por
  risco de perdas", "maior queda pico-a-vale", e "pior perda esperada num dia mau", respetivamente.
