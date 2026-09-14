# Audit Profundo — IB Bot (2026-09-14, ART / meio da manhã em Portugal WEST)

> Sessão de auditoria: `/home/servidor/agent-workspaces/mega-audit-2026-09-14`.
> Todos os comandos abaixo foram corridos NESTA sessão (ground truth re-verificado, não copiado
> de memória nem de auditorias anteriores). Esta é a **7ª auditoria profunda** deste projeto
> (depois de 2026-07-12, 2026-07-20, 2026-08-10, 2026-08-24, 2026-08-31 e 2026-09-07) — sempre no
> mesmo repositório (`/home/servidor/Desktop/cursor-projects/ib_bot`, HEAD de hoje `a23331a`,
> sempre no mesmo formato, para dar continuidade histórica.

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
   desde julho de 2026 por decisão do José ("dormência seletiva"). Continua a receber trabalho de
   engenharia defensiva de um gestor de domínio mais lato (`trading_manager`/`ib_bot` no
   Conductor) — ver secção (b) e (c) — mesmo sem nenhuma ordem real ter sido colocada.
3. **Arquivo "ponto-no-tempo" (PIT — point-in-time)** — desde 13 de julho de 2026, o robô tira uma
   "fotografia" todos os dias de 11 fontes de dados públicas e guarda-a para sempre, mesmo que a
   fonte original mude depois.
4. **"Paper trading" (fingir que compra/vende ações com dinheiro que não existe, para testar o
   sistema sem risco)** — corre todos os dias sozinho, mas **continua silenciosamente quebrado**,
   sem interrupção, desde pelo menos 14 de agosto de 2026 (achado CRÍTICO da auditoria anterior,
   **re-confirmado hoje, dia a dia, até ontem inclusive**).

O projeto está marcado como **PAUSED (pausado)** no sistema de gestão de projetos do José (o
Conductor), o que significa "não se decide o próximo grande passo de negócio" — não significa
"desligado". Há vários processos automáticos a correr todos os dias sozinhos (ver secção (c)), e
há também um **novo plano de engenharia em fila** (criado há só 1 dia, 13 de setembro) para
reforçar ainda mais a segurança do caminho de execução real, mesmo com o robô parado — ver
timeline.

## (b) Evolução até hoje (timeline, com datas verificadas)

Fonte: `git log` completo do repositório (`git log --oneline | wc -l` = **258 commits**, corrido
nesta sessão) + as 6 auditorias anteriores no mesmo diretório + `psql conductor` (planos e fases)
+ memórias em `/home/servidor/.claude/projects/-home-servidor/memory/`.

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repositório. |
| 2026-01 a 2026-04 | Construção inicial: motor de backtest, catálogo de estratégias, execução IB, frontend. |
| 2026-05 | Auditoria de investibilidade v1→v4 (Deflated Sharpe Ratio): v4 (AUTORITATIVA) reprova as 56 estratégias. Recomendação: vender o motor de dados, não o "alfa". |
| 2026-05-09 | **Última linha em `paper_trades` até hoje** — confirmado nesta sessão de novo (`max(timestamp)=2026-05-09`, inalterado há mais de 4 meses). |
| 2026-05-23/26 | Estudos irmãos PEAD e earnings-vol (0006) rejeitados/morreram (mesmo padrão: beta, não alfa; profit factor <1). Início dos `paper_snapshots` das duas contas de paper trading. |
| 2026-07-12/13 | Decisão de negócio do José: **dormência seletiva**. Gateway IB desligado. Arranca o arquivo diário PIT. |
| 2026-08-05 a 08-20 | Plano Conductor `04bf8af8` "Alt-data PIT archive hardening" fecha `done`: backup noturno offsite, separação de dono na DB, guarda de pré-voo de ordens. |
| 2026-08-17, 08-24, 08-31 | Três auditorias seguidas recomendam o **mesmo plano de 5 passos de limpeza/decisão**; nenhum é executado. |
| **2026-08-14 a hoje (contínuo)** | **A tarefa diária `paper_rebalance_daily_task` falha silenciosamente todos os dias, para as duas contas (1 e 2), com o mesmo erro `tuple index out of range`.** Descoberto na auditoria de 2026-09-07; **confirmado de novo nesta sessão, sem uma única exceção, até 2026-09-13 inclusive** (ver secção (c)). |
| 2026-08-30 | Novo plano Conductor `8e1fa5aa` — "Trading roadmap top-3 (proposta `8f2e018b`): kill authority, observable placement, stale broker state", dono `trading_manager`, alcança o `ib_bot` via `system/execution/order_preflight.py` e o caminho de colocação de ordens do backend. |
| 2026-09-02 12:30–16:19 WEST | Fase `p3-stale-broker-state` executada e revista 3 vezes por um revisor independente (ECC) antes de passar (commit final `cace802`, "atomic commit gate"). Bug real de segurança (TOCTOU — Time-Of-Check to Time-Of-Use — entre verificar cancelamento e colocar ordem) corrigido, sem que nenhuma ordem real fosse colocada em qualquer momento (gateway desligado o tempo todo). Plano `8e1fa5aa` fecha `done` a 2026-09-02 16:52. |
| 2026-09-07 | Auditoria anterior. Descobre o Finding CRÍTICO #0 (paper rebalance quebrado) e reclassifica a curva de equity da conta 2 como "carteira congelada reavaliada a preço de mercado", não "resultado de paper trading ativo". |
| **2026-09-13 00:12 WEST** | **NOVO plano Conductor `4c48535c`** — "IB bot money-path hardening — approved roadmap top-3 (proposal `49b22160`)", dono `ib_bot`, status **`draft`** (ainda não aprovado/a executar). 3 fases prontas (`p1` estado do Gateway/dormência, `p2` validação de respostas malformadas da API IB, `p3` fechar bypass do guard de ordens no cliente web), todas `run_mode=codex_goal`, deadline 2026-10-12. **Nenhum ficheiro de teste ou recibo destas 3 fases existe ainda no repositório** (confirmado com `find` nesta sessão) — é trabalho em fila, não trabalho já feito. |
| 2026-08-31 a 2026-09-14 (últimas 2 semanas) | Repositório recebeu **15 commits desde 2026-09-07**, todos 100% automáticos (7× backup noturno PIT, 7× recibo QA diária, 1× o próprio commit da auditoria de 09-07). Arquivo PIT cresceu de 625→**701 linhas** (57→**64 dias distintos**). Nenhum commit de engenharia manual nesta janela — o hardening `p3-stale-broker-state` já estava fechado antes de 09-07. |
| **2026-09-14 (hoje)** | Este audit. Confirma que o bug crítico do paper rebalance **continua ativo sem interrupção** (12 dias a mais de falha desde a última auditoria) e que **nenhum dos 5 passos de limpeza recomendados 4x foi executado** — é a 5ª auditoria seguida a repetir os mesmos dois achados críticos. |

## (c) Estado concreto HOJE (verificado nesta sessão)

### Repositórios
- `/home/servidor/Desktop/cursor-projects/ib_bot` — repo git ativo, branch `main`, HEAD `a23331a`
  (2026-09-14 04:33 WEST), **258 commits** (`git log --oneline | wc -l`), working tree limpo
  (`git status --porcelain` vazio). **15 commits desde a auditoria de 09-07**, todos automáticos
  (backup/QA do arquivo PIT).
- `/home/servidor/Desktop/cursor-projects/ib_bot-v2` — segundo worktree do mesmo repositório
  (`git worktree list` confirma), branch `frontend-v2`, HEAD `25f7a6a` (mais antigo, não avança
  automaticamente — normal para um worktree secundário), serve `ib-bot-v2-frontend.service`.
- `ib_bot-altdata-wt` (citado no brief) **continua a não existir** — confirmado de novo.

### Serviços systemd (comando: `systemctl status <unit>` corrido nesta sessão)
| Unit | Estado | Nota |
|---|---|---|
| `ibgateway.service` | `inactive (dead)`, `disabled` | Parado desde 2026-08-27 20:54 WEST, inalterado. |
| `xvfb-ibgw.service` | `inactive (dead)`, `disabled` | Idem. |
| `ib-bot-v2-frontend.service` | `active (running)` há 1 mês 4 dias | Porta 3001. |
| `ib-altdata-qa.timer`/`.service` | `active (waiting)`, último disparo 13-09 08:01, sucesso | Próximo: hoje 08:00 WEST. |
| `ib-altdata-backup.timer`/`.service` | `active (waiting)`, último disparo hoje 04:33 WEST, sucesso | Próximo: amanhã 04:34. |
| `ib-backtests.timer`/`.service` | `active (waiting)`, último disparo 13-09 06:17, sucesso | Próximo: 20-09 05:16 WEST. |
| `theta-terminal.service` | `active (running)` | Do projeto Polymarket/trading irmão — não é do ib_bot (confirmado de novo). |

Confirma-se de novo: **3 timers são do ib_bot** (`ib-altdata-qa`, `ib-altdata-backup`,
`ib-backtests`).

### Stack Docker (`docker ps -a --filter name=ib_bot`, `docker system df`)
```
ib_bot-api-1        Up 4 weeks   0.0.0.0:8001->8000/tcp
ib_bot-beat-1       Up 4 weeks
ib_bot-worker-1     Up 4 weeks
ib_bot-db-1         Up 4 weeks   5432/tcp (não exposta ao host)
ib_bot-redis-1      Up 4 weeks
ib_bot-web-1        Up 4 weeks   3000/tcp
ib_bot-nginx-1      Up 4 weeks   0.0.0.0:8090->80/tcp
ib_bot-web-lint-1   Exited (0) 2 months ago
```
`curl localhost:8001/health` → `200`. `curl localhost:8090` → `200`. `curl localhost:3001` →
`307`. **Continuam dois frontends vivos ao mesmo tempo** — 5ª auditoria seguida a repetir o mesmo
achado.

`docker system df`: **32,37 GB de imagens, 100% reclamáveis** (21 imagens) — praticamente idêntico
ao medido em 08-24, 08-31 e 09-07 (crescimento de 0,01 GB, ruído de build). Ninguém correu
`docker image prune`.

### Tarefas internas do bot (celery beat/worker — `docker logs ib_bot-worker-1`, últimos 7 dias completos, 2026-09-07 a 2026-09-13)
- `reconcile_stuck_runs_task`/`reconcile_stuck_executions_task` — housekeeping interno, sem
  efeito externo, sem erros novos.
- `altdata_snapshot_daily_task` (06:00 UTC diário) — **saudável**, `overall_status: ok` em todos os
  dias verificados.
- **`paper_rebalance_daily_task` (15:00 UTC/WEST diário) — CONTINUA QUEBRADA, sem interrupção.**
  Confirmado, dia a dia, do log completo `docker logs ib_bot-worker-1 --since 168h`: em
  **2026-09-07, 08, 09, 10, 11, 12 e 13**, às 15:00:00 WEST, a tarefa "sucede" ao nível do sistema
  de tarefas (`Task ... succeeded in 0.1-0.5s: None`), mas dentro dela, para **cada uma das duas
  contas** (`account=1 portfolio=7095ae3e...`, `account=2 portfolio=d2e87bea...`), o rebalanceamento
  real levanta a exceção `tuple index out of range`, é apanhada, e só regista um
  `logger.warning(...)` — nunca aparece como falha no systemd nem dispara nenhum alerta. Isto soma
  **12 dias adicionais de falha desde a auditoria de 09-07** (que já tinha confirmado 08-14 a
  09-06), sem uma única exceção nova nesta janela — o bug não se auto-resolveu e ninguém o corrigiu.
- `docker logs ib_bot-worker-1` também mostra erros de ruído esperados: tickers deslistados na
  Yahoo Finance (`$SQ`, `$STKL`, `$SATS`, `$BK`, etc. — "possibly delisted; no timezone/price data
  found") durante o backtest semanal de 07-09 — comportamento conhecido, sem impacto no resultado
  (a lógica de delisted-ticker-map já trata destes casos), não é um achado novo.

### Base de dados (Postgres dentro de `ib_bot-db-1`, `docker exec ib_bot-db-1 psql -U ibbot -d ibbot`)
- `ib_orders` = **0**, `ib_trades` = **0**, `live_execution_requests` = **0** — confirma **zero
  ordens reais desde sempre**, inalterado.
- `altdata_snapshots` = **701 linhas** (era 625 em 09-07), `count(distinct captured_at::date)` =
  **64 dias** (era 57) — cresceu 76 linhas / 7 dias, ritmo de ~11/dia mantido, consistente.
- `paper_snapshots`: 2 contas, **112 registos cada** (era 105 em 09-07), 2026-05-26 a
  **2026-09-13**.
  - Conta 1 (`account_id=1`): sempre `equity=$100.000` nas 112 linhas — confirmado de novo, ainda
    sem qualquer movimento (consistente com o rebalanceamento também quebrado para esta conta).
  - Conta 2 (`account_id=2`): equity diária de **US$177.973,30** (26 mai, 1º dia completo) a
    **US$182.596,32** (13 set, último registo) — ganho acumulado de **+US$4.623,02 (+2,60%)** em
    111 dias-calendário distintos. **Desde a auditoria anterior (06-09: US$186.203,09), a conta
    CAIU US$3.606,77 (-1,94%) na última semana** — a curva não está apenas a subir; teve uma
    correção clara nos últimos 4 dias (04-09 pico de US$186.473,90 → 13-09 US$182.596,32). Ver
    métricas completas (Sharpe 0,74 anual, Sortino 0,68, drawdown máximo US$9.577,09 / 5,24%) em
    `metrics.json`. **Continua confirmado:** `paper_trades` (conta 2) mantém **138 registos,
    inalterado desde `max(timestamp)=2026-05-09`** — nenhum trade novo há mais de 4 meses. A curva
    de equity é, portanto, só a reavaliação a preço de mercado de uma carteira comprada em maio e
    nunca mais mexida — não é o resultado de nenhuma estratégia sendo testada ativamente. A queda
    da última semana é apenas o mercado a corrigir sobre essas mesmas posições paradas.
- `paper_trades` (conta 2) = 138 registos, inalterado desde maio (confirmado de novo, 5ª vez).

### Conta real na Interactive Brokers (via MCP `get_account_summary`/`get_account_positions`, consultado nesta sessão)
- **Valor líquido: EUR 27.875,16** (era EUR 27.612,35 em 09-07 — mais uma subida, +EUR 262,81).
- **As mesmas três posições da auditoria anterior, inalteradas em quantidade:**
  1. 70 ações **BRK B** (Berkshire Hathaway), valor USD 35.798,70, ganho não realizado
     +USD 1.431,55.
  2. 300 ações de **"8473 @TSEJ"** (SBI Holdings, bolsa de Tóquio), valor JPY 991.980,03, ganho
     não realizado +JPY 8.094,03.
  3. 60 unidades de **"BCHN @LSEETF"** (ETF cotado em Londres), valor USD 11.674,80, ganho não
     realizado +USD 271,50.
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
| `8e1fa5aa` — Trading roadmap top-3 (proposta `8f2e018b`) | `trading_manager` | `done` (fechado 2026-09-02) | Sem alterações desde 09-07. |
| **`4c48535c` — IB bot money-path hardening (proposta `49b22160`)** | **`ib_bot`** | **`draft`** | **NOVO desde 09-07.** Criado 2026-09-13 00:12 WEST. 3 fases (`p1` fecha lacunas de estado/saúde/dormência do Gateway, `p2` valida respostas malformadas da API IB antes de execução, `p3` fecha um possível bypass do guard de ordens no cliente web), todas `run_mode=codex_goal`, deadline 2026-10-12. **Confirmado com `find` nesta sessão: nenhum dos ficheiros de teste ou recibo exigidos pelas 3 fases existe ainda** — é trabalho em fila (draft, não aprovado/executing), não trabalho já feito. Continuação natural do plano `8e1fa5aa` (mesmo padrão de hardening de money-path). |

**Recomendação para a próxima auditoria (mantida de 09-07):** continuar a procurar planos por
título/conteúdo, não só por `slug='ib_bot'`, e verificar sempre se um plano em `draft`/`ready`
já produziu ficheiros no disco antes de assumir que "está em curso" — neste caso não estava.

## (d) Findings, ordenados por gravidade

### CRÍTICO

**#0 — CONTINUA. O motor de paper trading está quebrado há pelo menos 31 dias corridos, sem
interrupção, e sem correção desde que foi descoberto (09-07).** A tarefa diária
`paper_rebalance_daily_task` corre às 15:00 WEST todos os dias e "sucede" ao nível do sistema de
tarefas (Celery), mas dentro dela, para as DUAS contas de paper trading e para as 9 estratégias
configuradas, o rebalanceamento real levanta sempre `tuple index out of range` e é engolido como
`WARNING`. Confirmado em `docker logs ib_bot-worker-1`: **todos os dias sem exceção, de
2026-08-14 a 2026-09-13** (7 dias novos confirmados nesta sessão desde a auditoria anterior, que
já tinha confirmado 2026-08-14 a 2026-09-06). Consequência prática inalterada: a conta paper 1
está congelada em exatamente $100.000 há 112 medições seguidas; a conta paper 2 não recebe um
trade novo desde **2026-05-09**. **Novidade desta auditoria: a conta 2 caiu 1,94% na última
semana** (US$186.203,09 em 06-09 → US$182.596,32 em 13-09) — prova adicional de que a curva
reflete só o mercado, não uma estratégia (uma estratégia ativa poderia ter reagido; uma carteira
parada só sobe e desce com o preço). Evidência: `docker logs ib_bot-worker-1 --since 168h | grep
paper_rebalance_daily` (comando corrido nesta sessão); código em `backend/app/worker/tasks.py`
(apanha a exceção e só regista aviso); `backend/app/api/routes/paper.py` (chama
`RebalancingBacktestEngine._generate_rebalance_events`, raiz provável do erro).

**#1 — CINCO auditorias seguidas (08-17, 08-24, 08-31, 09-07, e agora de novo hoje) recomendaram
o MESMO plano de limpeza de 5 passos; nenhum foi executado.** Verificado byte-a-byte nesta sessão:
os dois frontends continuam ambos vivos, os 32,37 GB de imagens Docker reclamáveis são
praticamente o número exato de 3 auditorias atrás, os resíduos na raiz do repositório (`$LOG`,
`alembic_validation.db`, os 3 `backtest_results_*.json`, `docker-compose.prod.yml.bak.*`) têm as
mesmas datas de modificação de janeiro/maio, e a decisão de negócio sobre o destino do arquivo PIT
continua por tomar (agora há **mais de 2 meses** desde julho). O padrão "auditoria escreve,
ninguém lê/decide os 5 passos de limpeza" continua intacto pela 5ª vez.

### ALTO

**#2 — Dois frontends web vivos ao mesmo tempo, sem necessidade clara (repetido pela 5ª vez).**
`curl localhost:3001` → `307` (`ib-bot-v2-frontend.service`). `curl localhost:8090` → `200` (stack
Docker completa própria).

**#3 — Nenhuma das 56 estratégias de investimento tem edge robusto, confirmado repetidamente
(inalterado desde maio).** Deflated Sharpe Ratio reprova as 56.

**#4 — Engenharia continua a ser gasta todos os dias num arquivo de dados sem uso decidido.**
`altdata_snapshots` cresceu de 625→701 linhas (76 em 7 dias); a decisão de negócio continua em
HOLD desde julho — agora **mais de 9 semanas** sem decisão.

### MÉDIO

**#5 — `theta-terminal.service` sempre ligado** — não é problema do ib_bot per se (é do projeto
irmão de trading), inalterado.

**#6 — 32,37 GB de imagens Docker reclamáveis, 21 imagens (praticamente inalterado há 4 auditorias
seguidas).**

