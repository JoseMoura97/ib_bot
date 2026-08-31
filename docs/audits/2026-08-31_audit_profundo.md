# Audit Profundo — IB Bot (2026-08-31, ART / 2026-08-31 03:xx -03)

> Sessão de auditoria: `/home/servidor/agent-workspaces/mega-audit-2026-08-31`.
> Todos os comandos abaixo foram corridos NESTA sessão (ground truth re-verificado, não copiado
> de memória nem de auditorias anteriores). Esta é a **4ª auditoria profunda** deste projeto
> (depois de 2026-07-12, 2026-07-20/2026-08-10, 2026-08-17 e 2026-08-24) — sempre no mesmo
> repositório, sempre no mesmo formato.

## (a) O que é este projeto (para um miúdo de 12 anos)

O **IB Bot** é um robô de computador que devia comprar e vender ações sozinho, usando a conta
de trading do José na **Interactive Brokers (IB — a corretora, a empresa que executa as ordens
de compra/venda na bolsa)**. A ideia era copiar o que "gente esperta" faz — políticos dos EUA
quando compram ações, fundos famosos (como o de Warren Buffett) quando publicam os seus
relatórios trimestrais, gestores que apostam contra empresas (Michael Burry) — e ver se copiar
essas jogadas dá dinheiro.

O robô testou **56 ideias diferentes** ("estratégias") em dados históricos, com um motor de
**backtest** (simular "se eu tivesse seguido esta regra no passado, ganhava ou perdia?"). Tem
três peças vivas:
1. **Motor de backtest** — testa ideias no passado, de graça, sem risco. Corre sozinho todas as
   semanas (domingo de madrugada).
2. **Motor de execução real** — a peça que manda ordens verdadeiras para a IB. Está **desligada**
   desde julho de 2026 por decisão do José ("dormência seletiva").
3. **Arquivo "ponto-no-tempo" (PIT — point-in-time)** — desde 13 de julho de 2026, o robô tira
   uma "fotografia" todos os dias de 11 fontes de dados públicas e guarda-a para sempre, mesmo
   que a fonte original mude depois. Isto é valioso porque nunca mais se pode reconstruir esse
   dia exatamente como estava — ou se guarda agora, ou perde-se para sempre.

Há ainda um **"paper trading"** (fingir que compra/vende ações com dinheiro que não existe, para
testar o sistema sem risco) que corre TODOS OS DIAS sozinho — isto é novo relativamente ao que
as auditorias anteriores documentaram em detalhe: confirma-se nesta sessão que existe uma tarefa
diária automática (`paper_rebalance_daily_task`) que atualiza a "carteira de mentira" da conta 2,
e é essa tarefa que produziu a curva de equity de ~90 dias analisada na secção de métricas.

O projeto está marcado como **PAUSED (pausado)** no sistema de gestão de projetos do José (o
Conductor), mas isso significa "não se decide o próximo grande passo de negócio" — não significa
"desligado". Há vários processos automáticos a correr todos os dias sozinhos (ver secção (c)).

## (b) Evolução até hoje (timeline, com datas verificadas)

