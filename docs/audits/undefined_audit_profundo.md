# Audit profundo — IB Bot (trading via Interactive Brokers)

Data da auditoria: 2026-08-17 (ART / hora de Buenos Aires). Autor: agente auditor Fable
(modo ultracode), read-only. Todas as evidências abaixo foram recolhidas NESTA sessão
(comandos `git`, `systemctl`, `journalctl`, `psql`/`docker exec psql`, `docker ps`, ferramenta
MCP da Interactive Brokers) — nada foi copiado de memória sem reconfirmar.

> **Nota importante já no topo:** o brief que originou este audit descrevia o projeto como
> "PAUSED". Isso é **impreciso na prática operacional**: o repositório tem commits
> automáticos TODOS OS DIAS até hoje de manhã (04:32 WEST), há uma stack Docker viva há
> 3–6 dias, e um plano do Conductor está `executing` neste preciso momento. O que está
> pausado é **a decisão de negócio** (não entrar em trading ao vivo, não gastar dinheiro
> novo) — não a máquina, que continua a trabalhar sozinha todos os dias. Ver secção (d).

---

## (a) O que é este projeto — para miúdos

Imagina um robô que lê notícias sobre o que gestores de fundos famosos, políticos dos EUA e
empresas andam a comprar e vender (informação pública, tipo "quem comprou o quê"), e tenta
usar isso para decidir se compra ou vende ações. Esse robô chama-se **IB Bot** porque usa a
corretora **Interactive Brokers (IB)** — uma empresa que executa ordens de compra/venda de
ações em bolsa em nome de quem tem conta lá.

O projeto tem três peças:

1. **O motor de backtesting** — testa "se eu tivesse seguido esta estratégia nos últimos anos,
   teria ganho ou perdido dinheiro?" para 56 estratégias diferentes (ex.: copiar compras de
   membros do Congresso dos EUA, copiar Michael Burry, copiar fundos "13F" — grandes
   investidores que são obrigados por lei a divulgar o que compram).
2. **O motor de execução** — o código que, SE ligado, mandaria ordens reais à IB. Tem travões
   de segurança (limites de valor, paragem de emergência, lista de contas permitidas).
3. **O arquivo de "alt-data" (dados alternativos)** — todos os dias, o sistema guarda uma
   "fotografia" (snapshot) de tudo o que sabe nesse dia — congresso, 13F, FINRA (dados de
   vendas a descoberto), FRED (dados económicos), etc. — para nunca mais poder ser alterada
   depois. Isto chama-se **PIT (Point-In-Time)**: garante que se testarmos "o que sabíamos em
   1 de julho" não estamos a fazer batota a olhar para o futuro sem querer.

**API (Application Programming Interface — a "porta" por onde dois programas falam um com o
outro):** a IB tem uma API que o robô usa para pedir preços e (se autorizado) mandar ordens.

**MCP (Model Context Protocol — outra "porta", desta vez entre um assistente de IA como este e
um serviço externo):** o José tem uma ligação MCP à IB que este auditor usou (só leitura) para
confirmar o saldo real da conta.

**Docker / container:** uma forma de empacotar um programa com tudo o que precisa para correr,
como uma caixa fechada e portátil. O IB Bot corre dentro de várias dessas caixas (API, worker,
base de dados, etc.) na mesma máquina.

**Celery / Celery Beat:** um sistema de "tarefas agendadas" — como um despertador que todos os
dias às X horas manda o programa fazer Y (ex.: "às 06:00 UTC vai buscar os dados de hoje").

**systemd timer:** o "despertador" do próprio sistema operativo Linux, usado para tarefas que
não vivem dentro do Docker (ex.: correr um backtest semanal).

---

