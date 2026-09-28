# Audit Profundo — IB Bot (2026-09-28, ART / meio da manhã em Portugal WEST)

> Sessão de auditoria: `/home/servidor/agent-workspaces/mega-audit-2026-09-28`.
> Todos os comandos abaixo foram corridos NESTA sessão (ground truth re-verificado, não copiado
> de memória nem de auditorias anteriores). Esta é a **10ª auditoria profunda** deste projeto
> (depois de 2026-07-12, 2026-07-20, 2026-08-10, 2026-08-17, 2026-08-24, 2026-08-31, 2026-09-07,
> 2026-09-14 e 2026-09-21 — confirmado com `ls docs/audits/*.md`), sempre no mesmo repositório
> (`/home/servidor/Desktop/cursor-projects/ib_bot`, HEAD de hoje `6abd2e0`), sempre no mesmo
> formato.
>
> **Nota sobre o brief:** o pedido descreve o projeto como "PAUSED — não construir consumer app".
> Isso continua a ser verdade ao nível de DECISÃO DE NEGÓCIO (nada de novo se lançou para
> clientes), mas volta a ser enganoso ler "PAUSED" como "ninguém mexe": nesta janela (09-21 a
> 09-28) o repositório recebeu **19 commits**, 17 deles automáticos (backup/QA diário do arquivo
> de dados) e **2 de engenharia manual real**, feitos por um operador humano diferente do José
> (Antonio Manuel) — ver secção (b). O ficheiro `ib_bot-altdata-wt` citado no brief **continua a
> não existir**; os dois worktrees reais do repositório são `ib_bot-v2` (frontend) e um terceiro,
> `/home/servidor/ib-altdata-guard-20260924`, criado esta semana para testar em segurança o fix
> do script de backup sem tocar no checkout principal.

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
   desde julho de 2026 por decisão do José ("dormência seletiva"), e continua desligada hoje.
3. **Arquivo "ponto-no-tempo" (PIT — point-in-time)** — desde 13 de julho de 2026, o robô tira uma
   "fotografia" todos os dias de 11 fontes de dados públicas e guarda-a para sempre, mesmo que a
   fonte original mude depois.
4. **"Paper trading" (fingir que compra/vende ações com dinheiro que não existe, para testar o
   sistema sem risco)** — corre todos os dias sozinho, mas **continua silenciosamente quebrado**,
   sem interrupção, desde pelo menos 14 de agosto de 2026 (achado CRÍTICO, agora **45 dias
   corridos confirmados**, ver secção (d)).

O projeto está marcado como **PAUSED (pausado)** no sistema de gestão de projetos do José (o
Conductor), o que significa "não se decide o próximo grande passo de negócio" — não significa
"desligado". Há vários processos automáticos a correr todos os dias sozinhos (ver secção (c)).

**Achado novo desta semana, fora do próprio ib_bot mas que usa o seu código:** um projeto irmão
("laboratório de trading" sob o gestor de domínio `trading_manager`, aprovado explicitamente pelo
José) copiou uma peça pequena e só-de-leitura do motor de execução do ib_bot
(`system/execution/ib_executor.py` + um novo ficheiro `futures_contracts.py`) para consultar dados
de contratos futuros E-mini (ES/NQ) na conta REAL da IB, com login automático e código de
autenticação de dois fatores (TOTP) já existentes — sem nunca ligar o gateway partilhado do
ib_bot nem enviar nenhuma ordem. Isto está fora do âmbito de decisão do ib_bot em si (é gerido por
outro dono, com as suas próprias regras e aprovação explícita do José), mas é relevante para este
audit porque **mexeu no código deste repositório** — ver Finding MÉDIO #5.

## (b) Evolução até hoje (timeline, com datas verificadas)

