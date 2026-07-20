# Audit profundo — IB Bot (PAUSADO) — 2026-07-20

Auditor: agente Fable (modo ultracode), sessão `mega-audit-2026-07-20`.
Timezone de leitura: ART (UTC-3), Buenos Aires. Todos os timestamps do sistema
foram capturados em WEST/UTC e convertidos onde relevante.

Este é o **segundo** audit profundo deste projeto (o primeiro foi
`docs/audits/2026-07-12_audit_profundo.md`). A maior parte dos findings
CRÍTICOS/ALTOS desse primeiro audit já foi corrigida por um plano do
Conductor (`e36e04ec-de9c-438f-b0e5-434dfa391154`) executado entre
2026-07-13 e 2026-07-19. Este documento **re-verifica tudo do zero** (não
assume que os fixes seguraram) e regista o que mudou, o que ainda falta, e
o que é novo.

---

## (a) O que é este projeto — para miúdos

O **IB Bot** é um robô de investimento automático ligado à **Interactive
Brokers (IB)** — uma corretora (empresa que compra e vende ações por nós) —
através de um programa chamado **IB Gateway**. A ideia era copiar as
compras/vendas de gente "esperta": políticos americanos (que têm de
declarar as suas transações em bolsa por lei), fundos famosos (como o de
Warren Buffett ou Michael Burry, que têm de reportar trimestralmente à SEC —
o regulador do mercado dos EUA — num documento chamado **13F**), e outros
sinais "alternativos" (ex.: quantas pessoas falam de uma ação no Reddit).

O sistema tinha três partes:
1. **Backtests** — simulações: "se eu tivesse seguido esta regra nos
   últimos anos, quanto teria ganho?" (56 receitas/estratégias diferentes).
2. **Paper trading** — negociar com dinheiro a fingir, para testar sem
   risco.
3. **Execução real** — a parte que compraria/venderia ações verdadeiras —
   construída, mas **nunca ligada a sério** (zero ordens reais desde
   sempre).

Um audit interno rigoroso de 26 de maio de 2026 (o "v4", ver glossário)
concluiu que **nenhuma das 56 estratégias tem uma vantagem real** acima do
que se explicaria por sorte (testar 56 coisas e escolher a melhor no fim
quase sempre parece boa por acaso). Por isso o projeto foi **pausado**: não
foi apagado, mas ninguém está a decidir trades com ele.

Ao lado, dentro de um outro repositório (`trading`), corria um estudo
irmão chamado **0006 / Iron Wing**: vender opções caras à volta dos
resultados trimestrais das empresas (uma estratégia chamada **iron-fly**).
Esse estudo também **morreu** — ver secção (c).

---

## (b) Evolução até hoje (timeline)

Fonte: `git log` dos 3 repositórios + memórias do agente
(`~/.claude/projects/-home-servidor/memory/project_ib_bot*.md`,
`project_pead.md`, `project_earnings_vol.md`). 81 commits no repo principal
`ib_bot`, distribuídos assim por mês: jan=6, fev=10, mar=5, abr=1, mai=18,
jun=14, jul=27 (`git log --format='%ad' --date=format:'%Y-%m' | sort | uniq -c`).

