# Audit profundo — IB Bot (slug: ib_bot) — 2026-07-12

Auditor: agente Fable (modo ultracode), sessão read-only (só leitura em sistemas; as únicas
escritas foram estes ficheiros de documentação). Todos os factos abaixo foram RE-VERIFICADOS
nesta sessão em 2026-07-12 (madrugada/manhã, hora ART = UTC-3); cada claim tem ao lado o
comando ou ficheiro que o prova.

---

## (a) O que é este projeto — explicado como para um miúdo de 12 anos

O **IB Bot** é um robô de investimento em ações americanas ligado à **Interactive Brokers**
("IB" — uma corretora, ou seja, a empresa através da qual se compram e vendem ações).
A ideia dele é copiar automaticamente as compras de pessoas "bem informadas":

- **Congressistas americanos** — políticos dos EUA são obrigados por lei a declarar as ações
  que compram; o robô lê essas declarações e imita-os.
- **Gestores de fundos famosos** (Michael Burry, Buffett, etc.) — através dos formulários
  **13F** (um relatório trimestral que os grandes fundos são obrigados a entregar ao regulador
  SEC, a "CMVM americana", a listar tudo o que têm em carteira).
- **Outros dados alternativos** ("alt-data" — informação que não vem dos preços, como gastos
  de lóbi, contratos do governo, compras de administradores das próprias empresas).

O robô tem três camadas:
1. **Backtests** — simular "e se eu tivesse seguido esta estratégia nos últimos anos?" com
   dados históricos (56 estratégias registadas).
2. **Paper trading** — negociar com dinheiro de mentira, para testar sem risco.
3. **Live trading** — negociar com dinheiro real na conta IB (construído, com muitas
   proteções, mas **nunca usado**: zero ordens reais até hoje — verificado na base de dados).

O projeto está oficialmente **PAUSED (pausado)** desde ~final de junho de 2026, depois de um
audit próprio (v4, 2026-05-26) ter concluído que **nenhuma das 56 estratégias tem "alpha"
robusto** (alpha = ganho acima do mercado que não é sorte nem simplesmente "o mercado subiu").

---

## (b) Evolução até hoje (timeline dos gits + memórias)

| Data | Marco | Evidência |
|---|---|---|
| 2026-02-19 | Conta paper "Main Paper" criada com $100.000; primeiras paper trades | DB `ib_bot-db-1`: `paper_cash.created 2026-02-19`, `min(paper_trades.timestamp)=2026-02-19` |
| 2026-02→05-09 | 138 paper trades executadas (115 compras / 23 vendas, 88 tickers), carteira "V1 Core" | `SELECT count(*) FROM paper_trades` → 138; última 2026-05-09 |
| 2026-05-18/22 | Preparação de go-live: fractional shares, verify engine, página "Deploy", frequência de rebalance | memória `project_ib_bot.md` + commits de maio |
| 2026-05-22 | Ligação IB Gateway estabilizada (socat porta 4003); conta live do bot **U23842862** "Splits Quiver" com €1.000; API deixada em **read-only** (não pode dar ordens) | memória + `/opt/ibc/config.ini` → `ReadonlyLogin=yes` (re-verificado hoje) |
| 2026-05-23 | Estudo **PEAD** (drift pós-resultados) FECHADO: era beta de mercado, não alpha (7 testes independentes convergem) | memória `project_pead.md` |
| 2026-05-23→28 | Estudo **0006 earnings-vol** (vender volatilidade à volta de resultados): morto → reaberto com iron-fly de asas largas (held-out PF 1.42-1.78); harness de forward paper + run multi-regime lançados | memória `project_earnings_vol.md`; ficheiros em `trading/backtests/reports/0006_earnings_vol/` |
| 2026-05-26 | **Audit v4 AUTHORITATIVE**: nenhum alpha robusto em 56 estratégias (Deflated Sharpe todos <0.15); NANC ETF é mais barato para retalho <$42k; caminho recomendado = licenciar dados B2B, NÃO app de consumo; ação nº1 = **arquivar snapshots point-in-time já** | memória `project_ib_bot_audit.md` |
| 2026-05-26 | `paper_snapshots` começa a gravar equity diária (a recomendação "capturar curva" foi implementada) | DB: `min(paper_snapshots.timestamp)=2026-05-26` |
| 2026-05-28 | Run multi-regime EOD do iron-fly termina: **PF<0,4 em TODOS os anos 2019-2026** — contradiz o "survivor"; resultado nunca foi reconciliado nem registado na memória | `trading/backtests/reports/0006_earnings_vol/peryear_multiregime.txt` (mtime 2026-05-28 16:52) |
| 2026-05-31 | Plano conductor "ib_bot → Alt-Data Product" criado; hoje está **superseded** (substituído) | `psql conductor`: plano 3702771c status=superseded |
| 2026-06-05/06 | Fase alt-data: Signal Explorer UI; stack v2 isolada ("Plan B go-live") em :8092 | git log `5095bd8`, `48b73dd` |
| 2026-06-29 | Último commit real: fix Celery + validação de fontes na API | git log `25f7a6a` |
| 2026-07-04 | ibeam (2º portal de login IB) com série de tentativas falhadas de login — 712 ficheiros de screenshots/logs acumulados no repo | `ls infra/ibeam/outputs | wc -l` → 712 |
| 2026-07-12 (hoje) | Backtest semanal correu às 05:16 UTC (54 estratégias OK, 2 falhadas); melhor alpha-only Sharpe = Burry 0.65 — continua tudo abaixo da fasquia de sorte (~1.06) | `/var/log/ib-backtests.log` (timestamp 06:19 de hoje) |