Fonte: `git log` completo do repositório `/home/servidor/Desktop/cursor-projects/ib_bot` (222
commits, primeiro commit `2026-01-17`, comando `git log --oneline | wc -l` corrido nesta sessão)
+ memórias em `/home/servidor/.claude/projects/-home-servidor/memory/` + as 4 auditorias
anteriores no mesmo diretório (`docs/audits/2026-07-12_*`, `2026-07-20_*`, `2026-08-10_*`,
`undefined_audit_profundo.md` de 08-17, `2026-08-24_audit_profundo.md`).

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repositório. |
| 2026-01 a 2026-04 | Construção inicial: motor de backtest, catálogo de estratégias, execução IB, frontend. |
| 2026-05 (18 commits) | Auditoria de investibilidade v1→v4 (memória `project_ib_bot_audit.md`): v1 mostra que o "alfa" (ganho acima do mercado) das estratégias populares é na verdade **beta** (só sobem porque o mercado sobe). v2 corrige o erro e encontra ~5 estratégias com alfa positivo não-deflacionado. v3 mede **decaimento do sinal**: as estratégias mais populares (Congress Buys, Burry) perderam força desde que ETFs como a NANC começaram a copiar o mesmo truque publicamente em 2023. v4 (AUTORITATIVA) aplica o **Deflated Sharpe Ratio** (teste que pune ter experimentado 56 ideias): **NENHUMA das 56 passa**. Recomendação: vender o motor de dados, não o "alfa". |
| 2026-05-23 | Estudo irmão PEAD (Post-Earnings Announcement Drift, repo `trading`) é **REJEITADO** — mesma conclusão: beta, não alfa (696 configurações testadas, melhor resultado inverteu no holdout). |
| 2026-05-26 | Início da série de `paper_snapshots` das duas contas de paper trading (conta 1 = controlo parado em $100k; conta 2 = carteira ativa) — confirmado nesta sessão, é a data mínima da tabela. |
| 2026-07-12/13 | **Decisão de negócio do José: dormência seletiva.** Gateway IB (`ibgateway.service`, `xvfb-ibgw.service`) desligados — zero sessões live diárias. Arranca o arquivo diário PIT (`altdata_snapshots`). Plano Conductor `e36e04ec` criado com 8 fases. |
| 2026-07-16 | Estudo irmão **earnings-vol / "Iron Wing" (0006)** é **MORTO** (memória `project_earnings_vol.md`): gate pré-registado de 36 eventos forward atingido — profit factor a preço médio 0.776, a preço de toque real 0.256, ambos <1 → perde dinheiro. Zero compra de ThetaData, zero capital real. |
| 2026-07-18/19 | Fases f2/f4 do plano `e36e04ec` fecham. Hardening de memória do backtest semanal depois de 2 kills por `systemd-oomd`. |
| 2026-08-05 a 08-13 | Plano Conductor `04bf8af8` "Alt-data PIT archive hardening" — backup noturno offsite, separação de dono na DB (papel `ibbot` perde superuser — corrige um CRITICO real), guarda de pré-voo de ordens (`order_preflight.py`). |
| 2026-08-14 a 08-20 | Fase H3 — prova de "opera sem agente humano" — soak de 3 disparos autónomos do timer diário. Plano `04bf8af8` fecha `done` a 08-20. |
| 2026-08-17 | Auditoria (commit `1da63d3`) recomenda 5 passos. **Nenhum executado até hoje.** |
| 2026-08-24 | Auditoria seguinte (commit `7e1aed8`) repete os mesmos 5 achados, produz 2º plano de fixes com aviso explícito: "se este plano também não for executado, é sinal de que ninguém está a agir sobre as auditorias — reportar ao José, não escrever um 6º plano idêntico." **Também não foi executado** (ver Finding CRITICO #1 abaixo). |
| 2026-08-27 20:16-20:54 WEST | **Teste manual e deliberado do IB Gateway**, feito a pedido do José ("Entao siga avançar, eu estou no telemovel", ledger `ib_bot:ibgateway_session`, decisão `e429220b`) para responder à pergunta "consegues colocar ordens na minha conta IB?". Confirmado por `journalctl`+`sudo` log: `systemctl start xvfb-ibgw` e `ibgateway` às 20:16, 2FA (autenticação de dois fatores) automática falhou uma vez ("code rejected"), serviço foi parado 37 min depois às 20:54. Conclusão registada em memória (`reference_ibkr_order_access_paths.md`): o gateway do ib_bot está em `ReadonlyLogin=yes` (não pode submeter ordens mesmo se ligado) E autentica-se numa conta errada (`U23842862`, não a pessoal `U15721390`) — **duplo bloqueio deliberado**. O script `verify_f1_dormencia_seletiva.sh` confirmou `RESULT FAIL failures=3` com o gateway ligado e `RESULT PASS failures=0` depois de o voltar a desligar — a invariante de dormência foi reprovada durante o teste e reposta corretamente no final. Nenhuma ordem foi submetida (o único caminho que consegue mesmo colocar ordens é o conector MCP `claude.ai IBKR`, cuja ferramenta `create_order_instruction` só gera um link para o José clicar — nunca submete sozinha). |
| 2026-08-24 a 2026-08-31 (últimos 7 dias) | Repositório recebeu **14 commits, todos 100% automáticos** (7× backup noturno do arquivo PIT, 7× recibo de QA diária) — comando `git log --oneline 7e1aed8..HEAD`. Arquivo PIT cresceu de 471 para **548 linhas** (43→50 dias distintos). Nenhuma linha de código, nenhuma decisão humana, nenhum commit manual nesta janela. |
| 2026-08-31 (hoje) | Este audit — **3ª vez consecutiva** que o mesmo plano de 5 passos de limpeza/decisão é encontrado por fazer. |

## (c) Estado concreto HOJE (verificado nesta sessão)

### Repositórios
- `/home/servidor/Desktop/cursor-projects/ib_bot` — repo git ativo (`main`), **222 commits**
  (`git log --oneline | wc -l`), **14 commits desde a auditoria anterior (08-24)**, todos
  automáticos. `git log -1`: commit `c430603` "backup(altdata): PIT table 20260831T033239Z",
  hoje 04:32 WEST.
- `/home/servidor/Desktop/cursor-projects/ib_bot-v2` — worktree secundário na branch
  `frontend-v2` (`git worktree list` confirma), serve o systemd `ib-bot-v2-frontend.service`.
  Continua "vivo" (ver frontends abaixo), não é lixo morto.
- O path `ib_bot-altdata-wt` citado no brief **não existe** (`ls` deu erro "No such file or
  directory") — confirmado por auditorias anteriores como worktree temporário já removido.

### Serviços systemd (comando: `systemctl status <unit>` corrido nesta sessão)
| Unit | Estado | Nota |
|---|---|---|
| `ibgateway.service` | `inactive (dead)`, `disabled` | Parado desde 2026-08-27 20:54 WEST (ver timeline — teste manual autorizado, reposto corretamente). Comportamento esperado hoje. |
| `xvfb-ibgw.service` | `inactive (dead)`, `disabled` | Idem. |
| `ib-bot-v2-frontend.service` | `active (running)` há 2 semanas 6 dias, porta 3001 | Fala com a API v1 real (:8001). `curl localhost:3001` → `307` (vivo). |
| `ib-altdata-qa.timer` / `.service` | `active (waiting)` / último disparo 08-30 08:00 WEST, sucesso | Do ib_bot. QA diária do arquivo PIT. |
| `ib-altdata-backup.timer` / `.service` | `active (waiting)` / último disparo hoje 04:33 WEST, sucesso | Do ib_bot. Backup offsite noturno. |
| `ib-backtests.timer` / `.service` | `active (waiting)` / último disparo 08-30 05:16→06:09 WEST, sucesso | Do ib_bot. Backtest semanal completo (56 estratégias). Próximo disparo: 06-09 05:15 WEST. |
| `theta-terminal.service` | `active (running)` há 2 semanas 6 dias, 739 MB RAM (pico histórico 6,8 GB + 6,5 GB swap) | Serve dados de opções para `theta-learned.timer` — **é do projeto Polymarket**, confirmado pela descrição literal da unit. No código do ib_bot só é referenciado por 2 scripts do estudo morto Iron Wing. |
| `lifeos-ib-refresh.timer` / `.service` | `active (waiting)`, dispara de 2h em 2h, sucesso | **NÃO é do ib_bot** — é do projeto `lifeos`, atualiza o saldo da conta IB pessoal do José via MCP para o "net worth" dele. Só lê, nunca escreve na DB do ib_bot. Mencionado aqui porque toca na mesma conta IB. |
| `execution-metrics.timer`, `cost-recalibration.timer`, `historical-backfill.timer`, `paper-ironfly.timer` | `active (waiting)` | **NÃO são do ib_bot** — confirmado pelas descrições literais das units: Polymarket (`execution-metrics`, `cost-recalibration`, `historical-backfill`) e projeto irmão `trading` (`paper-ironfly`, iron-fly de agosto). `historical-backfill.service` está hoje em estado `failed` (falha histórica), mas é 100% Polymarket — fora do escopo deste audit, não afeta nada do ib_bot. |

Confirma-se de novo: **3 timers são do ib_bot** (`ib-altdata-qa`, `ib-altdata-backup`,
`ib-backtests`); os restantes citados no brief pertencem a outros projetos.

### Stack Docker (comando: `docker ps -a --filter name=ib_bot`)
```
ib_bot-api-1        Up 2 weeks    0.0.0.0:8001->8000/tcp
ib_bot-beat-1       Up 2 weeks
ib_bot-worker-1     Up 2 weeks
ib_bot-db-1         Up 2 weeks    5432/tcp (não exposta ao host)
ib_bot-redis-1      Up 2 weeks
ib_bot-web-1        Up 2 weeks    3000/tcp
ib_bot-nginx-1      Up 2 weeks    0.0.0.0:8090->80/tcp
ib_bot-web-lint-1   Exited (0) 2 months ago
```
`curl localhost:8001/health` → `200`. `curl localhost:8090` → `200`. `curl localhost:3001` →
`307`. **Continuam dois frontends vivos ao mesmo tempo** — mesmo finding da 3ª auditoria
seguida, ainda não resolvido.

`docker system df`: **32,36 GB de imagens, 100% reclamáveis** (21 imagens) — número
byte-a-byte idêntico ao medido em 08-24, confirmando que ninguém correu o passo 3 do plano
anterior.

### Processo interno do bot (celery beat/worker, `docker logs ib_bot-beat-1`/`-worker-1`)
Confirmado nesta sessão (logs das últimas 24-48h): o beat dispara `reconcile_stuck_runs_task` e
`reconcile_stuck_executions_task` de 5 em 5/10 em 10 min (housekeeping interno, sem efeito
externo), e às 06:00 UTC diariamente dispara **duas tarefas de negócio**:
1. `altdata_snapshot_daily_task` — captura as 11 fontes do arquivo PIT. Log de hoje (08-31)
   confirma `overall_status: ok`, `successful_sources: 11/11`, incluindo a nota que
   `quiver_congress_trades` continua excluído (precisa de acesso pago/API-key, sem substituto
   silencioso — decisão de qualidade de dados correta).
2. `shadow_preview_task` — pré-visualização "sombra" (não executa nada real).
Não há tarefa `paper_rebalance_daily_task` visível nos últimos logs de 24-48h analisados neste
excerto, mas o schedule (`backend/app/worker/celery_app.py:41-42`) regista-a como tarefa diária
e a evolução dos `paper_snapshots` (ver abaixo) confirma que ela produz uma linha nova quase
todos os dias.

### Base de dados (Postgres dentro de `ib_bot-db-1`, acesso `docker exec ib_bot-db-1 psql -U ibbot -d ibbot`)
- `ib_orders` = **0**, `ib_trades` = **0**, `live_execution_requests` = **0** — confirma **zero
  ordens reais desde sempre**, mesmo depois do teste do gateway de 08-27 (que tinha
  `ReadonlyLogin=yes`, não podia submeter nada de qualquer forma).
- `live_rebalance_audit` = 25 linhas (inalterado desde maio — 17 dry-run + 8 preview, nunca um
  execute real).
- `altdata_snapshots` = **548 linhas**, 50 dias distintos, `2026-07-13` a `2026-08-31`, 11 fontes
  (CFTC, FINRA, FRED, House disclosure ×2, SEC ×2, Nasdaq, USAspending, 13F Berkshire, 13F Scion,
  + série de preços "iron_wing_equity_daily_bars" residual do estudo morto). Cresceu 77 linhas
  desde 08-24 (471→548), ritmo de ~11/dia mantido. Gatilho `altdata_snapshots_reject_mutation`
  confirmado ativo (tabela é append-only por desenho).
- `paper_snapshots`: 2 contas, **98 registos cada** (era 91 em 08-24), `2026-05-26` a
  `2026-08-30`.
  - Conta 1 (`account_id=1`): sempre `cash=equity=$100.000` nas 98 linhas — conta de controlo
    parada, confirmado de novo nesta sessão. Continua sem documentação do seu propósito.
  - Conta 2 (`account_id=2`): equity de **$177.973,30** (26 mai) para **$185.671,72** (30 ago) —
    ~97 dias de dinheiro FINGIDO (paper trading). Ver métricas completas em `metrics.json`
    (fonte: `docker exec ib_bot-db-1 psql -U ibbot -d ibbot -t -A -F"," -c "select account_id,
    timestamp::date, cash, equity from paper_snapshots where account_id=2 order by timestamp
    asc;"`).
- `paper_trades` (conta 2) = 138 registos, **inalterado desde maio** (`max(timestamp)` =
  2026-05-09) — confirma que o ganho de equity vem de reavaliação de posições existentes +
  rebalanceamentos periódicos, não de novos trades individuais registados.

### Conta real na Interactive Brokers (via MCP `get_account_summary` / `get_account_positions`,
consultado nesta sessão)
- **Valor líquido: EUR 27.248,34** (era EUR 26.550,79 em 08-24 — subida de mercado normal, BRK B
  a US$505/ação hoje vs. custo médio US$490,96).
- Posição única: **70 ações BRK B** (Berkshire Hathaway), valor de mercado USD 35.350,
  ganho não realizado +USD 982,85.
- Esta é uma **posição pessoal do José**, comprada manualmente — o robô nunca lá tocou
  (confirmado por `ib_orders=0`/`ib_trades=0`, mesmo depois do teste do gateway de 08-27).
- `lifeos-ib-refresh.timer` (projeto separado, `lifeos`) atualiza este mesmo saldo de 2 em 2h
  para o "net worth" pessoal do José — última leitura bem-sucedida hoje às 03:15 WEST:
  `net_liq: 27240.60`. Não é o ib_bot a fazer isto, mas confirma consistência entre as duas
  leituras (MCP direto vs. `lifeos`).

### Planos do Conductor (comando: `psql conductor -c "SELECT id,status,title FROM project_plans WHERE slug='ib_bot' ORDER BY id"`)
| Plano | Status | Nota |
|---|---|---|
| `04bf8af8` — Alt-data PIT archive hardening | **done** | Fechado 2026-08-20, sem alterações desde então. |
| `e36e04ec` — pós-triagem 2026-07-12 | **paused** | Fase `a1_altdata_b2b` continua em HOLD explícito: "NÃO reabrir, NÃO voltar a cardar, NÃO fazer qualquer contacto comercial." Sem alterações desde 08-24. |
| `3702771c` — ib_bot → Alt-Data Product | **superseded** | Sem alterações. |

Nenhum plano novo foi criado para o ib_bot desde a última auditoria — confirma que a frota do
Conductor também não está a agir sobre as recomendações.

## (d) Findings, ordenados por gravidade

### CRITICO

**#1 — TRÊS auditorias seguidas (08-17, 08-24, 08-31) recomendaram o MESMO plano de 5 passos,
NENHUM foi executado.** Isto deixou de ser um finding operacional normal (ALTO, como estava
classificado em 08-24) e passa a CRITICO porque o padrão em si é a falha mais importante do
projeto: nenhum humano nem agente está a fechar o loop entre "auditoria escreve recomendação" e
"alguém age". Evidência: `docs/plans/undefined_plano_fixes.md` (08-17) e
`docs/plans/2026-08-24_plano_fixes.md` (08-24) têm os mesmos 5 passos; verificado nesta sessão
que os 5 continuam por fazer byte-a-byte:
1. Decisão do José sobre o destino do arquivo PIT — nenhuma memória nova encontrada
   (`grep -rl ib_bot ~/.claude/projects/-home-servidor/memory/` só mostra ficheiros já conhecidos
   de auditorias anteriores + a memória `reference_ibkr_order_access_paths.md` de 08-27, que é
   sobre acesso a ordens, não sobre o destino do arquivo).
2. Dois frontends continuam ambos vivos (`curl` confirma 3001 e 8090 os dois a responder).
3. `docker system df` mostra os mesmos **32,36 GB** de imagens reclamáveis, número idêntico ao
   de 08-24 até à segunda casa decimal — prova direta de que ninguém correu `docker image prune`.
4. `$LOG` (765 KB), `alembic_validation.db` (86 KB), os 3 `backtest_results_*.json` (3,3 MB) e o
   `docker-compose.prod.yml.bak.1778273314` continuam na raiz (`ls -la` confirmado nesta sessão,
   mesmas datas de modificação de maio/janeiro que em 08-24 — ninguém tocou neles).
5. A conta paper 1 continua sem documentação do seu propósito (91→98 snapshots idênticos, mais 7
   dias de "não-explicação").

**O que isto significa na prática:** o ciclo de auditoria quinzenal está a gerar trabalho
(3 relatórios, 3 planos, ~15 páginas de recomendações) sem qualquer retorno — é esforço
desperdiçado se ninguém lê ou decide. Ver plano de fixes (`2026-08-31_plano_fixes.md`) passo 0,
que trata este finding como prioridade máxima antes de repetir qualquer passo de limpeza.

### ALTO

**#2 — Dois frontends web vivos ao mesmo tempo, sem necessidade clara (repetido pela 3ª vez).**
`curl localhost:3001` → `307` (systemd `ib-bot-v2-frontend.service`, fala com a API v1 real
:8001). `curl localhost:8090` → `200` (Docker `nginx-1`+`web-1`, stack completa incluindo API/
worker/beat/db/redis próprios, rodando há 2 semanas). Ambos consomem recursos (RAM + CPU do
stack Docker inteiro só para servir uma segunda cópia do frontend).

**#3 — Nenhuma das 56 estratégias tem edge robusto, confirmado repetidamente (inalterado desde
maio).** Deflated Sharpe Ratio (teste que pune ter testado 56 ideias diferentes) reprova as 56;
os 2 "sobreviventes" pré-deflação (Transportation Committee, House Long-Short) dependiam de 1-2
meses de sorte. O estudo irmão earnings-vol (0006) morreu no gate de 36 eventos forward. O
estudo irmão PEAD morreu com 7 testes independentes convergentes. **Três tentativas de encontrar
edge, três kills — e nenhuma quarta tentativa em curso.**

