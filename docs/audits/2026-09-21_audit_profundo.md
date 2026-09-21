# Audit Profundo — IB Bot (2026-09-21, ART / meio da manhã em Portugal WEST)

> Sessão de auditoria: `/home/servidor/agent-workspaces/mega-audit-2026-09-21`.
> Todos os comandos abaixo foram corridos NESTA sessão (ground truth re-verificado, não copiado
> de memória nem de auditorias anteriores). Esta é a **9ª auditoria profunda** deste projeto
> (depois de 2026-07-12, 2026-07-20, 2026-08-10, 2026-08-17, 2026-08-24, 2026-08-31, 2026-09-07 e
> 2026-09-14 — contagem confirmada com `ls docs/audits/*.md` nesta sessão), sempre no mesmo
> repositório (`/home/servidor/Desktop/cursor-projects/ib_bot`, HEAD de hoje `3b8ffc4`), sempre no
> mesmo formato, para dar continuidade histórica.
>
> **Nota importante sobre o brief:** o pedido descreve o projeto como "PAUSED — não construir
> consumer app". Isso é verdade ao nível de DECISÃO DE NEGÓCIO (não se decidiu vender/lançar
> nada), mas **é enganoso ler "PAUSED" como "parado"**: esta semana o repositório recebeu **41
> commits** (confirmado com `git log --since="2026-09-14" --oneline | wc -l`), incluindo trabalho
> de engenharia manual real (não só backups automáticos) — ver secção (b).

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
   semanas (domingo de madrugada). **Esta semana quase falhou silenciosamente** (ver achado novo
   abaixo) — foi corrigido no próprio dia por outro operador.
2. **Motor de execução real** — a peça que manda ordens verdadeiras para a IB. Está **desligada**
   desde julho de 2026 por decisão do José ("dormência seletiva"). Esta semana **terminou** um
   projeto de 3 fases de reforço de segurança desse motor (mesmo desligado) — ver secção (b).
3. **Arquivo "ponto-no-tempo" (PIT — point-in-time)** — desde 13 de julho de 2026, o robô tira uma
   "fotografia" todos os dias de 11 fontes de dados públicas e guarda-a para sempre, mesmo que a
   fonte original mude depois.
4. **"Paper trading" (fingir que compra/vende ações com dinheiro que não existe, para testar o
   sistema sem risco)** — corre todos os dias sozinho, mas **continua silenciosamente quebrado**,
   sem interrupção, desde pelo menos 14 de agosto de 2026 (achado CRÍTICO, agora **38 dias
   corridos confirmados**, ver secção (d)).

O projeto está marcado como **PAUSED (pausado)** no sistema de gestão de projetos do José (o
Conductor), o que significa "não se decide o próximo grande passo de negócio" — não significa
"desligado". Há vários processos automáticos a correr todos os dias sozinhos (ver secção (c)).

## (b) Evolução até hoje (timeline, com datas verificadas)