## (b) Evolução até hoje — linha do tempo (verificada por `git log`, memórias e a base de dados
do Conductor nesta sessão)

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit do repositório `ib_bot` ("Initial commit - IB Bot trading system"). |
| 2026-02-19 | Primeiras contas de paper trading criadas na base de dados (`paper_cash` ids 1 e 2). |
| 2026-05-09 | Última entrada em `paper_trades` no formato antigo (138 trades, fev–mai). |
| 2026-05-23 | Estudo irmão **PEAD** (`project_pead`, projeto separado mas relacionado, mesma tese de "seguir sinais públicos") é **REJEITADO/fechado**: 7 testes independentes concluem que não há alfa robusto (é beta de mercado disfarçado). |
| 2026-05-26 | Áudito profundo v1→v4 do IB Bot (memória `project_ib_bot_audit`, ver evidência em (d)). **v4 é a versão AUTORITATIVA**: nenhuma das 56 estratégias sobrevive a Deflated Sharpe Ratio + teste fora da amostra; recomenda vender o MOTOR (dados/infra), não o "alfa". Também nesta data arranca a conta de paper trading nº2 que hoje tem 83 dias de histórico real (ver secção de métricas). |
| 2026-07-12/13 | **Decisão vinculativa do José**: o projeto entra em "dormência seletiva" — IB Gateway, Xvfb, ibeam, VNC são todos desligados (zero sessões ao vivo na IB). O backtest semanal e o refresh diário de saldo via MCP **mantêm-se ligados** por ordem explícita. |
| 2026-07-13 a 07-19 | Sequência de correções ao backtest semanal (`ib-backtests.service`): falhas por falta de cache, depois por pressão de memória (OOM), corrigidas em 3 rondas (commits `8835568`, `b4358ae`, `6439026`). Desde 2026-07-19 não há mais nenhum alerta de falha (verificado: zero eventos `ib_backtests_failure_alert` desde essa data). |
| 2026-07-16 | Estudo irmão **earnings-vol / "Iron Wing" (0006)** é **MORTO (KILL)** ao atingir o gate pré-registado de 36 eventos forward: Profit Factor a preço-médio 0.78, a preço-de-execução-real 0.26 — perdedor estrutural. Zero compra de dados pagos (ThetaData), zero capital real. |
| 2026-08-04 a 08-14 | Arranca e evolui o plano **"Alt-data PIT archive hardening"** no Conductor (id `04bf8af8`): tornar o arquivo diário de dados à prova de adulteração, replicado para fora do servidor, e a correr sozinho sem agente humano/IA a empurrar. |
| 2026-08-12 | Auditoria de segurança independente encontra falha real: o papel de aplicação da base de dados (`ibbot`) ainda tinha poderes de "superuser" — podia forjar correções "auditadas". Corrigido com separação de privilégios (ver (d), CRÍTICO resolvido). |
| 2026-08-14 a 08-16 | Gate H3 (funcionamento sem agente) exige exatamente 3 disparos consecutivos e autónomos do timer diário de QA às 08:00 WEST — os 3 já aconteceram e ficaram verdes; falta só a confirmação final do script verificador. |
| 2026-08-17 (hoje) | Último commit automático (`4dc0504`, 04:32 WEST) — cópia diária ("backup") da tabela PIT. Este audit corre com o repositório neste estado. |

---

## (c) Estado concreto HOJE (tudo verificado nesta sessão)

### Repositório

- **Um único repositório git** (`git@github.com:JoseMoura97/ib_bot.git`), 188 commits na
  branch `main`. Os três "roots" mencionados no brief (`ib_bot`, `ib_bot-v2`,
  `ib_bot-altdata-wt`) **NÃO são repositórios diferentes** — são **git worktrees** (cópias de
  trabalho paralelas) do MESMO repositório, em branches diferentes:
  - `ib_bot` → branch `main` (4.2 GB em disco, inclui caches e resultados de backtests
    antigos).
  - `ib_bot-v2` → branch `frontend-v2` (1.2 GB), **descomissionada** — a memória confirma que
    esta stack "v2" (porta :8092) foi desligada; o commit de topo (`25f7a6a`) está
    explicitamente marcado "não obrigatório" numa das fases já fechadas.
  - `ib_bot-altdata-wt` → branch `alt-data-consolidation` (21 MB), usada para trabalho em
    curso de consolidação de código.
  - Há ainda 6 worktrees extra em `ib_bot/.worktrees/` usados pelas fases do Conductor
    (h1/h2/a1/f5/h3/h4).

### Serviços systemd (evidência: `systemctl list-units`/`list-timers`, `journalctl`)