**#4 — Engenharia continua a ser gasta todos os dias num arquivo de dados sem uso decidido.** O
arquivo PIT (`altdata_snapshots`) cresceu de 471→548 linhas desde 08-24 (77 linhas em 7 dias) e
vai continuar a crescer sozinho, mas a decisão de negócio sobre para que serve (vender B2B?
testar mais estratégias? arquivar?) continua formalmente em HOLD desde julho — agora há **8
semanas** sem decisão desde que a triagem original a suspendeu.

### MEDIO

**#5 — `theta-terminal.service` sempre ligado, pico histórico de 6,8 GB RAM + 6,5 GB swap.**
Confirmado nesta sessão: só é consumido pelo timer `theta-learned` (Polymarket) e por 2 scripts
do estudo Iron Wing já morto no ib_bot. Não é um problema do ib_bot per se, mas o ib_bot não
precisa dele.

**#6 — 32,36 GB de imagens Docker reclamáveis, 21 imagens (inalterado byte-a-byte desde 08-24).**

**#7 — Container `ib_bot-web-lint-1` parado há ~2 meses, nunca limpo.**

### BAIXO

**#8 — Resíduos na raiz do repositório, inalterados desde 08-17 (3ª auditoria seguida a
encontrá-los).** `$LOG` (765 KB), `alembic_validation.db` (86 KB), `backtest_results_2026_05_12
.json` + `_corrected.json` + `_final.json` (3,3 MB), `docker-compose.prod.yml.bak.1778273314`.