---

## (c) Estado concreto HOJE (verificado 2026-07-12)

### Processos e serviços — o que ainda está LIGADO

**Do ib_bot (tudo isto corre 24/7 para um projeto pausado):**

| Unidade | Estado | O que faz | Evidência |
|---|---|---|---|
| `ibgateway.service` | **ativo, modo LIVE** | IB Gateway (o programa da corretora que dá acesso à conta). Reinicia e faz **login live todos os dias às 21:45** com um bot de 2FA (2FA = segundo código de segurança; o bot lê o código TOTP e clica no ecrã) | `systemctl status`; journal: "Started" 09/10/11-jul 21:45 |
| `xvfb-ibgw.service` | ativo | Ecrã virtual (Xvfb) onde o Gateway "desenha" a janela dele (o servidor não tem monitor) | `systemctl status` |
| `ib-socat.service` | ativo | Túnel local porta 4003→4001 para os containers falarem com o Gateway | `systemctl list-unit-files` |
| `ibgw-watchdog.service` | ativo | Vigia a porta 4001 e manda alerta se o Gateway cair | journal 09-jul: "Port 4001 unreachable… back up" |
| **x11vnc** (dentro do ibgateway) | **ativo, SEM password, aberto a todas as interfaces** | Acesso remoto ao ecrã do Gateway (`x11vnc -nopw -listen 0.0.0.0`, porta 5900) — e a firewall ufw está **inactive** | `systemctl status ibgateway` (linha do processo); `ss -tlnp` porta 5900; `ufw status` → inactive |
| `ibeam-primary` (docker) | Up 10 dias (**unhealthy** no healthcheck, mas logs dizem "authenticated") | **Segunda** sessão de login live na IB, via Client Portal (interface web da IB), usada pelo MCP do IB e pelo lifeos | `docker ps`; `docker logs ibeam-primary` |
| Stack Docker `ib_bot` (7 containers: api, worker, beat, web, nginx, db, redis) | Up 12 dias | Backend v1 + API na porta 8001, site na 8090. O beat continua a fazer snapshots paper diários | `docker ps`; `docker stats` (~1,1 GB RAM) |
| Stack Docker `ib_bot-v2` (6 containers) | Up 12 dias | Stack "Plan B" isolada na porta 8092 | `docker ps` |
| `ib-bot-v2-frontend.service` / `-public` | ativos | Frontends Next.js nas portas 3001 e 3002 | `ss -tlnp`; `systemctl is-active` |
| `ib-backtests.timer` | ativo, **semanal (dom 04:15 UTC)** | Corre as 56 estratégias (63 min, hoje: 54 OK / 2 FALHADAS); o passo final de regenerar `plot_data` é **recusado** há 9 execuções pelo guarda `api_caution` (4500 chamadas IB estimadas) | `systemctl cat ib-backtests.timer`; `/var/log/ib-backtests.log` |

