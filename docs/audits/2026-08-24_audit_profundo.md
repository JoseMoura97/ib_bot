# Audit Profundo — IB Bot (2026-08-24, ART / 2026-08-24 06:09 -03)

> Sessão de auditoria: /home/servidor/agent-workspaces/mega-audit-2026-08-24.
> Todos os comandos abaixo foram corridos NESTA sessão (ground truth re-verificado, não copiado
> de memória). Onde relevante, mostra-se comando + resultado resumido.

## (a) O que é este projeto (para um miúdo de 12 anos)

O **IB Bot** é um robô de computador que devia comprar e vender ações sozinho, usando a conta
de trading do José na **Interactive Brokers (IB — a corretora, a empresa que executa as ordens
de compra/venda na bolsa)**. A ideia era: copiar o que "gente esperta" faz — políticos dos EUA
quando compram ações, fundos famosos (como o de Warren Buffett) quando publicam os seus
relatórios trimestrais, gestores que apostam contra empresas (Michael Burry) — e ver se copiar
essas jogadas dá dinheiro.

O robô testou **56 ideias diferentes** ("estratégias") em dados históricos, com um motor de
**backtest** (simular "se eu tivesse seguido esta regra no passado, ganhava ou perdia?"). Tem
três peças:
1. **Motor de backtest** — testa ideias no passado, de graça, sem risco.
2. **Motor de execução** — a peça que manda ordens reais para a IB. Está **desligada** desde
   julho de 2026 por decisão do José.
3. **Arquivo "ponto-no-tempo" (PIT — point-in-time)** — desde 13 de julho de 2026, o robô tira
   uma "fotografia" todos os dias de 11 fontes de dados públicas e guarda-a para sempre, mesmo
   que a fonte original mude depois. Isto é valioso porque nunca mais se pode reconstruir esse
   dia exatamente como estava — ou se guarda agora, ou perde-se para sempre.

O projeto está marcado como **PAUSED (pausado)** no sistema de gestão de projetos do José (o
Conductor), mas isso significa "não se decide o próximo grande passo de negócio" — não
significa "desligado". Como se vai ver na secção (c), há 8 processos automáticos a correr
todos os dias sozinhos.

## (b) Evolução até hoje (timeline, com datas verificadas)