| Data | Marco |
|---|---|
| 2026-01-17 | Primeiro commit (`22488df`) — sistema base de trading IB |
| 2026-02-19 → 05-09 | Conta paper "Main Paper" criada com $100.000; 138 trades executadas (só nesta janela — nunca mais houve trades novas) |
| 2026-05 (início) | Preparação para ir "a sério" (go-live): fractional shares, verify engine, conta real `U23842862` aberta com ~€1.000, API deixada **read-only** (proteção) |
| 2026-05-23 | Estudo irmão **PEAD** (Post-Earnings Announcement Drift, projeto `[[project_pead]]`, repo `trading`) **REJEITADO/FECHADO**: era beta de mercado disfarçado de skill — 7 testes independentes convergem em alpha≈0 |
| 2026-05-26 | **Audit v4 AUTHORITATIVE** (José, 4 agentes em paralelo): nenhuma das 56 estratégias sobrevive a Deflated Sharpe + teste fora-da-amostra; ~2 "edges" (congresso + Burry) na realidade são quase o mesmo trade (correlação 0,91-0,99); recomendação nº1 = arquivar snapshots diários point-in-time (**nunca começou nessa altura**) |
| 2026-06 (última 3ª semana) | Fase "alt-data" (Signal Explorer UI, stack v2 isolada em `:8092`); último commit de produto novo a 29-jun; projeto entra formalmente em pausa |
| 2026-07-12 | **1º audit profundo** (`docs/audits/2026-07-12_audit_profundo.md`): CRÍTICO — VNC (ecrã remoto) do IB Gateway aberto sem password para toda a rede; ALTO — 2 sessões live diárias na IB desnecessárias, contradição nunca resolvida no estudo 0006, arquivo point-in-time ainda vazio |
| 2026-07-13 | Triagem do José sobre esse audit: projeto entra em **dormência seletiva** (fecha VNC, desliga gateway/ibeam, mas mantém o fetch diário de saldo para o lifeos e o `ib-backtests.timer`); plano `e36e04ec` criado e aprovado |
| 2026-07-13 → 07-19 | Plano `e36e04ec` executa 7 das 8 fases: `f1` dormência ✅, `f2` corrige alerta do backtest semanal ✅, `f3` reconcilia o paper ledger ✅, `f4` limpa/funde o repo em `main` ✅, `f5` liga o arquivo diário alt-data ✅, `x1` reconcilia a contradição do estudo 0006 ✅, `x2` chega a 36 eventos forward e mata o estudo ✅ |
| 2026-07-16 | Estudo **0006 (earnings-vol/iron-fly) KILLED** — critério pré-registado disparou nos dois lados (PF@mid 0,776, PF@touch 0,256 em 36 eventos reais) |
| 2026-07-18/19 | `ib-backtests.service` falha 6× seguidas (3× oom-kill, 3× signal) antes de um fix de prioridade de memória (`b4358ae`, `6439026`) resolver; corrida R3 bem-sucedida às 2026-07-19 10:15-11:15 (56/56 estratégias) |
| **2026-07-20 (hoje)** | Este audit — re-verificação completa; ver secção (c) |

---

## (c) Estado concreto HOJE (2026-07-20, verificado nesta sessão)

### Dinheiro real (conta ligada via MCP — Model Context Protocol, a "ponte"
que liga este agente à conta real da Interactive Brokers do José)

- `get_account_summary`: **net liquidation €26.784,48**, leverage 1,12,
  moeda base EUR.
- `get_account_positions`: **1 posição** — 70 ações **BRK B** (Berkshire
  Hathaway classe B) a $491,01, valor $34.370,70. **Esta posição NÃO é do
  ib_bot** — o ib_bot nunca emitiu uma ordem (ver DB abaixo); é uma posição
  manual do José, não gerida por nenhum código deste projeto.
- Base de dados do próprio bot (`ib_bot-db-1`, Postgres, utilizador
  `ibbot`): `ib_orders=0`, `ib_trades=0`, `live_execution_requests=0`,
  `live_shadow_snapshots=0`. **Zero ordens reais desde sempre**, confirmado
  hoje por `SELECT count(*)` direto às tabelas.
- `live_rebalance_audit=25` linhas — todas de dry-run/preview antigos
  (9-22 maio), nunca uma execução real (consistente com a memória).

### Serviços e processos (systemd + Docker, verificado com
`systemctl list-units`, `systemctl show`, `docker ps`, `ss -tlnp`)