Fonte: `git log --all` completo do repositório + as 8 auditorias anteriores no mesmo diretório +
`psql -U servidor -d conductor` (planos e conhecimento de fases) + memórias em
`/home/servidor/.claude/projects/-home-servidor/memory/`.

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repositório. |
| 2026-01 a 2026-04 | Construção inicial: motor de backtest, catálogo de estratégias, execução IB, frontend. |
| 2026-05 | Auditoria de investibilidade v1→v4 (Deflated Sharpe Ratio): v4 (AUTORITATIVA) reprova as 56 estratégias. Recomendação: vender o motor de dados, não o "alfa". |
| 2026-05-09 | **Última linha em `paper_trades` até hoje** — confirmado nesta sessão de novo (`max(timestamp)=2026-05-09`, inalterado há mais de 4 meses). |
| 2026-05-23/26 | Estudos irmãos PEAD e earnings-vol (0006) rejeitados/morreram (mesmo padrão: beta, não alfa; profit factor <1). Início dos `paper_snapshots` das duas contas de paper trading. |
| 2026-07-12/13 | Decisão de negócio do José: **dormência seletiva**. Gateway IB desligado. Arranca o arquivo diário PIT. |
| 2026-08-05 a 08-20 | Plano Conductor `04bf8af8` "Alt-data PIT archive hardening" fecha `done`: backup noturno offsite, separação de dono na DB, guarda de pré-voo de ordens. |
| 2026-08-14 a 2026-09-20 (contínuo) | **A tarefa diária `paper_rebalance_daily_task` falha silenciosamente todos os dias, para as duas contas (1 e 2), com o mesmo erro `tuple index out of range`.** Descoberta na auditoria de 2026-09-07; **confirmada de novo nesta sessão, dia a dia, sem uma única exceção, até 2026-09-20 inclusive** — **38 dias corridos**. |
| 2026-08-30 – 2026-09-02 | Plano Conductor `8e1fa5aa` "Trading roadmap top-3", dono `trading_manager`, fecha `done` a 2026-09-02 16:52 (bug real de segurança TOCTOU no caminho de colocação de ordens, corrigido sem que nenhuma ordem real fosse colocada). |
| 2026-09-13 00:12 WEST | Plano Conductor `4c48535c` — "IB bot money-path hardening — approved roadmap top-3", dono `ib_bot`, criado em `draft`. 3 fases: `p1` (estado/saúde/dormência do Gateway), `p2` (validar respostas malformadas da API IB), `p3` (fechar bypass do guard de ordens no cliente web). |
| **2026-09-14** | Auditoria anterior (7ª/8ª da série). Confirma bug #0 continua e que o plano `4c48535c` ainda estava em `draft`, sem ficheiros produzidos. |
| **2026-09-15** | **Todas as 3 fases do plano `4c48535c` foram executadas e fecharam `done` (23:47 WEST), com revisão independente (ECC) — 7 tentativas de revisão em p1, 5 em p2, 3 em p3, todas eventualmente aprovadas.** Commits confirmados: `bd3d056` "fail closed on gateway state and dormancy", `6e93a90` "guard Client Portal order submissions", `3579a86` "reject non-finite (NaN/Inf) values in every IB response parser", `f71a4f5` "recheck Gateway predicate immediately before the legacy executor's placeOrder". Suite completa integrada em `main` (commit `e3e7422`): **308 passed / 17 skipped** (recibo `9b7102a`). Nenhuma ordem real foi colocada em qualquer momento (gateway continuou desligado o tempo todo). |
| 2026-09-15 a 09-20 | 6 dias de backup noturno PIT + recibo QA diária, automáticos, sem incidente. |
| **2026-09-20 05:16–07:16 WEST** | **NOVO achado: o backtest semanal (`ib-backtests.service`) correu pela primeira vez sob um limite de 2h e foi morto a 80,7% da regeneração dos gráficos** (`systemd[1]: ib-backtests.service: start operation timed out. Terminating`). O alerta de `OnFailure` (`ib_backtests_alert.sh`) **também falhou** (contrato de CLI do `conductor jobs add` tinha mudado e faltavam `--dedup-key`/`--recovery-message`) — **ninguém foi acordado pela falha**. Descoberto e corrigido no mesmo dia por outro operador (commits `40cbb23` fix do alerta, `c228fd3` + `c360884` mudança do timeout de 2h fixo para `runjob` contido com janela de 3h e `TimeoutStartSec` mais generoso). Re-corrido manualmente às 13:23–14:13 WEST com sucesso: `.cache/plot_data.json` e `.cache/latest_backtest_results.json` regenerados (56 estratégias, `generated_at: 2026-09-20T14:13:02`). |
| **2026-09-21 (hoje)** | Este audit. Confirma que o bug crítico do paper rebalance **continua ativo sem interrupção** (38 dias), que **o plano de hardening de money-path `4c48535c` fechou por completo esta semana** (positivo), que **o backtest semanal quase falhou silenciosamente mas foi corrigido no mesmo dia** (achado novo, já resolvido), e que **nenhum dos 5 passos de limpeza recomendados 5x seguidas foi executado** — é a 6ª auditoria seguida a repetir o mesmo achado de limpeza, e ainda não existe nenhuma resposta registada em memória à pergunta explícita do "Passo 0" do plano de fixes de 09-14.