Fonte: `git log --all` completo do repositório + as 9 auditorias anteriores no mesmo diretório +
`psql -U servidor -d conductor` (planos e conhecimento de fases) + memórias em
`/home/servidor/.claude/projects/-home-servidor/memory/` (grep por `ib_bot`).

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repositório. |
| 2026-01 a 2026-04 | Construção inicial: motor de backtest, catálogo de estratégias, execução IB, frontend. |
| 2026-05 | Auditoria de investibilidade v1→v4 (Deflated Sharpe Ratio): v4 (AUTORITATIVA) reprova as 56 estratégias. |
| 2026-05-09 | **Última linha em `paper_trades` até hoje** — confirmado de novo nesta sessão (`max(timestamp)=2026-05-09`, inalterado há mais de 4 meses e meio). |
| 2026-07-12/13 | Decisão de negócio do José: **dormência seletiva**. Gateway IB desligado. Arranca o arquivo diário PIT. |
| 2026-08-05 a 08-20 | Plano Conductor `04bf8af8` "Alt-data PIT archive hardening" fecha `done`. |
| 2026-08-14 a hoje (contínuo) | **A tarefa diária `paper_rebalance_daily_task` falha silenciosamente todos os dias, para as duas contas (1 e 2), com o mesmo erro `tuple index out of range`.** Descoberta na auditoria de 2026-09-07; **confirmada de novo nesta sessão, dia a dia, sem uma única exceção, até 2026-09-27 inclusive — 45 dias corridos**. |
| 2026-08-30 – 2026-09-15 | Duas rondas de hardening de segurança do caminho de execução real (planos `8e1fa5aa` e `4c48535c`), ambas fechadas `done`, revisão independente rigorosa, sem qualquer ordem real. |
| 2026-09-20 | Backtest semanal quase falha silenciosamente por timeout de 2h; corrigido no mesmo dia (achado já resolvido, ver auditoria de 09-21). |
| 2026-09-21 | Auditoria anterior (9ª). Confirma bug crítico do paper rebalance ativo há 38 dias, confirma limpeza pendente pela 6ª vez, regista 865 MB de resíduo em `.worktree-quarantine/`. |
| **2026-09-24 01:25 WEST** | **Commit `f86848f` "feat(ib): add read-only dated E-mini contract qualification"** — código novo (`system/execution/futures_contracts.py`, método `IBExecutor.qualify_emini_contract`) publicado no `main` do ib_bot, escrito por um operador diferente (Antonio Manuel) a pedido do laboratório de trading `trading_manager` (ver secção (a)). Só consulta metadados de contratos (`reqContractDetails`) numa sessão IB já ligada; não liga o gateway nem envia ordens. 61 testes próprios (`backend/tests/test_futures_contracts.py`), todos com mocks — nenhum teste chamou a IB real a partir deste repositório. |
| **2026-09-24 12:14 WEST** | **Commit `486b6e3` "fix(altdata): refuse backups outside main and require lab worktrees"** — o script de backup noturno do arquivo PIT (`infra/scripts/backup_altdata_snapshots.sh`) ganhou uma guarda `require_main()`: recusa (`exit 2`) publicar se o checkout principal não estiver exatamente na branch `main`, limpo, e sem ninguém ter trocado de branch a meio do dump. Motivo direto: o trabalho do commit anterior (`f86848f`) tinha corrido numa branch de laboratório (`feature/lab-futures-readonly-20260924`) dentro do MESMO checkout que os timers usam para publicar backups — risco real de o backup noturno publicar por engano trabalho de laboratório não revisto para `main`. 90 testes novos (`test_altdata_backup_branch.py`) provam a recusa em 3 cenários (branch errada, HEAD destacada, árvore suja) e o caminho feliz, contra repositórios Git isolados de teste, nunca contra produção. `AGENTS.md` do repositório também foi atualizado com a regra "o checkout principal pertence aos jobs agendados; trabalho de laboratório usa `git worktree add` numa branch separada". |
| 2026-09-24 (mesmo dia) | Worktree `/home/servidor/ib-altdata-guard-20260924` criado (branch `fix/altdata-backup-main-20260924`) para desenvolver e testar o fix acima sem tocar no checkout principal — aplicação correta da nova regra do próprio `AGENTS.md`. |
| 2026-09-21 a 09-28 (contínuo) | 7 dias de backup noturno PIT + recibo QA diária, automáticos, sem incidente novo. `altdata_snapshots` cresceu de 778 → **855 linhas** (77 em 7 dias, ritmo de ~11/dia mantido). |
| **Algures entre 09-21 e hoje** | `.worktree-quarantine/` no repositório principal **foi limpo**: 865 MB → **32 KB** hoje (achado MÉDIO #7 da auditoria anterior fecha-se sozinho, sem registo formal de quem o fez). |
| **2026-09-28 (hoje)** | Este audit. Confirma que o bug crítico do paper rebalance **continua ativo sem interrupção** (45 dias), que os dois frontends duplicados e os 31,5 GB de imagens Docker continuam por resolver (7ª auditoria seguida), que a conta pessoal do José na IB ganhou uma posição nova (GOOG) e perdeu valor esta semana (não relacionado com o bot), e que **continua sem existir nenhuma resposta registada do José** à pergunta explícita de limpeza feita há 6+ semanas. |

## (c) Estado concreto HOJE (verificado nesta sessão)

### Repositórios e worktrees
- `/home/servidor/Desktop/cursor-projects/ib_bot` — repo git ativo, branch `main`, HEAD `6abd2e0`
  (2026-09-28, backup automático de hoje de manhã), `git status --porcelain` vazio.
- `/home/servidor/Desktop/cursor-projects/ib_bot-v2` — segundo worktree do mesmo repositório
  (`git worktree list` confirma), branch `frontend-v2`, HEAD `25f7a6a`, serve
  `ib-bot-v2-frontend.service` (porta 3001). Tinha 2 ficheiros modificados não comitados
  (`.conductor/context.md`, `frontend/next-env.d.ts`) e um diretório `.verify/` novo — resíduo de
  trabalho de outro agente nesse worktree, não relacionado com este audit; não tocado (regra
  read-only).
- `/home/servidor/ib-altdata-guard-20260924` — **novo** (criado 24-09), terceiro worktree, branch
  `fix/altdata-backup-main-20260924`, árvore limpa, mesmo HEAD do `main`. Existe exatamente para
  cumprir a nova regra do `AGENTS.md` (trabalho de laboratório fora do checkout dos timers).
- `ib_bot-altdata-wt` (citado no brief) **continua a não existir** — confirmado de novo.

### Serviços systemd (comando: `systemctl status <unit>` corrido nesta sessão)
| Unit | Estado | Nota |
|---|---|---|
| `ibgateway.service` | `inactive (dead)`, `disabled` | Parado desde 2026-08-27 20:54 WEST, inalterado. Nenhum listener em `:4001`-`:4004` (`ss -tlnp` vazio). |
| `xvfb-ibgw.service` | `inactive (dead)`, `disabled` | Idem. |
| `ib-bot-v2-frontend.service` | `active (running)` há ~1 mês 12 dias | Porta 3001, `npm start`, aponta para o mesmo backend `:8001` (`INTERNAL_API_BASE=http://localhost:8001` em `.env.local`) — confirma que é a MESMA API, só outra interface. |
| `ib-altdata-qa-alert.service` / `ib-backtests-alert.service` | `inactive (dead)` (unidades `OnFailure`, só correm quando algo falha) | Nenhum disparo esta semana — nada falhou. |
| `theta-terminal.service` + 5 timers (`theta-learned`, `paper-ironfly`, `historical-backfill`, `execution-metrics`, `cost-recalibration`) | Todos `active` | **Re-confirmado com `systemctl cat` nesta sessão: NENHUM pertence ao ib_bot.** `WorkingDirectory`/`ExecStart` apontam para `/home/servidor/Desktop/cursor-projects/polytrader-bot-master` (4 deles, descrições dizem literalmente "Polymarket") ou `/home/servidor/Desktop/cursor-projects/trading` (`paper-ironfly`, o bot irmão de opções). O nome "theta" aqui é sobre modelos de probabilidade do Polymarket, não sobre opções financeiras do ib_bot — coincidência de nome que engana à primeira vista. |

Não existe unidade systemd separada `ib-altdata-qa.timer`/`ib-altdata-backup.timer`/`ib-backtests.timer`
neste servidor hoje (as auditorias anteriores referiam-nas, mas o backup/QA diário do arquivo PIT
corre hoje via commits automáticos do Celery beat dentro do stack Docker — confirmado pelos
commits diários `backup(altdata)`/`qa(altdata)` no git log, não por unidades systemd distintas).

### Stack Docker (`docker ps -a --filter name=ib_bot`, `docker system df`)
```
ib_bot-api-1        Up 6 weeks   0.0.0.0:8001->8000/tcp
ib_bot-beat-1       Up 6 weeks
ib_bot-worker-1     Up 6 weeks
ib_bot-db-1         Up 6 weeks   5432/tcp (não exposta ao host)
ib_bot-redis-1      Up 6 weeks   6379/tcp
ib_bot-web-1        Up 6 weeks   3000/tcp
ib_bot-nginx-1      Up 6 weeks   0.0.0.0:8090->80/tcp
```
`curl localhost:8001/health` → `200`. `curl localhost:8090` → `200`. `curl localhost:3001` →
`307`. **Continuam dois frontends vivos ao mesmo tempo** — 7ª auditoria seguida a repetir o mesmo
achado.

`docker system df`: **31,51 GB de imagens, 100% reclamáveis** (20 imagens) — inalterado, byte a
byte igual à auditoria anterior. Ninguém correu `docker image prune`.

### Tarefas internas do bot (celery beat/worker — `docker logs ib_bot-worker-1`, últimos 7 dias completos, 2026-09-21 a 2026-09-27)
- `altdata_snapshot_daily_task` — saudável todos os dias.
- **`paper_rebalance_daily_task` (15:00 WEST diário) — CONTINUA QUEBRADA, sem interrupção.**
  Confirmado, dia a dia, do log completo (`docker logs ib_bot-worker-1 --since 168h | grep
  paper_rebalance_daily`, comando corrido nesta sessão): em **2026-09-21 a 2026-09-27** (7 dias,
  todos verificados), às 15:00:00 WEST, para **cada uma das duas contas**
  (`account=1 portfolio=7095ae3e...`, `account=2 portfolio=d2e87bea...`), o rebalanceamento real
  levanta sempre `tuple index out of range`, é apanhado, e só regista `logger.warning(...)` —
  nunca aparece como falha no systemd/Celery nem dispara nenhum alerta. Total acumulado hoje:
  **45 dias corridos de falha, de 2026-08-14 a 2026-09-27, sem uma única exceção.**
  - Diagnóstico adicional feito nesta sessão (execução isolada, read-only, dentro do próprio
    container, sem tocar em nenhuma linha da base de dados): chamar diretamente
    `RebalancingBacktestEngine._generate_rebalance_events(strategy_name="Congress Buys", ...)`
    **funciona sem erro** (54 eventos gerados). Isto restringe a causa: o bug não está na função
    genérica de geração de eventos em si (pelo menos não para todas as estratégias), mas algures
    na combinação de múltiplas estratégias/portefólios reais das duas contas, ou numa estratégia
    específica do catálogo de 9 configuradas nesses portefólios, ou em `place_market_order`/
    `fetch_prices` chamados a seguir dentro de `paper_rebalance_execute`. Evidência: código em
    `backend/app/worker/tasks.py:481-572` (apanha a exceção e só regista aviso);
    `backend/app/api/routes/paper.py:264-414` (constrói pesos combinados, chama
    `_generate_rebalance_events` por estratégia, depois `place_market_order` para cada perna). **Nenhum destes ficheiros foi tocado em nenhum commit desde a descoberta do bug em 09-07**, apesar de todo o outro trabalho de engenharia feito nesta janela.

### Base de dados (Postgres dentro de `ib_bot-db-1`, `docker exec ib_bot-db-1 psql -U ibbot -d ibbot`)
- `ib_orders` = **0**, `ib_trades` = **0**, `live_execution_requests` = **0** — confirma **zero
  ordens reais desde sempre**, inalterado.
- `altdata_snapshots` = **855 linhas** (era 778 em 09-21), `count(distinct captured_at::date)` =
  **78 dias** (era 71) — cresceu 77 linhas / 7 dias, ritmo de ~11/dia mantido, consistente.
- `paper_snapshots`: 2 contas, **126 registos cada** (era 119 em 09-21), 2026-05-26 a
  **2026-09-27**.
  - Conta 1 (`account_id=1`): sempre `equity=$100.000` — **126 medições seguidas**, ainda sem
    qualquer movimento (consistente com o rebalanceamento também quebrado para esta conta).
  - Conta 2 (`account_id=2`): equity diária de **US$177.973,30** (26 mai) a **US$180.875,55**
    (27 set, último registo) — ganho acumulado de **+US$2.902,25 (+1,63%)** em 125 dias-calendário
    distintos. **Desde a auditoria anterior (21-09: US$180.706,13), a conta subiu US$169,42
    (+0,09%)** — praticamente parada, com um pico intermédio a 22-09 (US$182.669,88) e queda
    depois. Métricas completas (Sharpe 0,43 anual, Sortino 0,40, drawdown máximo inalterado
    US$9.577,09 / 5,24% — a pior queda continua a de julho) em `metrics.json`.
    **Continua confirmado:** `paper_trades` (conta 2) mantém **138 registos, inalterado desde
    `max(timestamp)=2026-05-09`** — nenhum trade novo há mais de 4 meses e meio. A curva de equity
    é, portanto, só a reavaliação a preço de mercado de uma carteira comprada em maio e nunca mais
    mexida — não é o resultado de nenhuma estratégia sendo testada ativamente.

### Resultado do backtest semanal mais recente
Ainda o de `.cache/latest_backtest_results.json`, gerado 2026-09-20 14:13 WEST (o backtest de
domingo 27-09 não deixou recibo mais recente visível nesta verificação de disco — `find
.cache -name '*.json' -newer` não mostrou ficheiro mais novo que 20-09; isto por si só não é
prova de que o timer falhou, só que o cache publicado é o mesmo há uma semana; não investigado
mais fundo por estar fora do foco desta auditoria, mas fica registado para a próxima). Isto NÃO
muda a conclusão da auditoria de investibilidade v4 (Deflated Sharpe Ratio) — continua a reprovar
as 56 estratégias.

### Conta real na Interactive Brokers (via MCP `get_account_summary`/`get_account_positions`, consultado nesta sessão)
- **Valor líquido: EUR 26.859,71** (era EUR 27.906,49 em 09-21 — **queda de EUR 1.046,78 /
  -3,75%** esta semana). Leverage subiu de 1,67 para **2,4**, cash total −EUR 37.577,07, margem
  inicial usada EUR 21.841,46.
- **Posição NOVA desde a última auditoria: 60 ações de GOOG (Alphabet)**, valor USD 20.259,00,
  perda não realizada −USD 951,40. As outras três posições mantêm-se: 70 BRK B (+USD 1.066,85),
  300 ações "8473 @TSEJ" / SBI Holdings (−JPY 26.886, maior perda esta semana), 60 unidades
  "BCHN @LSEETF" (+USD 131,10).
- Estas são **posições pessoais do José, geridas manualmente por ele** (fora do robô) —
  confirmado porque `ib_orders=0`/`ib_trades=0` na base de dados do bot continua exatamente
  igual. **O robô não tocou na conta.** Registado aqui só para manter o estado da conta
  atualizado; não é um achado do bot.

### Planos do Conductor (comando: `psql -U servidor -d conductor`)
| Plano | Slug | Status | Nota |
|---|---|---|---|
| `04bf8af8` — Alt-data PIT archive hardening | `ib_bot` | `done` | Sem alterações. |
| `e36e04ec` — pós-triagem 2026-07-12 | `ib_bot` | `superseded` | Sem alterações. |
| `3702771c` — ib_bot → Alt-Data Product | `ib_bot` | `superseded` | Sem alterações. |
| `4c48535c` — IB bot money-path hardening | `ib_bot` | `done` (fechado 2026-09-15) | Sem alterações. |

**Nenhum plano novo, aberto ou executing, para o slug `ib_bot` desde 09-15** — pesquisa por
título/conteúdo (`ILIKE '%ib bot%'`, `%ib_bot%'`, `%paper rebalance%'`, `%e-mini%'`, `%futures%'`)
confirma zero planos ativos hoje. O trabalho do laboratório de trading que tocou neste repositório
(`f86848f`, `486b6e3`) corre sob planos de OUTRO domínio (`trading_manager` / `lab-ib-20260924`,
plano `d9355270-7ffb-4212-bb77-fc2c40ec61ae` segundo a memória partilhada), não sob um plano do
`ib_bot`.

## (d) Findings, ordenados por gravidade

### CRÍTICO

**#0 — CONTINUA. O motor de paper trading está quebrado há pelo menos 45 dias corridos, sem
interrupção, e sem correção.** A tarefa diária `paper_rebalance_daily_task` corre às 15:00 WEST
todos os dias e "sucede" ao nível do sistema de tarefas (Celery), mas dentro dela, para as DUAS
contas de paper trading, o rebalanceamento real levanta sempre `tuple index out of range` e é
engolido como `WARNING`. Confirmado em `docker logs ib_bot-worker-1`: **todos os dias sem
exceção, de 2026-08-14 a 2026-09-27** (7 dias novos confirmados nesta sessão desde a auditoria
anterior). Consequência prática inalterada: a conta paper 1 está congelada em exatamente $100.000
há 126 medições seguidas; a conta paper 2 não recebe um trade novo desde **2026-05-09**.
Diagnóstico adicional feito nesta sessão (ver secção (c)) reduz o espaço de busca: a função
genérica `_generate_rebalance_events` funciona isoladamente para pelo menos uma estratégia
("Congress Buys"); o erro está algures na combinação de várias estratégias/portefólios reais ou
nos passos seguintes (`place_market_order`/`fetch_prices`). Evidência: `docker logs
ib_bot-worker-1 --since 168h | grep paper_rebalance_daily` (comando corrido nesta sessão); código
em `backend/app/worker/tasks.py` e `backend/app/api/routes/paper.py` — nenhum destes ficheiros
foi tocado em nenhum commit desde a descoberta do bug em 09-07.

**#1 — SETE auditorias seguidas (08-17, 08-24, 08-31, 09-07, 09-14, 09-21 e agora de novo hoje)
recomendaram o MESMO plano de limpeza de passos simples; nenhum foi executado.** Verificado
byte-a-byte nesta sessão: os dois frontends continuam ambos vivos, as 31,51 GB de imagens Docker
reclamáveis são exatamente o mesmo número de 5 auditorias atrás, os resíduos na raiz do
repositório (`$LOG`, `alembic_validation.db`, os 3 `backtest_results_*.json`,
`docker-compose.prod.yml.bak.*`) têm as mesmas datas de modificação de janeiro/maio, e a decisão
de negócio sobre o destino do arquivo PIT continua por tomar (agora **mais de 2 meses e meio**
desde julho). **Confirmado nesta sessão: continua a não existir nenhuma entrada de memória que
registe uma resposta do José** a esta pergunta explícita de limpeza. O padrão "auditoria escreve,
ninguém lê/decide" continua intacto pela 7ª vez — **um ponto positivo**: pelo menos um item da
lista (`.worktree-quarantine/`, 865 MB) foi limpo silenciosamente por outro operador esta semana,
o que mostra que a limpeza É possível quando alguém decide fazê-la; só falta decidir o resto.

### ALTO

**#2 — Dois frontends web vivos ao mesmo tempo, sem necessidade clara (repetido pela 7ª vez).**
`curl localhost:3001` → `307` (`ib-bot-v2-frontend.service`, Next.js). `curl localhost:8090` →
`200` (stack Docker completa própria, nginx + React antigo). Ambos apontam para a mesma API
`:8001` — são a mesma informação, duas interfaces.

**#3 — Nenhuma das 56 estratégias de investimento tem edge robusto, confirmado repetidamente
(inalterado desde maio).** Deflated Sharpe Ratio reprova as 56.

**#4 — Engenharia continua a ser gasta todos os dias num arquivo de dados sem uso decidido.**
`altdata_snapshots` cresceu de 778→855 linhas (77 em 7 dias); a decisão de negócio continua em
HOLD desde julho — agora **mais de 11 semanas** sem decisão.

### MÉDIO

**#5 (NOVO) — Um projeto irmão (`trading_manager`) publicou código novo neste repositório
(`f86848f`) para reutilizar o adaptador de execução da IB numa investigação separada de futuros
E-mini, incluindo, no mesmo laboratório mas fora deste repositório, uma autenticação real na
conta ao vivo da IB com TOTP existente (só leitura, gateway fechado a seguir, sem ordens).** Isto
está devidamente aprovado e delimitado pelo José e pelas suas próprias regras de segurança (ver
memória `project_trading_crypto_lab_20260922`), mas introduz um risco de coordenação que este
audit regista: o código de execução do ib_bot (`system/execution/ib_executor.py`) agora evolui
por dois caminhos independentes (o dono `ib_bot`, dormente, e o laboratório `trading_manager`,
ativo) — uma alteração futura de segurança num dos dois lados pode não se propagar
automaticamente ao outro. O próprio commit seguinte (`486b6e3`, mesmo dia) já reagiu a um segundo
risco real deste cruzamento: o checkout principal do ib_bot quase publicou trabalho de laboratório
não revisto através do backup noturno automático, e foi corrigido com uma guarda explícita antes
de isso acontecer. Recomenda-se só documentar/observar, não bloquear — o dono (`trading_manager`)
já geriu isto com cuidado.

**#6 — 31,51 GB de imagens Docker reclamáveis, 20 imagens (inalterado há 6 auditorias
seguidas).**