| Processo | Tipo | Estado hoje | Nota |
|---|---|---|---|
| `ibgateway.service` | service | **inactive/dead** | Dormência confirmada (era o alvo do fix crítico de 07-12) |
| `x11vnc` porta 5900 | processo interno do gateway | **fechado** | `ss -tlnp` mostra `127.0.0.1:5900` — só localhost, já não `0.0.0.0`. Fix do CRÍTICO de 07-12 confirmado a segurar |
| `ibeam` (Client Portal 24/7) | docker | **não existe nenhum container** | Removido, não só parado |
| `xvfb-ibgw.service` | service | inactive/dead | Acessório do gateway, dormente |
| Stack Docker `ib_bot` v1 (api/worker/beat/db/redis/web/nginx) | 7 containers | **ok, a correr** | api up 2 semanas (porta 8001), worker/beat up 6 dias (redeploy dos fixes de OOM), db/redis up 2 semanas, web+nginx (porta 8090) up 2 semanas. RAM total ~465 MiB — leve |
| Stack Docker `ib_bot-v2` (`:8092`) | — | **não existe nenhum container nem porta aberta** | Confirmado com `docker ps -a` e `ss -tlnp` — a "Plan B" duplicada do audit anterior foi desligada a sério |
| `ib-bot-v2-frontend.service` (`:3001`) | service | **active/running** | HTTP `curl localhost:3001/` → `307` (redirect normal). Fala com a API v1 `:8001` (`curl .../health` → `200`). É o painel que o José usa |
| `ib-backtests.timer` / `.service` | timer semanal (dom 04:15 UTC) | **timer active; último run OK** | Ver detalhe abaixo |
| `ib-backtests-alert.service` | OnFailure | armado | Recebeu 6 disparos reais em 07-19 (prova de que funciona) |
| `lifeos-ib-refresh.timer/.service` | timer diário 03:15 UTC | **ok** | Journal de hoje: `pushed: {"status":"ok","net_liq":26785.99,"positions":1,"sheet_synced":true}` — independente do gateway, usa o MCP |
| `theta-terminal.service` | service | **active, plano FREE** | Journal de hoje: `Bundle: STOCK.FREE, OPTION.FREE, INDEX.FREE` — **zero custo**, a subscrição paga de $80/mês nunca foi comprada (decisão do estudo 0006) |
| `paper-ironfly.timer` (repo `trading`) | timer diário | **ok, vigília passiva** | Ledger tem 44 eventos (era 3 em 07-13); estudo já morto, mas o José decidiu manter isto ligado como monitor de custo zero |
| `historical-backfill` / `execution-metrics` / `cost-recalibration` / `theta-learned` | services/timers | **ativos mas NÃO são deste projeto** | Descrição systemd confirma "Polymarket" — pertencem a outro projeto de trading, não ao ib_bot. Confirmado hoje via `systemctl list-units --all` |

### Backtest semanal — estado detalhado

- Última corrida bem-sucedida: início 2026-07-19 10:15:18 WEST, fim
  11:15:21 WEST (61 min), `Result=success`, `ExecMainStatus=0`,
  `MemoryPeak=1.625.137.152 bytes` (1,6 GiB — bem abaixo do teto de 24 GiB).
- Antes dessa corrida: **6 falhas seguidas** entre 06:34 e 10:09 do mesmo
  dia — `oom-kill` às 06:34, 07:39 e 08:21 (3×) e `signal` às 07:58, 09:59
  e 10:09 (3×) — confirmado via `journalctl -u ib-backtests.service
  --since '2026-07-19 06:00' --until '2026-07-19 12:00'`. A causa raiz
  (cache em memória sem limite + `OOMScoreAdjust` desproporcional) foi
  corrigida pelos commits `8835568`, `b4358ae`, `6439026` horas antes da
  corrida bem-sucedida.
- `.cache/plot_data.json`: 54 estratégias com séries de preços completas
  (mtime 2026-07-20 04:08 — este ficheiro é também tocado pelo coletor
  diário de alt-data, não só pelo backtest semanal). O log completo
  (`/var/log/ib-backtests.log`, 19,8 MB) confirma que a estratégia **"SMB
  Factor Regime"**, que falhava com "No tickers found" no audit anterior,
  **completou com sucesso** desta vez (312/312 segmentos processados).