Fonte: `git log` completo do repositório `/home/servidor/Desktop/cursor-projects/ib_bot`
(207 commits, primeiro commit `2026-01-17`) + memórias do José em
`/home/servidor/.claude/projects/-home-servidor/memory/` + histórico de auditorias anteriores
neste mesmo diretório (`docs/audits/2026-07-12_*`, `2026-07-20_*`, `2026-08-10_*`,
`undefined_audit_profundo.md` de 2026-08-17).

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repositório. |
| 2026-01 a 2026-04 | Construção inicial: motor de backtest, catálogo de estratégias, execução IB, frontend. Ritmo lento (6, 10, 5, 1 commits/mês). |
| 2026-05 (18 commits) | Auditoria de investibilidade v1→v4 (memória `project_ib_bot_audit.md`): v1 mostra que o "alfa" (ganho acima do mercado) das estratégias populares é na verdade **beta** (só sobem porque o mercado sobe). v2 corrige o erro e encontra ~5 estratégias com alfa positivo não-deflacionado. v3 mede **decaimento do sinal**: as estratégias mais populares (Congress Buys, Burry) perderam a força desde que ETFs como a NANC começaram a copiar o mesmo truque publicamente em 2023. v4 (AUTORITATIVA) aplica o **Deflated Sharpe Ratio** (teste que pune ter experimentado 56 ideias — quanto mais tentas, maior a hipótese de uma parecer boa só por sorte): **NENHUMA das 56 passa**. Recomendação: vender o motor de dados, não o "alfa". |
| 2026-05-23 | Estudo irmão PEAD (Post-Earnings Announcement Drift, no repo `trading`) é **REJEITADO** — mesma conclusão: beta, não alfa, mesmo com pesquisa agressiva de parâmetros (696 configurações testadas, o melhor resultado inverteu de positivo para negativo no holdout). |
| 2026-07-12/13 | **Decisão de negócio do José: dormência seletiva.** Gateway IB (`ibgateway.service`, `xvfb-ibgw.service`) desligados — zero sessões live diárias. Arranca o arquivo diário PIT (`altdata_snapshots`). Plano Conductor `e36e04ec` criado com 8 fases (f1-f5, x1-x2, a1). |
| 2026-07-16 | Estudo irmão **earnings-vol / "Iron Wing" (0006)** é **MORTO** (memória `project_earnings_vol.md`): gate pré-registado de 36 eventos forward atingido — PF (profit factor) a preço médio 0.776, a preço de toque real 0.256, ambos <1 → perde dinheiro. Zero compra de ThetaData, zero capital real. |
| 2026-07-18/19 | Fases f2 (backtest semanal corrigido) e f4 (repo limpo, merge para `main`) do plano `e36e04ec` fecham com oráculos congelados (evidência imutável). Hardening de memória do backtest semanal (cache-first, `YF_MEMORY_CACHE_MAX_TICKERS=128`) depois de dois kills por `systemd-oomd`. |
| 2026-08-05 a 08-13 | Plano Conductor `04bf8af8` "Alt-data PIT archive hardening" — torna o arquivo à prova de batota: backup noturno offsite (`ib-altdata-backup.timer`), separação de dono na base de dados (o papel `ibbot` de aplicação perde poderes de superuser — corrige um CRITICO real encontrado por auditoria independente ECC), guarda de pré-voo de ordens partilhada (`order_preflight.py`). |
| 2026-08-14 a 08-20 | Fase H3 do plano `04bf8af8` — prova de "opera sem agente humano" — soak de 3 disparos autónomos consecutivos do timer diário de QA (14, 15, 16 de agosto). **Fecha em 2026-08-20** (ver secção (c) — confirmado nesta sessão). |
| 2026-08-17 | **Auditoria profunda anterior** (commit `1da63d3`, mesmo formato deste relatório) produz `docs/audits/undefined_audit_profundo.md` + 4 planos. Recomenda 5 passos de limpeza/decisão. **Nenhum foi executado até hoje** — ver Finding ALTO #1 abaixo. |
| 2026-08-20 | Plano `04bf8af8` passa a `status=done` (todas as 5 fases done). |
| 2026-08-24 (hoje) | Este audit. Arquivo PIT continua a crescer sozinho: 471 linhas, 43 dias distintos, 11 fontes; equity paper trading em $184.794,80. |

## (c) Estado concreto HOJE (verificado nesta sessão)

### Repositórios
- `/home/servidor/Desktop/cursor-projects/ib_bot` — repo git ativo (`main`), 207 commits, **19
  commits desde a última auditoria (08-17)**, todos automáticos (backup diário do arquivo PIT +
  recibos de QA diária). `git log -1`: commit `0727d44` "backup(altdata): PIT table
  20260824T033104Z", hoje 04:31 WEST.
- `/home/servidor/Desktop/cursor-projects/ib_bot-v2` — worktree secundário na branch
  `frontend-v2`, **decomissionado** (confirmado: nenhum container Docker na porta 8092 vivo).
- O path `ib_bot-altdata-wt` citado no brief **não existe** (`find` não encontrou o diretório) —
  provavelmente um worktree temporário do Conductor já removido; não afeta nada vivo.