| Unidade | Tipo | Estado agora | Nota |
|---|---|---|---|
| `ib-bot-v2-frontend.service` | serviço | **ativo, 6 dias** | Apesar do nome "v2", fala com a API v1 (:8001) — confirmado pela memória e por `curl localhost:3001` a devolver 307 (redirect vivo). |
| `theta-terminal.service` | serviço | **ativo, 6 dias** | Gateway de dados de opções (ThetaData), porta 127.0.0.1:25510. Partilhado com o projeto irmão "trading" (usa-o o paper-ironfly). Pico de memória já visto: 4.7 GB. |
| `ib-altdata-backup.timer/.service` | timer | **ativo**, corre de madrugada | Cópia diária da tabela PIT para fora do servidor (offsite). Último disparo: hoje 04:32 WEST, sucesso (commit `4dc0504`). |
| `ib-altdata-qa.timer/.service` + `ib-altdata-qa-alert.service` | timer + alerta | **ativo** | QA diária ao arquivo (verifica integridade), 08:00 WEST. Alerta acorda o Domain Manager `ib_bot` no Conductor se falhar. |
| `ib-backtests.timer/.service` + `ib-backtests-alert.service` | timer + alerta | **ativo**, semanal (domingo 04:15 UTC) | Backtest completo das 56 estratégias + regeneração dos gráficos. Última corrida (16/08): sucesso, sem alertas desde 19/07. |
| `lifeos-ib-refresh.timer/.service` | timer | **ativo**, diário 03:15 ART | Vai buscar o saldo real da conta IB via MCP (não usa o IB Gateway) para a página pessoal "lifeos" do José. Mantido por ordem explícita dele. |
| `theta-learned.timer/.service` | timer | **ativo**, diário 07:30 UTC | Monitor "aprendido" só-report (não negoceia), sobre dados de opções. |
| `ibgateway.service` | serviço | **inativo/dead**, sem logs no journal | Desligado por decisão de 2026-07-12/13. |
| `xvfb-ibgw.service` | serviço | **inativo/dead** | Ecrã virtual que o IB Gateway usava — desligado junto com o gateway. |
| `cost-recalibration.timer`, `execution-metrics.timer`, `historical-backfill.timer` | timers | ativos, mas **NÃO são do ib_bot** | Descrição real no systemd: "Polymarket ..." — pertencem a outro projeto de trading (mercados de previsão). O brief pedia para confirmar isto: confirmado, não pertencem ao IB Bot. |
| `paper-ironfly.timer/.service` | timer | ativo, **NÃO é do ib_bot** | `WorkingDirectory=/home/servidor/Desktop/cursor-projects/trading` — é do repositório irmão "trading" (mesmo tema de opções, mas projeto/Domain Manager diferente). Não usa a base de dados do ib_bot. |

### Docker (stack viva)

`ib_bot-api-1` (3 dias), `ib_bot-worker-1` (3 dias), `ib_bot-beat-1` (3 dias — relançados há 3
dias, provavelmente um redeploy), `ib_bot-db-1` (Postgres 16, 6 dias), `ib_bot-redis-1` (6
dias), `ib_bot-web-1` + `ib_bot-nginx-1` (6 dias, porta 8090). API responde `200` em
`/health`. **Dois frontends vivos ao mesmo tempo** (o systemd `:3001` e o docker
`nginx:8090→web:3000`) — ver finding MÉDIO.

O Celery Beat corre 8 tarefas agendadas, incluindo `live_rebalance_hourly` — **verificado nos
logs de hoje e de ontem**: dispara todas as horas de mercado, mas imprime sempre
`LIVE_AUTO_REBALANCE off, skipping` e termina em <0.1s sem tocar na IB. Nenhuma ordem real foi
mandada.

### Base de dados (verificado por `docker exec ib_bot-db-1 psql`, só `SELECT`)

- `altdata_snapshots`: **394 linhas**, de 2026-07-13 a 2026-08-17 (arquivo PIT a crescer todos
  os dias, como esperado).
- `ib_orders`: **0 linhas**. `ib_trades`: **0 linhas**. Confirma, na base de dados viva de
  hoje, que **nunca houve uma ordem real executada** na IB por este sistema.
- `paper_trades`: 138 linhas (fev–mai, conta antiga de simulação manual).
- `paper_snapshots`: **168 linhas**, de 2026-05-26 a 2026-08-16, com DUAS contas:
  - conta 1 ("Main Paper"): fica sempre nos $100.000 iniciais — nunca operou.
  - conta 2 ("Main Paper"): **tem uma curva de capital real de 83 dias**, $177.540 →
    $185.513 (ver métricas em (métricas)). Esta é a única prova de "resultado" contínuo e
    autónomo que o projeto produziu.