**#7 — `paper_rebalance_daily_task` não emite *traceback* completo no erro, só a mensagem da
exceção** — continua a impedir uma correção rápida sem reproduzir localmente.

### BAIXO

**#8 — Resíduos na raiz do repositório, inalterados desde 08-17 (7ª auditoria seguida a encontrar
os mesmos ficheiros).** `$LOG` (765 KB), `alembic_validation.db` (86 KB), 3× `backtest_results_*.json`
(3,3 MB), `docker-compose.prod.yml.bak.1778273314`.

**#9 — Conta paper 1 (id=1) sempre em $100.000, sem documentação de propósito** — explicado em
parte pelo Finding #0 (rebalanceamento também quebrado para esta conta).

**#10 — 4 ficheiros de planos antigos com nome de data `undefined_*` em `docs/plans/`** (de
17-08, ex: `undefined_plano_fixes.md`), resíduo de um bug cosmético de uma auditoria antiga que
não conseguiu calcular a data — inofensivo, mas confunde quem procura o histórico por data;
renomear ou apagar sem risco.

**#11 (NOVO) — O último recibo de backtest semanal em disco continua datado de 20-09**, sem um
mais recente visível para o domingo 27-09; não investigado em profundidade nesta sessão (fora do
foco), mas fica sinalizado para confirmar na próxima auditoria se o timer `ib-backtests` correu e
publicou normalmente.