### Serviços systemd (comando: `systemctl status <unit>` corrido nesta sessão)
| Unit | Estado | Nota |
|---|---|---|
| `ibgateway.service` | `inactive (dead)`, `disabled` | Desligado por decisão do José desde 07-12/13. Comportamento esperado. |
| `xvfb-ibgw.service` | `inactive (dead)`, `disabled` | Idem. |
| `ib-bot-v2-frontend.service` | `active (running)` há 1 semana e 6 dias, porta 3001 | Fala com a API v1 real (:8001). `curl localhost:3001` → `307` (vivo, redireciona). |
| `theta-terminal.service` | `active (running)` há 1 semana e 6 dias, PID java, memória 684 MB (pico 4,7 GB) | Serve dados de opções para `theta-learned.timer`, que **é do projeto Polymarket, não do ib_bot** (confirmado pela descrição literal da unit nos logs: "Polymarket learned theta report-only daily monitor"). No código do ib_bot só é referenciado por 2 scripts do estudo morto Iron Wing (`scripts/verify_iron_wing_completion.py`, `scripts/reconcile_iron_wing.py`) — não é usado no dia-a-dia do ib_bot. |
| `ib-altdata-qa.timer` / `.service` | `active (waiting)` / último disparo 08-23 08:00 WEST, sucesso | Do ib_bot. QA diária do arquivo PIT. |
| `ib-altdata-backup.timer` / `.service` | `active (waiting)` / último disparo hoje 04:31 WEST, sucesso, push para GitHub confirmado no journal | Do ib_bot. Backup offsite noturno. |
| `ib-backtests.timer` / `.service` | `active (waiting)` / último disparo 08-23 05:16→06:34 WEST, sucesso, 1h05min CPU | Do ib_bot. Backtest semanal completo (56 estratégias). |
| `execution-metrics.timer` | `active (waiting)` | **NÃO é do ib_bot** — confirmado pela descrição da unit: "Polymarket execution daily metrics -> Mongo model_metrics_history". |
| `cost-recalibration.timer` | `active (waiting)` | **NÃO é do ib_bot** — descrição: "Polymarket weekly fill-cost bracket recalibration (not wired to trading)". |
| `historical-backfill.timer` | `active (waiting)` | **NÃO é do ib_bot** — descrição: "Polymarket historical-backfill — daily incremental subgraph pull". |
| `paper-ironfly.timer` | `active (waiting)`, próximo disparo amanhã | **NÃO é do ib_bot** — pertence ao projeto irmão `trading` (estudo Iron-fly de agosto, memória `project_ironfly_august_watch_20260714.md`), corre no repo `trading`, não neste. |

Isto resolve definitivamente a pergunta do brief "confirmar quais pertencem ao ib_bot vs
trading": **3 timers são do ib_bot** (`ib-altdata-qa`, `ib-altdata-backup`, `ib-backtests`); os
outros 4 citados no brief (`theta-learned`, `paper-ironfly`, `historical-backfill`,
`execution-metrics`, `cost-recalibration`) pertencem a **Polymarket** ou ao projeto irmão
`trading`.

### Stack Docker (comando: `docker ps -a`)
```
ib_bot-api-1     Up 10 days   0.0.0.0:8001->8000/tcp
ib_bot-beat-1    Up 10 days
ib_bot-worker-1  Up 10 days
ib_bot-db-1      Up 13 days   (Postgres 16, não exposta ao host)
ib_bot-redis-1   Up 13 days
ib_bot-web-1     Up 13 days   0.0.0.0:8090->80/tcp (via nginx)
ib_bot-nginx-1   Up 13 days
```
`curl localhost:8001/health` → `200`. `curl localhost:8090` → `200`. **Dois frontends vivos ao
mesmo tempo** (systemd :3001 e Docker :8090) — mesmo finding da auditoria anterior, **ainda não
resolvido** (ver Finding ALTO #2).

### Base de dados (Postgres dentro de `ib_bot-db-1`, acesso `docker exec ib_bot-db-1 psql -U ibbot -d ibbot`)
- `ib_orders` = **0**, `ib_trades` = **0**, `live_execution_requests` = **0** — confirma **zero
  ordens reais desde sempre**.
- `live_rebalance_audit` = 25 linhas (17 dry-run + 8 preview, nunca um execute real — inalterado
  desde maio).
- `altdata_snapshots` = **471 linhas**, 43 dias distintos, `2026-07-13` a `2026-08-24`, 11 fontes
  (CFTC, FINRA, FRED, House disclosure ×2, SEC ×2, Nasdaq, USAspending, 13F Berkshire, 13F Scion).
  Cresce ~11 linhas/dia sozinho. Tabela tem gatilho `altdata_snapshots_reject_mutation` que
  recusa `UPDATE`/`DELETE` diretos (confirma o hardening tamper-evidence do plano `04bf8af8`).
- `paper_snapshots`: 2 contas, 91 registos cada, `2026-05-26` a `2026-08-23`.
  - Conta 1: sempre `cash=100000, equity=100000` — conta parada, nunca operou (provavelmente
    conta de controlo/baseline).
  - Conta 2: equity de **$177.973,30** (26 mai) para **$184.794,80** (23 ago) — 90 dias de
    dinheiro FINGIDO (paper trading). Ver métricas na secção seguinte e em `metrics.json`.
- `paper_trades` (conta 2) = 138 registos, contagem estável desde maio — não houve novos trades
  registados recentemente na tabela de trades individual (o ganho vem de reavaliação de posições
  existentes + rebalanceamentos periódicos que atualizam `paper_snapshots` sem necessariamente
  gerar novas linhas em `paper_trades` a cada dia).

### Conta real na Interactive Brokers (via MCP `get_account_summary` / `get_account_positions`,
consultado nesta sessão)
- **Valor líquido: EUR 26.550,79** (era EUR 27.247,71 em 08-17 — variação de mercado normal).
- Posição única: **70 ações BRK B** (Berkshire Hathaway), valor de mercado USD 34.891,50,
  ganho não realizado +USD 524,35.