- **Ainda por verificar**: esta foi uma corrida de **remediação manual**
  (root, fora do timer). O próximo disparo *normal* e não assistido do
  `ib-backtests.timer` é **domingo 2026-07-26 04:15 UTC** — ainda não
  aconteceu. Ver finding A1.

### Arquivo alt-data point-in-time (`altdata_snapshots`)

- Recomendação nº1 do audit v4 (26-mai): "a coisa de maior ROI é começar a
  guardar snapshots datados". Ficou vazia até 2026-07-13.
- Hoje (`captured_at::date, count(*) GROUP BY 1`): **8 dias distintos**
  de vintages, de 2026-07-13 (9 fontes) a 2026-07-20 (11 fontes), ~11
  linhas/dia de forma estável. Gate do plano de licenciamento B2B
  (fase `a1_altdata_b2b`, bloqueada no Conductor) exige **≥14 dias**
  consecutivos — faltam 6 dias, ETA **~2026-07-26** (mesma data do
  registo `plan_knowledge` do Conductor, consistente).

### Paper trading — curva de equity

- 2 contas paper na DB: conta 1 ("Main Paper") ficou **sempre em
  $100.000,00 flat** — nunca teve trades, é uma conta de controlo/vazia.
  Conta 2 é a real: 88 posições, 138 trades históricas (fev→mai), e desde
  2026-05-26 um coletor diário grava snapshots de equity.
- **55 pontos diários** de 2026-05-26 a 2026-07-19 (extraídos
  agora via SQL — ver `metrics.json`). Curva essencialmente **flat/ligeira
  queda**: começa em $177.973,30, termina em $176.579,28.
- Reconciliação de contabilidade (já feita em `docs/audits/2026-07-12_paper_ledger_reconciliacao.md`,
  re-verificada hoje): o saldo só fecha aritmeticamente com um
  **crédito de $70.000,00 sem lançamento de auditoria** — o endpoint
  `POST /paper/accounts/{id}/fund` (confirmado no `/openapi.json` — sem
  prefixo `/api`) altera `paper_cash.balance`
  diretamente, sem escrever numa tabela de depósitos. As 138 trades em si
  são internamente consistentes (zero mismatches). **Portanto o nível
  absoluto da curva não é evidência de skill — só a FORMA da curva desde
  26-mai é fiável**, e essa forma é "flat/perde ligeiramente".

### Estudo 0006 (earnings-vol / iron-fly, repo `trading`) — desfecho final

- A contradição do audit anterior (motor EOD dizia "perde sempre" PF
  0,06-0,37; motor intraday dizia "ganha" PF 1,42-1,78) foi **totalmente
  reconciliada** em 2026-07-13: o número 1,42-1,78 era um artefacto —
  17,1% dos eventos intraday tinham `max_risk≈0`, o que faz o retorno
  explodir matematicamente (`ret = pnl/max_risk`, chegando a 3,5×10¹⁵).
  Corrigido (`clip[-1,1]`), a PF intraday cai para **0,109** — pior que a
  EOD. **Os dois motores concordam: não há vantagem, em nenhum ano
  2020-2026.**
- O teste forward (dinheiro a fingir, dados reais) acumulou os 30+ eventos
  pré-registados: **36 eventos, KILL em 2026-07-16** (PF@mid 0,776,
  PF@touch 0,256 — realista com custos de execução é claramente perdedor).
- O timer `paper-ironfly.timer` continua ligado (44 eventos no ledger
  hoje) como vigília de custo zero, por decisão explícita do José — não é
  um erro, é intencional.

### Repositórios e worktrees

- `ib_bot` (principal): branch `main`, `git status` **limpo**, `HEAD`
  em `6c3e8c5`, sincronizado com `origin/main`.
- `ib_bot-v2`: worktree na branch `frontend-v2` (**decomissionada** —
  confirmado pela decisão Jarvis `ea643e7a` referida na memória: não
  precisa de ser importada para `main`), 1 ficheiro modificado
  (`.conductor/context.md`, irrelevante).