### Conta real da Interactive Brokers (verificado agora via MCP, só leitura)

- **Valor líquido (net liquidation): €27.247,71.**
- Posição aberta: **70 ações de BRK B (Berkshire Hathaway)**, valor de mercado ~$35.345,
  ganho não realizado +$977,95. Esta é quase certamente uma posição **manual do José**, não
  gerada pelo IB Bot (as estratégias do bot são sobre 13F/congresso/insiders, não uma compra
  simples e concentrada de Berkshire; o bot nunca colocou uma ordem, como confirmado acima).
  **Não confundir**: a conta IB tem dinheiro real e uma posição real, mas nada disso veio do
  motor automático do ib_bot.

### Plano ativo no Conductor (para não duplicar trabalho)

Plano `04bf8af8-6614-4f12-9d57-772f7af2b67d`, "Alt-data PIT archive hardening", **status
`executing`**. Das 5 fases:
- H1 (cópia offsite + prova de restore) — **done**.
- H2 (reparar sincronização para o GitHub) — **done**.
- H3 (operação sem agente, 3 dias verdes seguidos) — **in_progress**: os 3 disparos autónomos
  de 14/15/16-08 já aconteceram e ficaram verdes (confirmado por `verify_h3_soak.sh`,
  commit local, output "OK 2026-08-16 pinned-image timer-window green"), mas o script mais
  recente já também exige o disparo de hoje (17/08, ainda não disparou às 08:00 WEST na hora
  desta verificação) — `H3_SOAK_RED NO_RUNTIME_RECEIPT 2026-08-17`.
- H4 (imutabilidade / cadeia de hashes) — **done**. Resolveu um CRÍTICO real encontrado a
  12/08 (o papel de aplicação da base de dados tinha poderes de superuser e podia forjar
  correções "auditadas"); hoje o gate de privilégios está a passar.
- H5 (lacunas medidas + teste de reconstrução adversarial) — **done**.

---

## (d) Findings, por gravidade

### CRÍTICO

Nenhum finding CRÍTICO **em aberto** neste momento. O único CRÍTICO real identificado no
histórico (papel de base de dados `ibbot` com poderes de superuser, podendo forjar correções
"auditadas" no arquivo PIT — descoberto 2026-08-12) já está **corrigido e verificado** (gate
H4, `done`). Fica registado aqui como findig histórico fechado, com evidência: memória
`reference_ib_bot_altdata_owner_boundary_20260812.md`, commit `ddc0656` + migração `0014`,
`plan_knowledge` do plano `04bf8af8`.

### ALTO

1. **Nenhuma das 56 estratégias tem alfa robusto — validado 4 vezes, nunca refutado.**
   Evidência: memória `project_ib_bot_audit` v4 (autoritativa, 2026-05-26): Deflated Sharpe
   Ratio (Bailey–López de Prado) sobre 36 testes → NENHUMA estratégia passa (todas DSR<0.15);
   17/18 estratégias com "alfa" decaem depois de fev-2023; os 2 sobreviventes (Transportation
   Cmte, House L/S) dependem de 1-2 meses de sorte (65%/95% do ganho pós-2023 vem de 1-2
   meses). Implicação prática: **não há razão financeira para reativar trading ao vivo com o
   catálogo atual de estratégias**. Isto não é uma opinião nova deste audit — é a conclusão já
   tomada e nunca contestada desde maio.

2. **O projeto continua a gastar recursos (compute, disco, atenção de alertas) todos os dias
   à volta de um plano de "hardening" de dados que serve um produto (as 56 estratégias) já
   comprovadamente sem edge.** O plano `04bf8af8` está a fazer um trabalho tecnicamente sólido
   (imutabilidade, backups, QA autónomo) mas **não há, nas evidências do Conductor, uma fase
   seguinte definida que ligue "arquivo perfeito" a "decisão de negócio"** — o risco é o
   arquivo continuar a crescer indefinidamente sem ninguém nunca vir a usá-lo para nada
   accionável, e o esforço de engenharia (dezenas de commits, ECC reviews, migrações de BD)
   continuar a ser gasto num produto pausado. Ver plano de fixes, passo sobre decisão de
   continuidade.