- Esta é uma **posição pessoal do José**, comprada manualmente — o robô nunca lá tocou
  (confirmado por `ib_orders=0`/`ib_trades=0` na base de dados do bot).

### Planos do Conductor (comando: `psql conductor -c "SELECT id,status,title FROM project_plans WHERE slug='ib_bot'"`)
| Plano | Status | Nota |
|---|---|---|
| `04bf8af8` — Alt-data PIT archive hardening | **done** (5/5 fases done, fechado 2026-08-20) | Já não está a correr — resolve o item "amarelo" da auditoria anterior (estava à espera do 3º dia do soak H3; hoje está fechado). |
| `e36e04ec` — pós-triagem 2026-07-12 | **paused** (8/8 fases done) | Todas as fases técnicas (dormência, backtest, ledger, repo, arquivo PIT, estudo 0006, B2B) fecharam done. A fase `a1_altdata_b2b` termina com uma nota explícita: **"B2B em HOLD. NÃO reabrir, NÃO voltar a cardar, NÃO fazer qualquer contacto comercial."** — os entregáveis técnicos (exports com 51.967 linhas, one-pager `docs/altdata_b2b_one_pager_draft.md`) estão prontos mas a decisão de negócio de vender fica parada por ordem do José. |
| `3702771c` — ib_bot → Alt-Data Product | **superseded** (06-05) | Plano antigo substituído pelo `e36e04ec`. |

## (d) Findings, ordenados por gravidade

### CRITICO
Nenhum finding CRITICO ativo hoje. O único CRITICO conhecido na história do projeto (o papel de
aplicação `ibbot` na base de dados tinha poderes de superuser, podendo forjar correções
"auditadas") **já foi corrigido** — fase `h4_tamper_evidence` do plano `04bf8af8`, `done`,
verificado por auditoria independente (ECC) em 2026-08-13, evidência em
`reference_ib_bot_altdata_owner_boundary_20260812.md`. Confirmado nesta sessão: a tabela
`altdata_snapshots` tem o gatilho `altdata_snapshots_reject_mutation` ativo.

### ALTO

**#1 — O plano de fixes da auditoria anterior (08-17) não foi executado, 7 dias depois.**
Evidência: os 5 passos do ficheiro `docs/plans/undefined_plano_fixes.md` (commit `1da63d3`,
08-17) recomendavam (1) confirmar fecho do gate H3, (2) levar ao José a decisão de continuidade,
(3) consolidar os dois frontends, (4) limpar imagens Docker, (5) arrumar resíduos no root.
Verificado nesta sessão: o passo 1 fechou-se sozinho (o Conductor fez o trabalho, não a
auditoria); os passos 2, 3, 4 e 5 continuam exatamente como estavam — `$LOG` (765 KB),
`alembic_validation.db` (86 KB), os 3 `backtest_results_*.json` (3,3 MB no total) e o
`docker-compose.prod.yml.bak.1778273314` continuam na raiz do repo (`ls -la` confirmou nesta
sessão); as duas frontends continuam ambas vivas; `docker system df` mostra ainda 32,36 GB de
imagens 100% reclamáveis. Nenhuma memória nova sobre "decisão do José" foi encontrada
(`grep -rl ib_bot memory/ | xargs stat` mostra que os únicos ficheiros de memória tocados desde
08-17 nem mencionam decisão de continuidade). **Isto significa que ninguém está a ler ou agir
sobre estas auditorias.**