**#9 — Conta paper 1 (id=1) fica sempre em $100.000, sem documentação de propósito (98
snapshots idênticos, 3ª auditoria a repetir o achado).**

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Resolver o Finding CRITICO #1 primeiro — não outro plano de limpeza.** Ver
   `docs/plans/2026-08-31_plano_fixes.md` passo 0: apresentar ativamente ao José (não esperar que
   ele leia um documento) a pergunta de continuidade + o facto de 3 auditorias seguidas terem
   sido ignoradas, e obter uma resposta explícita registada em memória. Sem isto, os passos 2-5
   deste plano de fixes vão ser encontrados por fazer numa 4ª auditoria (previsivelmente por
   volta de 2026-09-07/14).
2. **Consolidar os dois frontends** (Finding ALTO #2) — baixo risco, reversível.
3. **Limpar disco Docker** (Finding MEDIO #6) — grátis, sem risco, recupera >30 GB.
4. **Arrumar resíduos no root** (Finding BAIXO #8) — cosmético mas rápido.
5. Findings #5, #7, #9 — baixa prioridade, documentar e não agir sem necessidade.

## (f) Riscos se nada for feito

- **Nenhum risco de perda de dinheiro real hoje.** Trading ao vivo está travado em 3 camadas
  (`ibgateway` desligado, `LIVE_AUTO_REBALANCE` off, guarda de pré-voo de ordens em
  `order_preflight.py`), e o teste manual de 08-27 confirmou ainda um 4º bloqueio (o gateway do
  bot autentica-se numa conta errada, mesmo que fosse ligado). Confirmado `ib_orders=0`/
  `ib_trades=0` nesta sessão, mesmo depois desse teste.
- **Risco real = desperdício continuado de atenção, disco e confiança no processo de
  auditoria.** Cada semana que passa sem decisão é mais um backtest semanal (1h+ CPU), mais um
  backup noturno, mais ~11 linhas no arquivo PIT — tudo a compor um ativo cujo destino ninguém
  decidiu. Pior: o próprio mecanismo de auditoria (este relatório) está a perder valor a cada
  ciclo que é ignorado — se a 4ª auditoria também encontrar os mesmos 5 problemas, o custo de
  oportunidade passa a incluir o tempo gasto a escrevê-las.
- **Risco de confusão operacional:** dois frontends vivos podem levar a olhar para dados
  desatardos/errados sem se aperceber.
- **Risco de "fadiga de auditoria":** se o José continuar a não ver/agir sobre estes relatórios,
  o valor do próximo ciclo cai para perto de zero — é preferível reduzir a cadência ou mudar o
  canal de entrega do que continuar a produzir relatórios idênticos que não são lidos.

## (g) Glossário

- **API (Application Programming Interface)** — a "porta" por onde dois programas trocam
  informação, por exemplo o robô perguntar à IB "qual é o saldo da conta?".
- **MCP (Model Context Protocol)** — uma ligação que permite a um assistente de IA falar
  diretamente com um serviço externo; aqui usada para ler o saldo real da conta IB e para
  preparar (nunca submeter) ordens.
- **2FA (autenticação de dois fatores)** — um código extra (para além da password) que confirma
  que és mesmo tu a entrar numa conta; aqui gerado automaticamente por um script (`auto2fa.py`).
- **Backtest** — simular "se eu tivesse seguido esta estratégia no passado, ganhava ou perdia
  dinheiro?", usando dados históricos, sem risco real.
- **Paper trading** — fingir que compras e vendes ações, com dinheiro que não existe, para testar
  se o sistema funciona sem risco real.
- **PIT (point-in-time)** — guardar uma "fotografia" dos dados exatamente como estavam num certo
  dia, para nunca poderes fazer batota usando informação que só existiu depois.
- **Alfa vs Beta** — alfa é o ganho que vem de escolheres bem (competência real); beta é o ganho
  que vem só de o mercado em geral ter subido.
- **Deflated Sharpe Ratio** — um teste estatístico que pune o facto de teres experimentado muitas
  estratégias diferentes; quanto mais tentas, maior a hipótese de uma parecer boa só por sorte.
- **Sharpe Ratio / Sortino Ratio** — medem o "ganho por unidade de risco"; Sortino só conta o
  risco de perdas (ignora a variação positiva).
- **Drawdown** — a maior queda desde um pico até um vale seguinte numa curva de dinheiro.
- **VaR (Value at Risk) a 95%** — uma estimativa de "no pior dia entre 20, quanto podes perder"
  olhando para o histórico de retornos.
- **Docker / container** — uma "caixa" isolada onde um programa corre com tudo o que precisa,
  sem mexer no resto do computador.
- **systemd timer** — o despertador do próprio computador Linux que dispara uma tarefa a uma hora
  marcada.
- **Celery beat/worker** — um "relógio" (beat) que dispara tarefas periódicas dentro da própria
  aplicação, e um "trabalhador" (worker) que as executa — diferente do systemd timer, que é do
  sistema operativo; aqui os dois coexistem (systemd para tarefas do host, celery para tarefas
  dentro do container Docker).
- **Conductor / Domain Manager / plano / fase** — o sistema que o José usa para gerir trabalho
  longo de agentes de IA; um plano tem fases com regras exatas de quando se pode considerar
  "feito" (o "oráculo de aceitação").
- **13F** — um relatório trimestral que grandes fundos de investimento nos EUA são obrigados a
  publicar, mostrando o que compraram e venderam.
- **RIA (Registered Investment Adviser)** — o estatuto legal nos EUA que uma empresa precisa de
  ter se gerir dinheiro de terceiros automaticamente por uma taxa; tem obrigações regulatórias
  pesadas.