3. **Dois frontends web expostos ao mesmo tempo, sem necessidade clara enquanto o projeto está
   pausado**: `ib-bot-v2-frontend.service` (systemd, porta 3001, fora do Docker) e
   `ib_bot-nginx-1` (Docker, porta 8090). Nenhuma ordem real pode ser colocada através deles
   (o motor de execução ao vivo está desligado no nível do Celery/gateway), mas é superfície
   web desnecessária e potencialmente confusa (dois "produtos" a responder em paralelo)
   enquanto ninguém está a usar o produto ativamente.

### MÉDIO

4. **`theta-terminal.service` já teve picos de 4.7 GB de memória** e está sempre ligado (6
   dias), partilhado entre o ib_bot (`theta-learned.timer`, monitor diário só-report) e o
   projeto irmão "trading" (paper-ironfly). Se o "trading" desligar o seu uso, ninguém vai
   questionar se o ib_bot ainda precisa dele ligado 24/7 só para um monitor diário de 1
   execução/dia.

5. **Confusão de nomenclatura "v2"**: `ib-bot-v2-frontend.service` serve a API v1 (:8001); a
   verdadeira stack "v2" (:8092, Plan B go-live, branch `frontend-v2`) está desligada. Isto já
   causou um erro documentado numa fase anterior do Conductor (f4 quase exigiu o commit errado
   `25f7a6a` como referência de "main" antes de ser corrigido pela autoridade Jarvis). Risco de
   o próximo agente/pessoa repetir o erro.

6. **Máquina hospedeira sob pressão de memória em geral** (verificado agora:
   `free -h` → 2.3 GiB livres de 251 GiB, 64 GiB de swap em uso). Não é uma falha do ib_bot
   isoladamente (é o estado do servidor partilhado), mas o histórico de 2026-07-19 mostra que
   o backtest semanal do ib_bot já foi morto duas vezes pelo `systemd-oomd` por causa desta
   pressão antes de ser corrigido — o risco de recorrência não desapareceu, só foi mitigado
   (cache limitado a 128 tickers, `OOMScoreAdjust=0`).

7. **`docker system df` mostra 36,3 GB de imagens e 5,7 GB de build cache reclamáveis** no
   host — parte pertence ao ib_bot (rebuilds frequentes de api/worker/beat para as fases do
   Conductor), parte a outros projetos. Não é uma falha específica mas é desperdício de disco
   fácil de recuperar.

### BAIXO

8. **`ib_bot-v2` (1,2 GB em disco) e o worktree `ib_bot-altdata-wt`** só têm valor enquanto o
   Conductor ainda usa as branches associadas; nenhum dos dois é necessário para a operação
   diária (backups, QA, backtest semanal correm todos a partir do worktree principal `ib_bot`
   com branch `main`).

9. **Resíduos antigos no root do repositório** (`$LOG` de 765 KB, `alembic_validation.db`,
   três `backtest_results_*.json` de ~1 MB cada, `docker-compose.prod.yml.bak.*`) — inofensivos
   mas poluem a raiz do projeto.

---

## (e) Actionable steps — ordenados por prioridade e porquê

1. **Fechar o gate H3 do plano ativo (`04bf8af8`) — deixar o timer terminar sozinho, não
   empurrar manualmente.** É o único item a meio-caminho; falta o disparo autónomo de hoje
   (17/08) às 08:00 WEST. Zero esforço — só esperar e depois correr o verificador. (Detalhe no
   plano de fixes, passo 1.)
2. **Decisão de negócio explícita do José: o que acontece DEPOIS do arquivo estar
   "hardened"?** Este é o item de maior alavancagem — sem ele, o projeto continua a gastar
   engenharia e compute num alicerce sem edifício por cima. Ver Plano de Fixes passo 2 e os
   planos futuros (secção de planos futuros) para as opções concretas.
3. **Consolidar/decidir os dois frontends** (systemd :3001 vs docker :8090) — manter só um,
   documentar qual é o canónico, desligar o outro. Baixo risco, resolve a confusão de "v2".
4. **Limpar `docker system df`** (imagens/build cache não usados) — recupera dezenas de GB sem
   tocar em nada vivo.
5. **Arrumação de resíduos no root** (`$LOG`, `.bak`, resultados antigos) — cosmético, zero
   risco.