**#2 — Dois frontends web vivos ao mesmo tempo, sem necessidade clara (repetido de 08-17).**
`curl localhost:3001` → `307` (systemd `ib-bot-v2-frontend.service`, fala com a API v1 real
:8001). `curl localhost:8090` → `200` (Docker `nginx-1`+`web-1`, stack completa incluindo API/
worker/beat/db/redis próprios, rodando há 13 dias). Ambos respondem, ambos consomem recursos
(RAM + CPU do stack Docker inteiro só para servir uma segunda cópia do frontend), e não há
registo de qual o José realmente usa.

**#3 — Nenhuma das 56 estratégias tem edge robusto, confirmado repetidamente (herdado, sem
mudança desde maio).** Deflated Sharpe Ratio (teste que pune ter testado 56 ideias diferentes)
reprova as 56; os 2 "sobreviventes" pré-deflação (Transportation Committee, House Long-Short)
dependiam de 1-2 meses de sorte (65%/95% do ganho pós-2023 concentrado em 1-2 meses). O estudo
irmão earnings-vol (0006) também morreu no gate de 36 eventos forward. O estudo irmão PEAD
morreu com 7 testes independentes convergentes. **Três tentativas de encontrar edge, três
kills.**

**#4 — Engenharia continua a ser gasta todos os dias num arquivo de dados sem uso decidido.**
O arquivo PIT (`altdata_snapshots`) cresceu de 328→471 linhas desde 08-11 e vai continuar a
crescer sozinho (backup, QA, captura diária), mas a decisão de negócio sobre para que serve
(vender B2B? testar mais estratégias? arquivar?) está formalmente em HOLD desde a triagem de
julho, e ninguém voltou a levá-la ao José desde então (ver #1).

### MEDIO

**#5 — `theta-terminal.service` sempre ligado, já teve picos de 4,7 GB RAM + 2,9 GB swap.**
Verificado nesta sessão que só é consumido pelo timer `theta-learned` (Polymarket) e por 2
scripts do estudo Iron Wing já morto no ib_bot. Não é um problema do ib_bot per se, mas o ib_bot
não precisa dele — se o Polymarket alguma vez o desligar, nenhum processo vivo do ib_bot quebra.

**#6 — 32,36 GB de imagens Docker + reclamável, 21 imagens.** `docker system df` corrido nesta
sessão confirma o mesmo problema da auditoria anterior, ligeiramente pior (era 36,3 GB
"images+cache" combinados em 08-17; hoje são 32,36 GB só de imagens, 100% reclamáveis, mais
containers/volumes residuais).

**#7 — Container `ib_bot-web-lint-1` parado há 7 semanas, nunca limpo.** `Exited (0) 7 weeks ago`
— não consome recursos ativos mas é ruído no `docker ps -a`.

### BAIXO

**#8 — Resíduos na raiz do repositório, inalterados desde 08-17.** `$LOG` (765 KB), 
`alembic_validation.db` (86 KB), `backtest_results_2026_05_12.json` + `_corrected.json` +
`_final.json` (3,3 MB), `docker-compose.prod.yml.bak.1778273314` — todos ainda presentes,
confirmados por `ls -la` nesta sessão.

**#9 — Conta paper 1 (id=1) fica sempre em $100.000, sem uso aparente.** 91 snapshots idênticos
de `cash=equity=100000` — provavelmente uma conta de controlo/baseline não documentada; não é
prejudicial, mas ninguém explica o seu propósito nos ficheiros do projeto encontrados.

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Decidir o destino do arquivo PIT** (a pergunta em aberto desde julho — ver Finding ALTO #4).
   Isto desbloqueia tudo o resto: se a resposta for "arquivar", os passos de limpeza fazem-se uma
   vez só; se for "continuar a acumular para vender/testar", então os timers ficam e só falta
   limpar o resto. Ver `docs/plans/2026-08-24_plano_fixes.md` passo 1.
2. **Consolidar os dois frontends** (Finding ALTO #2) — baixo risco, reversível, resolve confusão
   operacional imediata.
3. **Limpar disco Docker** (Finding MEDIO #6) — grátis, sem risco, recupera >30 GB.
4. **Arrumar resíduos no root** (Finding BAIXO #8) — cosmético mas rápido.
5. Findings #5, #7, #9 — baixa prioridade, documentar e não agir sem necessidade.

## (f) Riscos se nada for feito

- **Nenhum risco de perda de dinheiro real** — trading ao vivo está travado em 3 camadas
  (`ibgateway` desligado, `LIVE_AUTO_REBALANCE` off, guarda de pré-voo de ordens em
  `order_preflight.py` bloqueia qualquer submissão fora do allowlist/limites). Confirmado
  `ib_orders=0`/`ib_trades=0` nesta sessão.
- **Risco real = desperdício continuado de atenção e disco.** Cada semana que passa sem decisão
  é mais um backtest semanal (1h+ CPU), mais um backup noturno, mais 11 linhas no arquivo PIT —
  tudo a compor um ativo cujo destino ninguém decidiu. Se esta acumulação continuar indefinidamente
  sem nunca ser usada, é puro custo de oportunidade (compute + espaço + risco de dependência
  esquecida) sem contrapartida.
- **Risco de confusão operacional:** dois frontends vivos podem levar a olhar para dados
  desatualizados/errados sem se aperceber.
- **Risco de esta auditoria também ser ignorada como a anterior foi.** Se o padrão do Finding
  ALTO #1 se repetir, a próxima auditoria (dentro de mais 1-2 semanas, pelo padrão observado)
  vai encontrar exatamente os mesmos 5 problemas triviais ainda por resolver.

## (g) Glossário

- **API (Application Programming Interface)** — a "porta" por onde dois programas trocam
  informação, por exemplo o robô perguntar à IB "qual é o saldo da conta?".
- **MCP (Model Context Protocol)** — uma ligação que permite a um assistente de IA falar
  diretamente com um serviço externo; aqui usada para ler o saldo real da conta IB.
- **Backtest** — simular "se eu tivesse seguido esta estratégia no passado, ganhava ou perdia
  dinheiro?", usando dados históricos, sem risco real.
- **Paper trading** — fingir que compras e vendes ações, com dinheiro que não existe, para testar
  se o sistema funciona sem risco real.
- **PIT (point-in-time)** — guardar uma "fotografia" dos dados exatamente como estavam num certo
  dia, para nunca poderes fazer batota usando informação que só existiu depois (informação do
  futuro).
- **Alfa vs Beta** — alfa é o ganho que vem de escolheres bem (competência real); beta é o ganho
  que vem só de o mercado em geral ter subido. Uma estratégia "só beta" não vale nada extra além
  de comprar um índice barato.
- **Deflated Sharpe Ratio** — um teste estatístico que pune o facto de teres experimentado muitas
  estratégias diferentes; quanto mais tentas, maior a hipótese de uma parecer boa só por sorte.
- **Sharpe Ratio / Sortino Ratio** — medem o "ganho por unidade de risco"; Sortino só conta o
  risco de perdas (ignora a variação positiva).
- **Drawdown** — a maior queda desde um pico até um vale seguinte numa curva de dinheiro.
- **Docker / container** — uma "caixa" isolada onde um programa corre com tudo o que precisa,
  sem mexer no resto do computador.
- **systemd timer** — o despertador do próprio computador Linux que dispara uma tarefa a uma hora
  marcada.
- **Conductor / Domain Manager / plano / fase** — o sistema que o José usa para gerir trabalho
  longo de agentes de IA; um plano tem fases com regras exatas de quando se pode considerar
  "feito" (o "oráculo de aceitação").
- **ECC (independent auditor/reviewer no Conductor)** — um agente separado que verifica de forma
  independente se um trabalho realmente cumpre o que diz cumprir, antes de ser aceite como
  "feito".
- **13F** — um relatório trimestral que grandes fundos de investimento nos EUA são obrigados a
  publicar, mostrando o que compraram e venderam.
- **RIA (Registered Investment Adviser)** — o estatuto legal nos EUA que uma empresa precisa de
  ter se gerir dinheiro de terceiros automaticamente por uma taxa; tem obrigações regulatórias
  pesadas.