## (c) Estado concreto HOJE (verificado nesta sessão)

### Repositórios
- `/home/servidor/Desktop/cursor-projects/ib_bot` — repo git ativo, branch `main`, HEAD `3b8ffc4`
  (2026-09-21 04:35 WEST), working tree limpo (`git status --porcelain` vazio). **41 commits desde
  a auditoria de 09-14** (`git log --since="2026-09-14" --oneline | wc -l`) — a maioria automática
  (backup/QA do arquivo PIT), mas com trabalho de engenharia manual real: fecho das 3 fases de
  `4c48535c` (09-15) e o fix do backtest semanal/alerta (09-20).
- `/home/servidor/Desktop/cursor-projects/ib_bot-v2` — segundo worktree do mesmo repositório
  (`git worktree list` confirma), branch `frontend-v2`, HEAD `25f7a6a` (mais antigo, não avança
  automaticamente — normal para um worktree secundário), serve `ib-bot-v2-frontend.service`.
- `ib_bot-altdata-wt` (citado no brief) **continua a não existir** — confirmado de novo.
- **NOVO achado de disco:** `.worktree-quarantine/` dentro do repo tem **865 MB** em 2 diretórios
  (`20260915T201254...-phase-p3-ee99-...`, `20260915T204341...-phase-p2-43e6-...`) — cópias
  completas dos worktrees usados para as fases `p2`/`p3` do plano `4c48535c`, já fundidas em
  `main` desde 09-15 e nunca limpas. Mesmo padrão dos resíduos de raiz (achado #9), só que maior
  em volume.

### Serviços systemd (comando: `systemctl status <unit>` corrido nesta sessão)
| Unit | Estado | Nota |
|---|---|---|
| `ibgateway.service` | `inactive (dead)`, `disabled` | Parado desde 2026-08-27 20:54 WEST, inalterado. |
| `xvfb-ibgw.service` | `inactive (dead)`, `disabled` | Idem. |
| `ib-bot-v2-frontend.service` | `active (running)` há 1 mês 11 dias | Porta 3001. |
| `ib-altdata-qa.timer`/`.service` | `active (waiting)`, último disparo hoje 08:00 WEST, sucesso | Próximo: amanhã 08:00. |
| `ib-altdata-backup.timer`/`.service` | `active (waiting)`, último disparo hoje 04:34 WEST, sucesso | Próximo: amanhã 04:31. |
| `ib-backtests.timer`/`.service` | `active (waiting)`, último disparo 20-09 (com incidente e recuperação, ver timeline), sucesso final | Próximo: 27-09 05:15 WEST. |
| `theta-terminal.service` + 5 timers (`theta-learned`, `paper-ironfly`, `historical-backfill`, `execution-metrics`, `cost-recalibration`) | Todos `active` | **Confirmado de novo com `systemctl cat` nesta sessão: NENHUM pertence ao ib_bot.** `WorkingDirectory`/`ExecStart` apontam todos para `/home/servidor/Desktop/cursor-projects/polytrader-bot-master` ou `/home/servidor/Desktop/cursor-projects/trading` (o bot Polymarket irmão) — o brief listava-os como "confirmar quais pertencem ao ib_bot", e a resposta re-verificada é: nenhum. |
| `lifeos-ib-refresh.timer`/`.service` | `active`, dispara às 05:15 WEST | Também não é do ib_bot — é do LifeOS (`/home/servidor/Desktop/cursor-projects/lifeos`), usa o MCP da IB só para atualizar um saldo pessoal, não mexe no bot. |

Confirma-se de novo: **3 timers são do ib_bot** (`ib-altdata-qa`, `ib-altdata-backup`,
`ib-backtests`) — nenhum outro do brief pertence a este projeto.

### Stack Docker (`docker ps -a --filter name=ib_bot`, `docker system df`)
```
ib_bot-api-1        Up 5 weeks   0.0.0.0:8001->8000/tcp
ib_bot-beat-1       Up 5 weeks
ib_bot-worker-1     Up 5 weeks
ib_bot-db-1         Up 5 weeks   5432/tcp (não exposta ao host)
ib_bot-redis-1      Up 5 weeks
ib_bot-web-1        Up 5 weeks   3000/tcp
ib_bot-nginx-1      Up 5 weeks   0.0.0.0:8090->80/tcp
```
`curl localhost:8001/health` → `200`. `curl localhost:8090` → `200`. `curl localhost:3001` →
`307`. **Continuam dois frontends vivos ao mesmo tempo** — 6ª auditoria seguida a repetir o mesmo
achado. **Positivo:** o container fantasma `ib_bot-web-lint-1` (parado há ~2 meses, achado #7 das
auditorias anteriores) **já não aparece em `docker ps -a`** — foi removido nalgum momento desde
09-14, sem que nenhum plano formal o tenha registado; achado #7 fecha-se sozinho.

`docker system df`: **31,51 GB de imagens, 100% reclamáveis** (20 imagens) — praticamente igual a
08-24/08-31/09-07/09-14 (variação de ruído normal de build, não de acumulação nova). Ninguém
correu `docker image prune`.

### Tarefas internas do bot (celery beat/worker — `docker logs ib_bot-worker-1`, últimos 8 dias completos, 2026-09-13 a 2026-09-20)
- `reconcile_stuck_runs_task`/`reconcile_stuck_executions_task` — housekeeping interno, sem
  efeito externo, sem erros novos.
- `altdata_snapshot_daily_task` (06:00 UTC diário) — **saudável**, `overall_status: ok` em todos os
  dias verificados.
- **`paper_rebalance_daily_task` (15:00 WEST diário) — CONTINUA QUEBRADA, sem interrupção.**
  Confirmado, dia a dia, do log completo `docker logs ib_bot-worker-1 --since 192h`: em
  **2026-09-13 a 2026-09-20** (8 dias, todos verificados nesta sessão), às 15:00:00 WEST, a tarefa
  "sucede" ao nível do sistema de tarefas (Celery), mas dentro dela, para **cada uma das duas
  contas** (`account=1 portfolio=7095ae3e...`, `account=2 portfolio=d2e87bea...`), o
  rebalanceamento real levanta a exceção `tuple index out of range`, é apanhada, e só regista um
  `logger.warning(...)` — nunca aparece como falha no systemd nem dispara nenhum alerta. Total
  acumulado: **38 dias corridos de falha, de 2026-08-14 a 2026-09-20, sem uma única exceção.**
  Evidência: `docker logs ib_bot-worker-1 --since 192h | grep paper_rebalance_daily` (comando
  corrido nesta sessão); código em `backend/app/worker/tasks.py` (apanha a exceção e só regista
  aviso); `backend/app/api/routes/paper.py` (chama `RebalancingBacktestEngine._generate_rebalance_events`,
  raiz provável do erro — inalterada, nenhum commit tocou esta função desde a descoberta).
- `paper_rebalance_daily_task` ainda **não** emite traceback completo (achado MÉDIO #8, inalterado).

### Base de dados (Postgres dentro de `ib_bot-db-1`, `docker exec ib_bot-db-1 psql -U ibbot -d ibbot`)
- `ib_orders` = **0**, `ib_trades` = **0**, `live_execution_requests` = **0** — confirma **zero
  ordens reais desde sempre**, inalterado.
- `altdata_snapshots` = **778 linhas** (era 701 em 09-14), `count(distinct captured_at::date)` =
  **71 dias** (era 64) — cresceu 77 linhas / 7 dias, ritmo de ~11/dia mantido, consistente.
- `paper_snapshots`: 2 contas, **119 registos cada** (era 112 em 09-14), 2026-05-26 a
  **2026-09-20**.
  - Conta 1 (`account_id=1`): sempre `equity=$100.000` nas 119 linhas (confirmado com
    `select account_id, count(*), min/max, valor distinto`) — ainda sem qualquer movimento
    (consistente com o rebalanceamento também quebrado para esta conta).
  - Conta 2 (`account_id=2`): equity diária de **US$177.973,30** (26 mai, 1º dia completo) a
    **US$180.706,13** (20 set, último registo) — ganho acumulado de **+US$2.732,83 (+1,54%)** em
    118 dias-calendário distintos. **Desde a auditoria anterior (13-09: US$182.596,32), a conta
    CAIU mais US$1.890,19 (-1,04%) nesta última semana**, embora com um pico intermédio a
    15-09 (US$183.850,56). Métricas completas (Sharpe 0,43 anual, Sortino 0,39, drawdown máximo
    inalterado US$9.577,09 / 5,24% — a pior queda continua a de julho) em `metrics.json`.
    **Continua confirmado:** `paper_trades` (conta 2) mantém **138 registos, inalterado desde
    `max(timestamp)=2026-05-09`** — nenhum trade novo há mais de 4 meses. A curva de equity é,
    portanto, só a reavaliação a preço de mercado de uma carteira comprada em maio e nunca mais
    mexida — não é o resultado de nenhuma estratégia sendo testada ativamente.
- `paper_trades` (conta 2) = 138 registos, inalterado desde maio (confirmado de novo, 6ª vez).

### Resultado do backtest semanal mais recente (`.cache/latest_backtest_results.json`, gerado 2026-09-20 14:13 WEST)
56 estratégias, `price_source=ib` com fallback `cache_hit=1`/`ib_hit=0`/`yfinance_hit=0` (dados
vieram todos de cache, não houve chamada nova à IB nem à Yahoo Finance nesta corrida — sinal
saudável de que o cache PIT está a ser usado como esperado). Exemplo (`Congress Buys`, `core`):
CAGR 13,9%, Sharpe 0,76, max drawdown -24,8%, 3.347 trades simulados no período 2020-04 a
2026-01. **Isto NÃO muda a conclusão da auditoria de investibilidade v4 (Deflated Sharpe Ratio)**
— continua a reprovar as 56 estratégias quando se corrige para "quantas ideias diferentes foram
tentadas" (ver Finding ALTO #3); o resultado bruto de uma estratégia isolada parecer bom não
significa que sobreviva ao ajuste estatístico.

### Conta real na Interactive Brokers (via MCP `get_account_summary`/`get_account_positions`, consultado nesta sessão)
- **Valor líquido: EUR 27.906,49** (era EUR 27.875,16 em 09-14 — mais uma pequena subida, +EUR
  31,33). Conta usa alavancagem (leverage 1,67, cash total negativo -EUR 18.743,79, margem
  inicial usada EUR 17.745,53) — normal para a forma como o José gere esta conta pessoalmente,
  não é uma anomalia do bot.
- **As mesmas três posições das auditorias anteriores, inalteradas em quantidade:**
  1. 70 ações **BRK B** (Berkshire Hathaway), valor USD 35.711,20, ganho não realizado
     +USD 1.344,05.
  2. 300 ações de **"8473 @TSEJ"** (SBI Holdings, bolsa de Tóquio), valor JPY 982.500,00, perda
     não realizada -JPY 1.386,00 (única posição em vermelho esta semana, pequena).
  3. 60 unidades de **"BCHN @LSEETF"** (ETF cotado em Londres), valor USD 11.601,00, ganho não
     realizado +USD 197,70.
- Estas são **posições pessoais do José, geridas manualmente por ele** (fora do robô) — confirmado
  porque `ib_orders=0`/`ib_trades=0` na base de dados do bot continua exatamente igual. **O robô
  não tocou na conta.** Registado aqui só para manter o estado da conta atualizado; não é um
  achado do bot.

### Planos do Conductor (comando: `psql -U servidor -d conductor`)
| Plano | Dono (slug) | Status | Nota |
|---|---|---|---|
| `04bf8af8` — Alt-data PIT archive hardening | `ib_bot` | `done` | Sem alterações. |
| `e36e04ec` — pós-triagem 2026-07-12 | `ib_bot` | `superseded` | Sem alterações. |
| `3702771c` — ib_bot → Alt-Data Product | `ib_bot` | `superseded` | Sem alterações. |
| `8e1fa5aa` — Trading roadmap top-3 | `trading_manager` | `done` (fechado 2026-09-02) | Sem alterações. |
| **`4c48535c` — IB bot money-path hardening** | **`ib_bot`** | **`done` (fechado 2026-09-15 23:47 WEST)** | **MUDOU desde 09-14 (estava `draft`).** As 3 fases (`p1`, `p2`, `p3`) confirmadas `done` na coluna `phases` da tabela `project_plans`; `plan_knowledge` mostra 7+5+3 tentativas de revisão ECC (revisor independente) antes de aprovação e um recibo de suite completa (317 passed em `f71a4f5`). Fecha a série de hardening de money-path que já vinha do plano `8e1fa5aa`. |

Nenhum plano novo aberto para `ib_bot` desde 09-14 — pesquisa por título/conteúdo (`ILIKE '%ib bot%'`,
`%ib_bot%`, `%money-path%`) não devolve nada adicional além da tabela acima.

## (d) Findings, ordenados por gravidade

### CRÍTICO

**#0 — CONTINUA. O motor de paper trading está quebrado há pelo menos 38 dias corridos, sem
interrupção, e sem correção.** A tarefa diária `paper_rebalance_daily_task` corre às 15:00 WEST
todos os dias e "sucede" ao nível do sistema de tarefas (Celery), mas dentro dela, para as DUAS
contas de paper trading e para as 9 estratégias configuradas, o rebalanceamento real levanta
sempre `tuple index out of range` e é engolido como `WARNING`. Confirmado em `docker logs
ib_bot-worker-1`: **todos os dias sem exceção, de 2026-08-14 a 2026-09-20** (8 dias novos
confirmados nesta sessão desde a auditoria anterior). Consequência prática inalterada: a conta
paper 1 está congelada em exatamente $100.000 há 119 medições seguidas; a conta paper 2 não
recebe um trade novo desde **2026-05-09**, e caiu mais 1,04% esta semana (US$182.596,32 →
US$180.706,13), reforçando que a curva é só mercado, não estratégia. Evidência: `docker logs
ib_bot-worker-1 --since 192h | grep paper_rebalance_daily` (comando corrido nesta sessão); código
em `backend/app/worker/tasks.py` e `backend/app/api/routes/paper.py` — **nenhum destes ficheiros
foi tocado em nenhum commit desde a descoberta do bug em 09-07**, apesar de todo o outro trabalho
de engenharia feito nesta janela (money-path hardening, fix do backtest). O bug não é
tecnicamente difícil — está isolado e reproduzível — só não foi priorizado.

**#1 — SEIS auditorias seguidas (08-17, 08-24, 08-31, 09-07, 09-14, e agora de novo hoje)
recomendaram o MESMO plano de limpeza de 5 passos; nenhum foi executado.** Verificado
byte-a-byte nesta sessão: os dois frontends continuam ambos vivos, as 31,51 GB de imagens Docker
reclamáveis são praticamente o número exato de 4 auditorias atrás, os resíduos na raiz do
repositório (`$LOG`, `alembic_validation.db`, os 3 `backtest_results_*.json`,
`docker-compose.prod.yml.bak.*`) têm as mesmas datas de modificação de janeiro/maio, e a decisão
de negócio sobre o destino do arquivo PIT continua por tomar (agora **mais de 2 meses e meio**
desde julho). **Confirmado nesta sessão: não existe nenhuma entrada de memória nova (`find
... -newer 2026-09-14_audit_profundo.md`) que registe uma resposta do José ao "Passo 0" do plano
de fixes de 09-14** — a pergunta foi escrita no ficheiro, mas (tanto quanto se consegue confirmar
por disco/memória) nunca chegou a ser feita de forma síncrona com `request_user_approval`. O
padrão "auditoria escreve, ninguém lê/decide os 5 passos de limpeza" continua intacto pela 6ª vez.

### ALTO

**#2 — Dois frontends web vivos ao mesmo tempo, sem necessidade clara (repetido pela 6ª vez).**
`curl localhost:3001` → `307` (`ib-bot-v2-frontend.service`). `curl localhost:8090` → `200`
(stack Docker completa própria).

**#3 — Nenhuma das 56 estratégias de investimento tem edge robusto, confirmado repetidamente
(inalterado desde maio).** Deflated Sharpe Ratio reprova as 56; o backtest semanal desta semana
(20-09) confirma os mesmos números de sempre, sem mudança de veredicto.

**#4 — Engenharia continua a ser gasta todos os dias num arquivo de dados sem uso decidido.**
`altdata_snapshots` cresceu de 701→778 linhas (77 em 7 dias); a decisão de negócio continua em
HOLD desde julho — agora **mais de 10 semanas** sem decisão.

### MÉDIO

**#5 — `theta-terminal.service` e 5 timers do bot Polymarket irmão sempre ligados** — não são
problema do ib_bot per se, re-confirmado esta semana com `systemctl cat` que nenhum pertence a
este projeto.

**#6 — 31,51 GB de imagens Docker reclamáveis, 20 imagens (praticamente inalterado há 5 auditorias
seguidas).**

**#7 (NOVO) — 865 MB em `.worktree-quarantine/`, resíduo das fases `p2`/`p3` do plano `4c48535c`,
fechadas e fundidas em `main` desde 2026-09-15, nunca limpas.** Mesmo padrão dos resíduos de raiz
(#9 abaixo), desta vez do processo do Conductor, não do repositório em si.

**#8 — `paper_rebalance_daily_task` não emite *traceback* completo no erro, só a mensagem da
exceção** — continua a impedir uma correção rápida sem reproduzir localmente.

**#9 (NOVO, informativo/positivo, mas com lição) — O backtest semanal de 20-09 quase falhou
silenciosamente: o wrapper de alerta `OnFailure` tinha um bug próprio (faltavam flags exigidas por
uma mudança de contrato do CLI `conductor jobs add`) e não avisou ninguém quando o job foi morto a
80,7% por timeout.** Foi corrigido no mesmo dia por outro operador, mas é um lembrete de que
"existe um alerta configurado" não é o mesmo que "o alerta funciona" — vale a pena um teste de
fumo periódico do próprio mecanismo de alerta (matar o job de propósito 1x por trimestre e
confirmar que a notificação chega).

### BAIXO

**#10 — Resíduos na raiz do repositório, inalterados desde 08-17 (6ª auditoria seguida a encontrar
os mesmos ficheiros).** `$LOG` (765 KB), `alembic_validation.db` (86 KB), 3× `backtest_results_*.json`
(3,3 MB), `docker-compose.prod.yml.bak.1778273314`.

**#11 — Conta paper 1 (id=1) sempre em $100.000, sem documentação de propósito** — explicado em
parte pelo Finding #0 (rebalanceamento também quebrado para esta conta).

### INFORMATIVO / POSITIVO

**#A — O plano de hardening de money-path `4c48535c` fechou por completo esta semana (09-15),
com revisão independente rigorosa (ECC — até 7 tentativas por fase) antes de qualquer merge.**
Três lacunas reais fechadas: estado/dormência do Gateway partilhado por todos os pontos de
entrada de execução, validação de respostas malformadas/NaN/Inf da API IB antes de qualquer
execução, e um bypass possível do guard de ordens no caminho do cliente web. Nenhuma ordem real
foi colocada em qualquer momento deste trabalho. Este é o segundo exemplo seguido (depois do
achado #A de 09-14 sobre a fase TOCTOU) de disciplina correta de money-path mesmo com o robô
pausado — a frota continua a fechar lacunas de segurança preventivamente.

**#B — O container fantasma `ib_bot-web-lint-1` (achado MÉDIO das últimas 5 auditorias) já não
existe.** Foi removido nalgum momento entre 09-14 e hoje, sem nenhum plano formal a registá-lo —
achado fecha-se sozinho, sem ação necessária.

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Investigar e corrigir o Finding CRÍTICO #0 (paper rebalance quebrado)** — continua a ser o
   achado mais importante: cada dia que passa sem corrigir é mais um dia de dados de "performance"
   inúteis/enganosos acumulados (já são 38). Baixo risco (não mexe em dinheiro real), alto valor
   informativo.
2. **Resolver o Finding CRÍTICO #1 outra vez — decisão explícita do José, não outro plano de
   limpeza idêntico.** Já são 6 auditorias a pedir isto. Ver plano de fixes passo 0 (agora com
   instrução explícita de usar `request_user_approval` de forma síncrona).
3. Consolidar os dois frontends (#2) — baixo risco, reversível.
4. Limpar `.worktree-quarantine/` (865 MB, #7, novo) — grátis, sem risco, o trabalho já está
   fundido em `main`.
5. Limpar disco Docker (#6) — grátis, sem risco, recupera >30 GB.
6. Arrumar resíduos no root (#10) — cosmético mas rápido.
7. Considerar um teste de fumo trimestral do mecanismo de alerta do backtest semanal (#9) — para
   não repetir o quase-incidente de 20-09.
8. Findings #5, #8, #11 — baixa prioridade, documentar e não agir sem necessidade.

## (f) Riscos se nada for feito

- **Nenhum risco de perda de dinheiro real hoje.** Trading ao vivo está travado em 4+ camadas
  (`ibgateway` desligado, `LIVE_AUTO_REBALANCE` off, guarda de pré-voo de ordens, gate atómico de
  colocação, e agora também o hardening completo do plano `4c48535c`). `ib_orders=0`/`ib_trades=0`
  confirmado de novo.
- **Risco confirmado e a agravar: decisões futuras baseadas na curva de equity de paper trading
  continuam erradas.** Quanto mais tempo o bug #0 fica por corrigir, mais dias de dados
  "congelados mas parecendo ativos" se acumulam — hoje já são 38 dias confirmados de falha
  contínua.
- **Risco continuado de desperdício de atenção, disco e confiança no processo de auditoria** —
  mesmo achado de limpeza pela 6ª vez seguida, e agora com 865 MB adicionais de resíduo do
  Conductor a somar ao problema.
- **Risco de "fadiga de auditoria"** confirmado a crescer: 6 ciclos seguidos com a mesma
  recomendação ignorada é o momento certo para o José decidir explicitamente se quer manter esta
  cadência ou mudar de abordagem (ex.: só auditar quando algo muda de facto, com alertas
  automáticos a substituir a auditoria de rotina para o que já está estável).

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
  programa verifica uma condição, mas antes de agir sobre ela essa condição já mudou.
- **ECC (aqui: revisor independente do Conductor)** — um segundo agente de IA, separado de quem
  fez o trabalho, que tem de re-verificar de forma independente antes de qualquer fase "difícil"
  (ex.: caminho de dinheiro real) poder ser marcada como concluída.
- **Celery beat/worker** — um "relógio" (beat) que dispara tarefas periódicas dentro da própria
  aplicação, e um "trabalhador" (worker) que as executa.
- **systemd timer** — o despertador do próprio computador Linux que dispara uma tarefa a uma hora
  marcada.
- **Docker / container** — uma "caixa" isolada onde um programa corre com tudo o que precisa.
- **Conductor / Domain Manager (gestor de domínio) / plano / fase** — o sistema que o José usa
  para gerir trabalho longo de agentes de IA; um "gestor de domínio" (ex.: `trading_manager`) pode
  ter autoridade sobre vários repositórios ao mesmo tempo, incluindo o `ib_bot`.
- **draft (rascunho, no Conductor)** — um plano criado mas ainda não aprovado nem a executar; não
  confundir com trabalho já em curso.
- **13F** — relatório trimestral obrigatório nos EUA em que grandes fundos revelam o que
  compraram/venderam.
- **Sharpe Ratio / Sortino Ratio / Drawdown / VaR** — medidas de "ganho por risco", "ganho por
  risco de perdas", "maior queda pico-a-vale", e "pior perda esperada num dia mau", respetivamente.
- **runjob** — a ferramenta do José para correr trabalho pesado (CPU/RAM/disco) dentro de limites
  seguros, para não travar a máquina inteira; usada pela primeira vez pelo próprio `ib-backtests`
  esta semana, depois do incidente de timeout de 20-09.
- **worktree (do git)** — uma segunda cópia de trabalho do mesmo repositório, útil para um agente
  trabalhar numa fase sem interferir com o código principal; deve ser removida depois de fundida.