**Relacionados mas de OUTROS projetos (o brief pedia para confirmar — confirmado):**

| Unidade | Pertence a | Evidência |
|---|---|---|
| `theta-learned.timer`, `historical-backfill.timer`, `execution-metrics.timer`, `cost-recalibration.timer` | **Polymarket** (polytrader-bot-master), NÃO ib_bot | `systemctl cat`: WorkingDirectory=…/polytrader-bot-master |
| `paper-ironfly.timer` + `options-cache.timer` | projeto **trading** (estudo 0006 earnings-vol — tematicamente ligado ao ib_bot, código noutro repo) | `systemctl cat paper-ironfly.service`: WorkingDirectory=…/trading |
| `theta-terminal.service` | projeto **trading** (gateway de dados de opções ThetaData) — a subscrição caiu para **FREE** (o plano pago OPTION.STANDARD $80/mês já não está ativo) | journal 11-jul: "Bundle: STOCK.FREE, OPTION.FREE, INDEX.FREE" |
| `lifeos-ib-refresh.timer` | **lifeos** (só lê o saldo IB por dia) | `systemctl cat` |

### Dados e contas

- **Conta live do bot (U23842862 "Splits Quiver")**: NUNCA negociou — `ib_orders=0`,
  `ib_trades=0` na DB (verificado hoje). `live_rebalance_audit` = 25 linhas, todas dry-run
  (17) ou preview (8), maio de 2026. Trava de segurança `ReadonlyLogin=yes` confirmada hoje
  no `/opt/ibc/config.ini` — a API do Gateway rejeita qualquer ordem.
- **Conta IB pessoal do José (via MCP)**: NLV €26.981,67, posição única 70 ações BRK B
  (~$34.560), cash −€3.281 (margem), alavancagem 1,12. Os trades reais dos últimos 90 dias
  (BRK B, NVDA, MOD, LIN, MSTR, ações chinesas, FWONK — ordens STOP) **não são do ib_bot**
  (o ib_bot nunca emitiu ordens; padrão é de outro sistema/manual). Evidência: MCP
  `get_account_summary`/`get_account_positions`/`get_account_trades` hoje.