**#7 — Container `ib_bot-web-lint-1` parado há ~2 meses, nunca limpo.**

**#8 — `paper_rebalance_daily_task` não emite *traceback* completo no erro, só a mensagem da
exceção** — continua a impedir uma correção rápida sem reproduzir localmente.

### BAIXO

**#9 — Resíduos na raiz do repositório, inalterados desde 08-17 (5ª auditoria seguida a encontrar
os mesmos ficheiros).** `$LOG` (765 KB), `alembic_validation.db` (86 KB), 3× `backtest_results_*.json`
(3,3 MB), `docker-compose.prod.yml.bak.1778273314`.

**#10 — Conta paper 1 (id=1) sempre em $100.000, sem documentação de propósito** — explicado em
parte pelo Finding #0 (rebalanceamento também quebrado para esta conta).

### INFORMATIVO / POSITIVO

**#A — Um bug real de segurança no caminho de colocação de ordens foi encontrado e corrigido em
setembro (herdado, sem alterações desde 09-07) — continua a ser o exemplo de disciplina correta de
money-path.** Ver timeline 2026-09-02.

**#B — NOVO. Existe um plano de continuação para reforçar ainda mais a segurança do caminho de
execução real (`4c48535c`, draft, criado 13-09-2026), mesmo com o robô parado.** Cobre três
lacunas concretas: estado/saúde/dormência do Gateway partilhados por todos os pontos de entrada de
execução, validação de respostas malformadas da API IB antes de qualquer execução, e um possível
bypass do guard de ordens no caminho do cliente web. Ainda **não está aprovado nem tem nenhum
ficheiro produzido** — é trabalho em fila, não trabalho em curso. Isto é uma boa prática (a frota
continua a fechar lacunas de segurança preventivamente mesmo com o projeto pausado), mas também um
lembrete de que "existir um plano" não é o mesmo que "estar a acontecer" — confirmar sempre no
disco antes de reportar progresso.

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Investigar e corrigir o Finding CRÍTICO #0 (paper rebalance quebrado)** — continua a ser o
   achado mais importante: cada dia que passa sem corrigir é mais um dia de dados de "performance"
   inúteis/enganosos acumulados. Baixo risco (não mexe em dinheiro real), alto valor informativo.