---

## (f) Riscos se nada for feito

- **Financeiro direto: nenhum.** O motor de execução ao vivo está desligado em 3 camadas (o
  IB Gateway está `inactive`, `LIVE_AUTO_REBALANCE` está `off` — verificado nos logs de hoje —
  e `ib_orders`/`ib_trades` estão a 0 na base de dados viva). Mesmo que nada mude, não há
  caminho para uma ordem real acontecer por acidente.
- **Financeiro indireto (custo de oportunidade):** o esforço de engenharia contínuo
  (dezenas de commits/semana, revisões ECC, migrações de BD) está a ser gasto num arquivo de
  dados cada vez mais robusto para um catálogo de estratégias já comprovadamente sem edge. Se
  ninguém decidir "para que serve este arquivo perfeito", o trabalho fica a compor sem nunca
  ser monetizado.
- **Operacional:** se o gate H3 nunca fechar (por o timer falhar silenciosamente ou o
  verificador nunca ser corrido), a fase fica presa em `in_progress` indefinidamente,
  continuando a acordar o Domain Manager em cada falha.
- **Recursos:** consumo contínuo de RAM (theta-terminal, stack docker), disco (arquivo PIT +
  imagens docker) e alertas — pequeno individualmente, mas sem limite de tempo definido.
- **Confusão futura:** a nomenclatura "v2" enganosa e os dois frontends vivos aumentam a
  probabilidade de o próximo agente (humano ou IA) tomar uma decisão errada sobre qual stack é
  a real.

---

## Glossário

- **API (Application Programming Interface):** a "porta" por onde dois programas trocam
  informação (ex.: o robô pede à IB "qual é o preço da ação X?").
- **MCP (Model Context Protocol):** protocolo que permite a um assistente de IA (como este)
  ligar-se a serviços externos (aqui, à conta da Interactive Brokers) para ler dados.
- **Backtest:** simular "se eu tivesse seguido esta estratégia no passado, teria ganho ou
  perdido dinheiro?", usando dados históricos.
- **Alfa (alpha) / Beta (beta):** alfa é o ganho que vem da tua capacidade de escolher bem
  (skill); beta é o ganho que vem só de o mercado em geral ter subido (ex.: comprar um
  bocadinho de tudo). Uma estratégia "com alfa" ganha mais do que só acompanhar o mercado.
- **Sharpe Ratio / Deflated Sharpe Ratio:** número que mede "quanto ganhas por unidade de
  risco". "Deflated" corrige o facto de teres testado 25-56 estratégias diferentes — quanto
  mais testas, maior a hipótese de uma parecer boa só por sorte; o Deflated Sharpe pune isso.
- **Paper trading:** simular ordens de compra/venda com dinheiro fictício, sem risco real, para
  testar se o sistema funciona como esperado.
- **PIT (Point-In-Time):** guardar uma "fotografia" imutável dos dados tal como eram nesse dia,
  para nunca poderes (sem querer ou por batota) usar informação do futuro num teste do passado.
- **Celery / Celery Beat:** sistema de tarefas agendadas dentro do Docker (ex.: "todos os dias
  às 06:00 UTC, vai buscar os dados novos").
- **systemd timer:** o "despertador" do próprio sistema Linux, fora do Docker.
- **OOM / OOM-kill (Out Of Memory):** quando o Linux fica sem memória livre e mata um processo
  à força para o sistema não morrar todo.
- **Docker / container:** uma "caixa" isolada e portátil onde um programa corre com tudo o que
  precisa, sem interferir com o resto da máquina.
- **git worktree:** uma segunda pasta de trabalho ligada ao MESMO repositório git, mas com uma
  branch (versão paralela do código) diferente aberta — não é uma cópia independente do
  histórico.
- **Conductor / Domain Manager (DM) / plano / fase:** o sistema de orquestração de agentes de
  IA que o José usa para gerir trabalho de longa duração; um "plano" tem "fases" com critérios
  de aceitação exatos que têm de ser provados, não assumidos.
- **RIA (Registered Investment Adviser):** categoria regulatória nos EUA para quem gere dinheiro
  de terceiros por decisão automática — obrigaria a registo formal se o ib_bot alguma vez
  passasse a negociar por conta de outras pessoas além do José.