- `ib_bot-altdata-wt`: worktree na branch `alt-data-consolidation`, limpo.
- Existe ainda um worktree extra `ib_bot/.worktrees/phase-f5_altdata_arquivo-6090`
  (da fase `f5`, já `done`) — resíduo pequeno, não crítico.

### Estado do Conductor (orquestrador da frota de agentes)

- `projects.status` para `ib_bot` = **`paused`** (confirmado por SQL
  direto — bate certo com o brief).
- Plano ativo `e36e04ec-de9c-438f-b0e5-434dfa391154`: 7 de 8 fases
  `done` (`f1`…`f5`, `x1`, `x2`); a fase `a1_altdata_b2b` está `blocked`
  por um **time-gate genuíno** (precisa de 14 vintages, tem 8), com um job
  já agendado (`c52a5a91`, acorda 2026-07-26) para verificar e destravar
  sozinho — **não é preciso ação humana agora**.
- Plano antigo `3702771c` ("Alt-Data Product / Unusual Whales
  competitor") está `superseded` — não é a direção atual.
- Contagem de tabelas na base de dados do bot (`ib_bot-db-1`, schema
  `public`): **21 tabelas**, confirmado hoje via
  `SELECT count(*) FROM information_schema.tables WHERE table_schema='public'`.

---

## (d) Findings ordenados por gravidade

### CRÍTICO
*Nenhum encontrado nesta verificação.* O CRÍTICO do audit anterior (VNC
sem password) está confirmado corrigido (porta só em loopback, firewall
não é gerível por este agente mas a exposição de rede já não existe porque
o serviço nem está a correr).

### ALTO

**A1 — O fix do backtest semanal ainda não foi provado num disparo normal
e não assistido.**
A corrida bem-sucedida de 56/56 estratégias (2026-07-19, 10:15-11:15) foi
uma **remediação manual como root**, feita horas depois de 6 falhas
seguidas (`oom-kill` às 06:34, 07:39, 08:21 — 3×; `signal` às 07:58,
09:59, 10:09 — 3×) na madrugada do mesmo dia. Os commits que corrigem a
causa (`8835568` cache com limite, `b4358ae` prioridade de OOM
proporcional, `6439026` deploy em produção) estão no `main`, mas o
**próximo disparo automático do `ib-backtests.timer` só acontece domingo
2026-07-26 04:15 UTC** — ainda não aconteceu. Se falhar outra vez sem
assistência, o `OnFailure` está armado (confirmado: 6 recibos reais em
07-19) e acorda o Domain Manager do Conductor, mas ninguém verificou ainda
que esse caminho completo (falha → alerta → DM resolve) funciona
ponta-a-ponta num disparo *não manual*.
**Evidência:** `systemctl show ib-backtests.service --property=Result,ExecMainStatus,MemoryPeak`
→ `success/0/1625137152`; `journalctl -u ib-backtests.service --since "2026-07-19 06:00" --until "2026-07-19 12:00"`
→ 6 falhas antes do sucesso (06:34, 07:39, 07:58, 08:21, 09:59, 10:09).

**A2 — O bug que causou o crédito de $70.000 sem auditoria continua no
código, não só no passado.**
A investigação de 07-13 (re-confirmada hoje) explica a origem mais
provável (endpoint `POST /paper/accounts/{id}/fund` — sem prefixo `/api`,
confirmado no `/openapi.json` — que escreve
`paper_cash.balance` diretamente) mas **não corrigiu o endpoint** — ele
continua a aceitar um crédito positivo sem criar uma linha de ledger. Isto
não é dinheiro real (é paper), mas é um padrão de código perigoso: se
algum dia o mesmo padrão existir num caminho de dinheiro real, um crédito
poderia acontecer sem rasto de quem, quando ou porquê.
**Evidência:** `docs/audits/2026-07-12_paper_ledger_reconciliacao.md`,
secção "3. Top-up manual de $70.000"; código
`acct.balance = float(acct.balance) + float(body.amount)` sem escrita em
tabela de auditoria.

### MÉDIO

**M1 — Nenhuma decisão com data marcada para quando o gate de 14 dias
abrir (~2026-07-26).**
O arquivo alt-data está a crescer de forma saudável e vai destravar a fase
`a1_altdata_b2b` sozinho por volta de 2026-07-26. Mas não há, nem no
Conductor nem nas memórias, uma data marcada para o José decidir entre os
3 caminhos identificados pelo audit v4 (licenciar dados B2B / retomar em
modo pessoal-família / matar de vez). Sem essa decisão, o projeto fica
"pausado para sempre" por inércia, mesmo depois de todo o trabalho de
preparação estar pronto.

**M2 — Cache de preços em disco cresce sem limpeza automática.**
`.cache/yf_prices/` tem **2.752 ficheiros, 473 MB** hoje, e cresce
todas as semanas (o backtest semanal só limita a *memória* — 128 tickers
em RAM, commit `8835568` — não o disco). A médio prazo (anos) isto cresce
sem controlo. Não é urgente (473 MB é pequeno face aos 685 GB livres no
disco), mas não há política de retenção.

**M3 — Sem teste de regressão a garantir que as 56 estratégias continuam
todas a correr.**
A estratégia "SMB Factor Regime" já falhou uma vez no passado ("No
tickers found", ver audit de 07-12) e voltou a funcionar agora, mas não
existe nenhum teste automático que falhe o CI/pipeline se isto voltar a
quebrar — só se descobre olhando ao log de 19 MB à mão.

### BAIXO

**B1 — Resíduo de worktree da fase `f5` (já `done`) ainda no disco.**
`ib_bot/.worktrees/phase-f5_altdata_arquivo-6090` não foi limpo após a
fase terminar. Inofensivo, só desarruma.

**B2 — `docker system df` mostra 52 GB de imagens e 28 GB de build cache
reclamáveis no host** — mas isto é **partilhado por todos os projetos do
servidor**, não é específico do ib_bot; mencionado só para contexto, sem
ação recomendada aqui (seria decisão a nível de servidor, não de projeto).

---

## (e) Actionable steps ranked (o que fazer primeiro e porquê)

1. **Verificar o disparo normal do backtest de domingo 2026-07-26** (A1) —
   é o único item com risco real de voltar a falhar sem ninguém notar;
   basta 1 comando de verificação, sem mudar código. Ver plano de fixes
   passo 1.
2. **Fechar o buraco do endpoint de funding paper** (A2) — corrige a causa
   raiz, não só o sintoma; baixo esforço (adicionar 1 tabela + 1 escrita).
   Ver plano de fixes passo 2.
3. **Marcar a data de decisão estratégica para ~2026-07-26** (M1) — sem
   isto, todo o trabalho de preparação (arquivo, reconciliação,
   dormência) não converte em ação; é o gate mais importante do projeto.
   Ver plano futuro "decisão estratégica".
4. Adicionar retenção ao cache de disco (M2) e um teste de regressão às
   56 estratégias (M3) — baixo risco, baixo esforço, fazem parte do
   "deixar isto seguro enquanto ninguém olha".
5. Limpar o worktree residual (B1) — 30 segundos, zero risco.

---

## (f) Riscos se nada for feito

- **Financeiro direto: baixo.** Zero ordens reais desde sempre, gateway
  live desligado, API read-only na conta real do bot, subscrição paga de
  dados (ThetaData) nunca comprada. O único dinheiro real ligado a esta
  família de contas é a posição pessoal do José (BRK B) — não gerida por
  código deste projeto.
- **Risco operacional se o backtest semanal voltar a falhar sem
  supervisão:** baixo impacto direto (é só uma simulação), mas desperdiça
  recursos do servidor repetidamente (5 tentativas em poucas horas em
  07-19) e pode mascarar um problema maior se o padrão se repetir sem
  ninguém a olhar — o `OnFailure` existe mas nunca foi testado num
  disparo 100% não-assistido.
- **Risco de oportunidade:** o trabalho de arquivar dados point-in-time
  (o único ativo que "ganha valor sozinho", segundo o audit v4) está a
  correr bem, mas se ninguém marcar a decisão de licenciamento B2B para
  quando o gate abrir (~26 de julho), o arquivo continua a crescer sem
  nunca ser convertido em receita — o cenário exato que o audit v4 já
  tinha avisado ("engine é live-pull, não guarda vintages" — isso já foi
  corrigido; agora falta o passo comercial).
- **Risco de deriva silenciosa:** se este audit não se repetir (é a 2ª
  vez em 8 dias), pequenas regressões como a do funding endpoint (A2) ou
  do cache sem limite (M2) tendem a acumular-se sem serem notadas —
  nenhuma delas é urgente isoladamente, mas juntas erodem a confiança nos
  números que alimentam qualquer decisão futura.

---

## (g) Glossário

| Termo | Explicação |
|---|---|
| IB / Interactive Brokers | A corretora — empresa através da qual se compram/vendem ações. O "IB Gateway" é o programa dela que dá acesso à conta a partir de código. |
| MCP (Model Context Protocol) | Um "protocolo" (conjunto de regras combinadas) que permite a este agente de IA falar diretamente com sistemas externos (aqui, a conta IB do José) de forma seca seaurizada, sem ver passwords. |
| API | Application Programming Interface — a "porta" por onde dois programas falam um com o outro. |
| Backtest | Simulação histórica: "quanto teria ganho se tivesse seguido esta regra nos últimos anos". |
| Paper trading | Negociar com dinheiro a fingir para testar o sistema sem risco. |
| 13F | Relatório trimestral que os grandes fundos americanos são obrigados a entregar ao regulador (SEC) a listar as ações que têm — é público, e o bot usa-o para os imitar. |
| Alpha vs beta | Alpha é o ganho que vem de habilidade/informação real; beta é o ganho que qualquer pessoa teria só por estar no mercado (ex.: o índice sobe, tudo sobe). |
| Deflated Sharpe | Medida de "ganho por risco" corrigida pelo número de tentativas: se testas 56 estratégias, a melhor parece boa por pura sorte; esta correção desconta isso. |
| Iron-fly | Aposta com opções em que se ganha se a ação mexer POUCO no dia dos resultados: vende-se o "seguro" caro no preço atual e compram-se proteções mais afastadas para limitar a perda máxima. |
| PF (Profit Factor) | Soma de tudo o que se ganhou a dividir pela soma de tudo o que se perdeu; acima de 1 é lucrativo. |
| EOD vs intraday | EOD (end of day) = um preço por dia, ao fecho; intraday = preços ao longo do dia. |
| Point-in-time / vintage | Guardar os dados exatamente como eram naquele dia. Sem isto, os backtests fazem batota sem querer (usam informação que só apareceu depois). |
| VNC / x11vnc | Programa que deixa ver e controlar o ecrã de outro computador à distância — como um TeamViewer básico. |
| systemd timer | O "despertador" do Linux: liga um programa automaticamente a horas certas. |
| OOM / oom-kill | Out Of Memory — quando um programa pede mais memória RAM do que existe, o sistema operativo mata-o à força para não travar a máquina toda. |
| ThetaData | Fornecedor de dados históricos de opções; o plano gratuito não dá preços ao longo do dia, só o pago (nunca comprado aqui). |
| Conductor / Domain Manager (DM) | O orquestrador de agentes de IA deste servidor; o "DM" é o agente responsável por um projeto específico (aqui, `ib_bot`). |
| Gate / time-gate | Uma condição que só se cumpre com o passar do tempo (aqui: esperar 14 dias de dados). Não é um bloqueio de decisão, é matemática de calendário. |
| Drawdown (maxDD) | A maior queda desde um pico até ao fundo seguinte — mede o pior momento para quem tivesse entrado no topo. |