2. **Resolver o Finding CRÍTICO #1 outra vez — decisão explícita do José, não outro plano de
   limpeza idêntico.** Já são 5 auditorias a pedir isto. Ver plano de fixes passo 0.
3. Consolidar os dois frontends (#2) — baixo risco, reversível.
4. Limpar disco Docker (#6) — grátis, sem risco, recupera >30 GB.
5. Arrumar resíduos no root (#9) — cosmético mas rápido.
6. Decidir se/quando aprovar o plano `4c48535c` (hardening adicional de money-path) — não é
   urgente enquanto o gateway estiver desligado, mas não custa nada aprová-lo já que está pronto.
7. Findings #5, #7, #10 — baixa prioridade, documentar e não agir sem necessidade.

## (f) Riscos se nada for feito

- **Nenhum risco de perda de dinheiro real hoje.** Trading ao vivo está travado em 4 camadas
  (`ibgateway` desligado, `LIVE_AUTO_REBALANCE` off, guarda de pré-voo de ordens, e o *gate*
  atómico de colocação corrigido em 09-02). `ib_orders=0`/`ib_trades=0` confirmado de novo.
- **Risco confirmado e a agravar: decisões futuras baseadas na curva de equity de paper trading
  continuam erradas.** Quanto mais tempo o bug #0 fica por corrigir, mais dias de dados
  "congelados mas parecendo ativos" se acumulam — hoje já são 31 dias confirmados de falha
  contínua, e a curva já mostrou tanto subidas como uma queda de quase 2% na última semana, sem
  que nenhuma decisão de estratégia esteja realmente a ser tomada por trás.
- **Risco continuado de desperdício de atenção, disco e confiança no processo de auditoria** —
  mesmo achado de limpeza pela 5ª vez seguida.
- **Risco de "fadiga de auditoria"**: se os relatórios continuarem a ser ignorados, o valor do
  próximo ciclo cai para perto de zero. Recomenda-se que a resposta ao passo 0 do plano de fixes
  inclua também uma decisão sobre a cadência deste próprio ciclo de auditoria.

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