- **Paper trading**: conta 2 "Main Paper" — equity hoje $177.517 (cash $36.892 + 88 posições
  ~$140.6k, custo base $137.1k → só +2,5% acima do custo). Snapshots diários desde 26-mai:
  47 pontos, essencialmente FLAT (−$457 no período, maxDD −4,7%). ⚠️ o "ganho" aparente
  100k→177k inclui um delta de caixa de **+$70.000 redondos que não fecha** com as trades
  registadas (ver finding M1). Conta 1 parada nos $100.000 (alocação de $10k a "A — Hedge
  Fund Mirror" em 22-mai nunca gerou trades).
- **`altdata_snapshots` = 0 linhas** — a tabela existe mas a ação nº1 do audit v4 (arquivar
  vintages ponto-no-tempo, o único "moat") nunca começou a gravar. `live_shadow_snapshots`
  também 0.
- **Repos**: `ib_bot` (main repo, branch atual `snapshots-exec-fixes`, último commit real
  29-jun) + worktrees `ib_bot-v2` (frontend-v2) e `ib_bot-altdata-wt` (alt-data-consolidation).
  Árvore suja: **357 ficheiros** untracked/modificados, quase todos lixo do ibeam
  (screenshots de logins falhados). Remote: github.com/JoseMoura97/ib_bot.
- **Conductor**: projeto `ib_bot` ainda marcado `active` na tabela projects; único plano
  (Alt-Data Product) está `superseded`. Nenhum plano ativo → o audit não duplica trabalho
  da frota.
- **VMs**: nenhuma VM (máquina virtual) pertence ao ib_bot.

### Estudos — o que concluíram (com números)

1. **Catálogo de 56 estratégias (core do ib_bot)** — audit v4 (2026-05-26, AUTHORITATIVE):
   **nenhum alpha robusto**. Com Deflated Sharpe (correção de Bailey/López-de-Prado para
   "tentei 36 vezes, alguma ia parecer boa por sorte"; fasquia ~1.06): todos <0.15. Run
   fresco de HOJE confirma: melhor alpha-only Sharpe = Michael Burry 0.653, Transportation
   Committee 0.617, resto ≤0.28 — tudo abaixo da fasquia da sorte. Estratégias populares
   decaíram desde fev-2023 (lançamento dos ETFs NANC/KRUZ): Congress Buys Sharpe 1.03→0.21,
   Burry 0.78→−0.10.
2. **PEAD (estudo 0005)** — REJEITADO/fechado 2026-05-23: o "drift pós-resultados" era
   **beta** (exposição ao mercado), não alpha. Placebo de entradas aleatórias empata
   (Sharpe 0.89 vs 0.87); hedged com SPY dá alpha t=+0.07 ≈ zero; sweep 35 células todas
   ≤0; busca agressiva 696 configs deu t=3.24 in-sample que **virou negativo no holdout**
   (overfit de manual). $0 gastos. Infra de event-study reutilizável ficou feita.
3. **Earnings-vol / iron-fly (estudo 0006)** — estado AMBÍGUO (o mais importante para
   decidir):
   - Sweep intraday com dados reais ThetaData (2026-05-27): iron-fly de asas largas (10%),
     segurar até ao fecho: TRAIN PF 1.35 / held-out **PF 1.78** (slip 0.10) e **PF 1.42**
     (slip 0.25), win 62% — único candidato "vivo". MaxDD brutal (40-75%).
   - MAS o run multi-regime EOD (2026-05-28, para validar 2019-2026): **PF 0.06-0.37 em
     TODOS os anos** (e straddle PF 0.49-0.89 todos <1) — resultado nunca reconciliado com
     o sweep; a memória ficou parada em "reopened survivor". Provável causa: quotes EOD
     (fim-de-dia) das asas OTM são lixo com slippage 0.25, vs quotes intraday reais — mas
     isso é uma HIPÓTESE por provar, não um facto.
   - Forward paper test (paper-ironfly.timer, diário desde 28-mai): **0 eventos registados
     em 6 semanas** — o ledger nem existe. Funnel de ontem: 19 earnings → 16 "not_in_snap_universe"
     + 3 "no_entry_legs" → 0. O universo do snapshot cache não cobre os nomes com earnings.
   - ThetaData caiu para FREE tier → já não há dados intraday para repetir/estender o sweep
     sem re-subscrever ($80/mês).

---

## (d) Findings ordenados por gravidade

### CRÍTICO

**C1 — VNC sem password aberto para o IB Gateway LIVE.**
O processo `x11vnc -nopw -listen 0.0.0.0` (porta 5900) dá acesso remoto ao ecrã e **ao rato/
teclado** do IB Gateway em modo live, sem password nenhuma, e a firewall do servidor está
desligada (`ufw status` → inactive). Qualquer pessoa/dispositivo na rede local ou na tailnet
consegue ver e CONTROLAR a janela do Gateway — incluindo mexer nas definições (p.ex. tirar o
modo read-only) ou interferir com o login 2FA. A trava `ReadonlyLogin=yes` protege a API, mas
o VNC contorna-a porque controla a interface gráfica.
Evidência: `systemctl status ibgateway` (linha x11vnc), `ss -tlnp | grep 5900`, `ufw status`.
Ação: pôr password/localhost-only no x11vnc (é 1 flag) — passo 1 do plano de fixes.

### ALTO

**A1 — Duas sessões live permanentes na IB para um projeto pausado, com 2FA automatizado
frágil.** O `ibgateway.service` relança e faz login live diário às 21:45 com um bot que clica
pixels e insere o código TOTP; no dia 11-jul o código foi **rejeitado à 1ª tentativa** e "No
new 2FA dialog appeared" (journal). Em paralelo o container `ibeam-primary` mantém uma segunda
sessão live (Client Portal) 24/7, e teve dezenas de tentativas falhadas a 04-jul (712
screenshots/logs). Logins live automáticos repetidos e falhados = risco real de **lockout da
conta IB** (a IB bloqueia contas com padrões de login suspeitos), sem nenhum benefício
enquanto o projeto está pausado — o bot não negoceia (ib_orders=0) e só o lifeos lê o saldo
uma vez por dia.
Evidência: journal ibgateway 11-jul 21:45; `docker ps` (ibeam unhealthy); `ls infra/ibeam/outputs | wc -l` → 712.

**A2 — O único candidato a estratégia (iron-fly 0006) está em limbo: validação contraditória
nunca reconciliada + forward test avariado + dados pagos perdidos.** O multi-regime EOD deu
PF<0,4 em todos os anos (contradiz o held-out PF 1.42-1.78 do sweep intraday) e ninguém olhou
para o resultado (a memória continua "survivor"); o forward paper registou **0 eventos em 6
semanas** (universo desalinhado — 16/19 eventos "not_in_snap_universe"); e o ThetaData caiu
para FREE tier, por isso já não se consegue repetir o teste intraday. Neste estado, é
impossível decidir honestamente se o estudo com "maior expectativa" é real ou artefacto.
Evidência: `peryear_multiregime.txt` (28-mai), journal paper-ironfly ("logged 0"), journal theta-terminal ("OPTION.FREE").

**A3 — A ação de maior ROI do audit v4 nunca arrancou: `altdata_snapshots` = 0 linhas.** O
audit de 26-mai disse, em maiúsculas, que arquivar snapshots point-in-time dos dados
alternativos "é o único moat que compõe com o tempo" e devia começar JÁ. A tabela foi criada
e está vazia; 45+ dias de vintages (versões datadas dos dados) perderam-se — cada dia que
passa é história que nunca mais se recupera (os dados live de hoje deixam de ser reconstruíveis
amanhã).
Evidência: `SELECT count(*) FROM altdata_snapshots` → 0 (hoje).

### MÉDIO

**M1 — A contabilidade do paper trading não fecha (+$70.000 sem explicação).** Cash da conta
paper 2: $36.892. Mas $100.000 iniciais − $164.705 comprados + $31.597 vendidos = −$33.108.
Diferença = exatamente +$70.000 — cheira a top-up manual ou dupla contagem nunca registada.
Enquanto isto não for explicado, a curva paper (equity $177.5k) não serve de evidência de
performance. (No período COM snapshots, 26-mai→11-jul, a curva é honesta e FLAT: −$457,
maxDD −4,7%, Sharpe −0.13.)
Evidência: queries a `paper_cash`, `paper_trades`, `paper_snapshots` hoje.

**M2 — O backtest semanal gasta ~63 min/semana e o passo final falha há 9 execuções.** O
`ib-backtests.timer` corre as 56 estratégias todos os domingos (hoje: 54 OK, 2 FALHADAS — as
SMB Factor Regime, "No tickers found") e depois o `generate_plot_data.py` é recusado pelo
guarda `api_caution` (4500 chamadas IB estimadas > limite). Ou seja: um job semanal pesado
cujo output final (dashboard) não é regenerado por ele próprio, num projeto pausado que
ninguém está a ler.
Evidência: `/var/log/ib-backtests.log` (grep "refusing" → 9), corrida de hoje 05:16-06:19.

**M3 — Repo sujo e à deriva: 357 ficheiros untracked (lixo do ibeam) e branch de trabalho
`snapshots-exec-fixes` ≠ main.** O container `ib_bot-api-1` foi construído a partir de `main`,
mas a árvore de trabalho está noutra branch com fixes de 29-jun; os worktrees v2/altdata
divergem do main (backend v2 diverge ~400-500 linhas e NÃO está a correr). Risco: próximo
agente "corrige" o código errado ou perde os fixes.
Evidência: `git worktree list`, `git status --porcelain | wc -l` → 357.

**M4 — 14 containers + 2 frontends systemd + 4 portas expostas (8001/8090/8092/3001/3002 em
0.0.0.0) para um projeto pausado.** Consumo modesto (~1,6 GB RAM total, CPU ~0) mas é
superfície de ataque e de confusão (duas stacks completas fazem polling diário; o beat da v1
continua a criar snapshots e a mexer na DB).
Evidência: `docker ps`, `docker stats`, `ss -tlnp`.

### BAIXO

**B1 — Tickers delisted fazem ruído no weekly run** (yfinance "possibly delisted" aos montes;
14 nomes mortos conhecidos nas carteiras grandes).
**B2 — Conductor desatualizado**: projeto `ib_bot` = `active` na DB do conductor, mas na
prática está pausado; plano único superseded.
**B3 — `ibeam-primary` marcado unhealthy no healthcheck** apesar de autenticado — healthcheck
mal calibrado; e o `ibeam-session-manager.service` do host está disabled enquanto um
`ibeam_starter.py` avulso corre fora do systemd (PID 697116, cwd apagado `/srv/ibeam`).
**B4 — plot_data.json tem timestamp 11-jul 22:27** (algum processo no container atualiza-o),
mas o passo oficial de regeneração falha — não está claro qual é a fonte de verdade do
dashboard.

---

## (e) Actionable steps, por ordem (o quê e porquê)

1. **Fechar o VNC (C1)** — 1 linha no unit file; risco real, custo zero. AGORA.
2. **Decidir e executar o "modo dormência"**: parar `ibgateway`+`xvfb`+`ib-socat`+`watchdog`+
   `ibeam` (elimina A1: zero sessões live automáticas) e desligar `ib-backtests.timer` (M2).
   O lifeos perde o refresh diário do saldo → trocar para modo "stale ok" ou aceitar. Se o
   José preferir manter o saldo diário no lifeos, alternativa: manter SÓ o ibeam (Client
   Portal, sem GUI, sem 2FA-bot de pixels) e matar o Gateway/VNC/2FA-bot.
3. **Ligar o arquivo `altdata_snapshots` (A3)** — job diário barato que grava os vintages;
   é a única coisa deste projeto que GANHA valor enquanto ele está parado.
4. **Reconciliar o estudo 0006 (A2)**: análise offline (dados já no disco) para explicar
   multiregime-EOD vs sweep-intraday; corrigir o universo do forward paper (ou parar o timer
   se não for corrigido). Só depois decidir se vale re-subscrever ThetaData.
5. **Explicar o delta +$70k do paper (M1)** — investigação de 1 hora na DB; ou se documenta,
   ou se marca a curva paper como "não usar como evidência".
6. **Arrumar o repo (M3)**: gitignore para `infra/ibeam/outputs/`, commit dos fixes da
   branch, decidir merge para main.
7. **Reduzir para 1 stack Docker (M4)** quando se souber qual (v1:8001/8090 é a que serve o
   frontend 3001; a v2:8092 é a "Plan B" — provavelmente desligar a v2).

## (f) Riscos se nada for feito

- **Segurança**: VNC aberto sem password à frente de uma sessão de corretora live — qualquer
  intruso na LAN/tailnet pode mexer na conta (mesmo sem conseguir dar ordens via API, pode
  desativar o read-only pela GUI). É o risco nº1 de toda a auditoria.
- **Conta IB**: logins live automáticos diários com 2FA frágil (+ tentativas falhadas do
  ibeam) podem levar a bloqueio da conta pela IB — chato de reverter, e afeta a conta real.
- **Perda de valor silenciosa**: cada dia sem `altdata_snapshots` é um dia de "moat" perdido
  para sempre; era o único ativo que o audit v4 considerou compounding.
- **Decisão errada no futuro**: se ninguém reconciliar o multiregime vs sweep do 0006, ou o
  José retoma uma estratégia que na verdade perde 20%/trade, ou mata a única candidata viva.
- **Recursos/entropia**: ~63 min de compute semanal + 14 containers + timers a produzir dados
  que ninguém lê; lixo a acumular no repo; memória da frota desatualizada (diz "survivor"
  quando os dados dizem outra coisa).

## (g) Glossário (termos por ordem alfabética)

- **13F** — relatório trimestral que fundos grandes entregam à SEC a listar as ações que têm.
- **Alpha** — a parte do ganho que vem de habilidade/informação, depois de descontar o que o
  mercado deu por si só. **Beta** = a parte que é só "andar com o mercado".
- **Alt-data** — dados alternativos: informação fora dos preços (compras de políticos, lóbi,
  contratos públicos, posts em fóruns).
- **API (Application Programming Interface)** — a "porta" por onde dois programas falam um
  com o outro.
- **Backtest** — simulação histórica: "quanto teria ganho se tivesse seguido esta regra".
- **Celery / beat / worker** — sistema de tarefas em fila: o *beat* é o despertador que agenda,
  os *workers* executam.
- **Client Portal / ibeam** — a interface web da IB; o *ibeam* é um programa que mantém esse
  login vivo automaticamente.
- **Deflated Sharpe** — Sharpe corrigido pelo número de tentativas (se testas 36 estratégias,
  a melhor parece boa por sorte; esta correção desconta isso).
- **Docker / container** — "caixas" isoladas onde os programas correm com tudo o que precisam.
- **Dry-run** — ensaio: o sistema faz todos os passos MENOS enviar a ordem real.
- **EOD (End Of Day)** — dados de fim-de-dia (um valor por dia), vs **intraday** (ao longo do dia).
- **Equity / NLV (Net Liquidation Value)** — valor total da conta se vendesses tudo agora.
- **Held-out / holdout** — fatia de dados escondida durante o desenvolvimento, usada só no
  fim para testar honestamente.
- **IB / IBKR (Interactive Brokers)** — a corretora. **IB Gateway** — o programa dela que dá
  acesso à conta por API. **IBC** — utilitário que automatiza o arranque/login do Gateway.
- **Iron-fly (iron butterfly)** — aposta em opções: vende-se um straddle (call+put no preço
  atual) e compram-se "asas" mais afastadas como seguro; ganha se a ação mexer pouco; a perda
  máxima fica limitada pelas asas.
- **MaxDD (Maximum Drawdown)** — a maior queda desde um pico até ao fundo seguinte.
- **MCP (Model Context Protocol)** — protocolo que liga os agentes de IA a ferramentas (ex.:
  consultar a conta IB).
- **Paper trading** — negociar com dinheiro fictício para testar.
- **PF (Profit Factor)** — soma dos ganhos ÷ soma das perdas; >1 é lucrativo.
- **Point-in-time / vintage** — guardar os dados como eles eram NAQUELE dia (para backtests
  honestos, sem usar informação do futuro).
- **Sharpe (ratio)** — ganho por unidade de risco; ~0 é nada, >1 começa a ser bom.
- **Slippage (slip)** — quanto pior que o preço "ideal" é o preço a que realmente consegues
  negociar. slip 0.25 = pagas 25% do spread bid-ask.
- **TOTP / 2FA** — código de 6 dígitos que muda a cada 30s; segunda camada de segurança do login.
- **VNC / x11vnc** — programa de acesso remoto ao ecrã (ver e controlar com rato/teclado).
- **Worktree (git)** — segunda pasta de trabalho ligada ao mesmo repositório, noutra branch.
- **yfinance** — biblioteca gratuita de preços do Yahoo Finance (limitada e às vezes falha).