### INFORMATIVO / POSITIVO

**#A — O worktree `.worktree-quarantine/` (865 MB, achado MÉDIO da auditoria anterior) foi
limpo.** Confirmado com `du -sh`: 32 KB hoje. Sem registo formal de quem o fez, mas sem dano —
mostra que limpeza acontece quando alguém a prioriza.

**#B — O novo commit `486b6e3` já aplica corretamente a lição de segurança "checkout principal só
para jobs agendados"** que este audit teria de outra forma recomendado — o próprio `AGENTS.md` do
repositório já diz isto e há testes automáticos (`test_altdata_backup_branch.py`) a prová-lo.

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Investigar e corrigir o Finding CRÍTICO #0 (paper rebalance quebrado)** — continua a ser o
   achado mais importante: cada dia que passa sem corrigir é mais um dia de dados de "performance"
   inúteis/enganosos acumulados (já são 45). Baixo risco (não mexe em dinheiro real), alto valor
   informativo. Ver plano de fixes passo 1 com diagnóstico mais fundo já feito nesta sessão.
2. **Resolver o Finding CRÍTICO #1 outra vez — decisão explícita do José, não outro plano de
   limpeza idêntico.** Já são 7 auditorias a pedir isto.
3. Consolidar os dois frontends (#2) — baixo risco, reversível.
4. Limpar disco Docker (#6) — grátis, sem risco, recupera >30 GB.
5. Arrumar resíduos no root (#8) e renomear/apagar os 4 ficheiros `undefined_*` (#10) — cosmético
   mas rápido.
6. Adicionar *traceback* completo ao log do bug #0 antes/durante a correção (#7) — torna a
   próxima vez que algo assim acontecer muito mais rápida de diagnosticar.
7. Confirmar se o backtest semanal de 27-09 correu (#11) — verificação rápida, sem risco.
8. Finding #5 — só documentar/observar; não é uma ação do ib_bot, é do laboratório
   `trading_manager` (já gerido por esse dono).

## (f) Riscos se nada for feito

- **Nenhum risco de perda de dinheiro real hoje.** Trading ao vivo está travado em 4+ camadas
  (`ibgateway` desligado, `LIVE_AUTO_REBALANCE` off, guarda de pré-voo de ordens, gate atómico de
  colocação, e o hardening completo do plano `4c48535c`). `ib_orders=0`/`ib_trades=0` confirmado
  de novo. Também confirmado: nenhum listener em `:4001`-`:4004` neste momento.
- **Risco confirmado e a agravar: decisões futuras baseadas na curva de equity de paper trading
  continuam erradas.** Quanto mais tempo o bug #0 fica por corrigir, mais dias de dados
  "congelados mas parecendo ativos" se acumulam — hoje já são 45 dias confirmados.
- **Risco continuado de desperdício de atenção, disco e confiança no processo de auditoria** —
  mesmo achado de limpeza pela 7ª vez seguida.
- **Risco de fadiga de auditoria** — 7 ciclos seguidos com a mesma recomendação ignorada é o
  momento certo para o José decidir explicitamente se quer manter esta cadência ou mudar de
  abordagem (ex.: só auditar quando algo muda de facto).
- **Risco de coordenação (novo, baixo mas a monitorizar):** o código de execução da IB agora tem
  dois donos ativos em paralelo (`ib_bot` dormente, `trading_manager` a construir por cima). Não
  é um risco de dinheiro hoje, mas vale a pena revisitar dentro de 2-3 auditorias se o laboratório
  continuar a publicar neste repositório com frequência.

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
- **Celery beat/worker** — um "relógio" (beat) que dispara tarefas periódicas dentro da própria
  aplicação, e um "trabalhador" (worker) que as executa.
- **systemd timer** — o despertador do próprio computador Linux que dispara uma tarefa a uma hora
  marcada.
- **Docker / container** — uma "caixa" isolada onde um programa corre com tudo o que precisa.
- **Conductor / Domain Manager (gestor de domínio) / plano / fase** — o sistema que o José usa
  para gerir trabalho longo de agentes de IA; um "gestor de domínio" (ex.: `trading_manager`) pode
  ter autoridade sobre vários repositórios ao mesmo tempo, incluindo o `ib_bot`.
- **TOTP (Time-based One-Time Password)** — o código de 6 dígitos que muda a cada 30 segundos,
  usado como segundo fator de autenticação (2FA); aqui, um mecanismo já existente e automatizado
  para entrar na conta real da IB só para consultas, nunca para ordens.
- **E-mini (ES/NQ)** — contratos "futuros" (promessas de compra/venda a um preço fixado, para uma
  data futura) sobre os índices bolsistas S&P 500 (ES) e Nasdaq-100 (NQ), numa versão mais
  pequena/acessível do contrato original.
- **13F** — relatório trimestral obrigatório nos EUA em que grandes fundos revelam o que
  compraram/venderam.
- **Sharpe Ratio / Sortino Ratio / Drawdown / VaR** — medidas de "ganho por risco", "ganho por
  risco de perdas", "maior queda pico-a-vale", e "pior perda esperada num dia mau", respetivamente.
- **runjob** — a ferramenta do José para correr trabalho pesado (CPU/RAM/disco) dentro de limites
  seguros, para não travar a máquina inteira.
- **worktree (do git)** — uma segunda cópia de trabalho do mesmo repositório, útil para um agente
  trabalhar numa fase sem interferir com o código principal; deve ser removida depois de fundida.
