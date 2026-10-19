# Futuro — Decisão Estratégica: reativar, manter dormente, ou encerrar (2026-10-19)

**Gate de arranque:** só começa quando o passo 2 do plano de fixes (`docs/plans/
2026-10-19_plano_fixes.md`) estiver verde — verificar com:
```bash
psql -U servidor -d conductor -c \
  "SELECT id, status, title FROM project_plans WHERE slug='ib_bot' ORDER BY updated_at DESC LIMIT 1;"
```
→ esperado: existe um plano com dono formal (não `superseded`/`done`). Sem dono formal, esta
decisão corre o risco de ficar, como as anteriores, pendente por meses sem ninguém a cobrar.

## Contexto para o executor (lê isto primeiro, sem precisar da conversa original)

O `ib_bot` testou 56 estratégias de "copiar os espertos" (políticos dos EUA, 13F de fundos
famosos, apostas de Michael Burry) e todas reprovaram num teste estatístico rigoroso (Deflated
Sharpe Ratio) em maio de 2026 — nenhuma tem ganho real acima do que se esperaria por sorte. O
projeto está pausado desde então ao nível de decisão de negócio. Este plano **não é um plano de
engenharia** — é um plano para ajudar o José a decidir, com as 3 opções concretas e o que cada
uma implica em esforço/custo/risco, e os passos de EXECUÇÃO para a opção escolhida.

**Dados de apoio à decisão (re-verificados no audit de 2026-10-19):**
- Paper trading (dinheiro fictício) da carteira de produção (conta 2, "V1 Core"): **−0,92%** em
  146 dias, Sharpe anualizado **−0,14**, Sortino **−0,19**, máxima queda **−5,43%**. Isto é
  evidência adicional (não só o Deflated Sharpe Ratio teórico de maio) de que o sistema, tal como
  está, perde dinheiro fictício em condições reais de mercado.
- Zero ordens reais em toda a história (`ib_orders=0`), zero risco monetário acumulado.
- Custo de manter tudo como está: **insignificante em compute** (<0,5% CPU, <400MB RAM), mas
  **~65GB de disco** em imagens Docker (parcialmente resolvido pelo plano de fixes) e **~99 dias
  e a crescer** de dados PIT sem destino de negócio definido.

**Paths importantes:** ver secção "Paths importantes" do plano de fixes (`docs/plans/
2026-10-19_plano_fixes.md`) — os mesmos se aplicam aqui.

**Regras obrigatórias:** as mesmas do plano de fixes (read-only em produção real, commit no
mesmo turn, `runjob` para trabalho pesado, nunca tocar `ibgateway.service` sem decisão explícita
do José).

---

## Passo 1 — Apresentar as 3 opções ao José e obter decisão explícita

**Objetivo:** não avançar com nenhuma ação de engenharia antes de o José escolher uma das 3
opções abaixo. Isto é uma decisão de negócio, não técnica.

**Opção A — Reativar com investigação de novas ideias.** Implica: gerar um novo conjunto de
hipóteses de estratégia (fora das 56 já reprovadas e do estudo 0006 já morto), correr o motor de
backtest existente sobre elas, e só considerar execução real depois de outro Deflated Sharpe
Ratio independente. Esforço estimado: várias semanas de investigação de dados + validação
estatística, sem garantia de encontrar edge novo (o mercado de "seguir políticos"/"seguir 13F" já
está competido por ETFs públicos como a NANC, conforme a auditoria de maio documentou).

**Opção B — Manter dormência indefinidamente, mas com revisão trimestral explícita em vez de
auditorias semanais.** Implica: nenhuma ação de engenharia nova; reduzir a cadência de auditoria
(este processo semanal) para trimestral, mantendo os timers automáticos (backtest, PIT, paper
trading) a correr como estão, com o dono formal do passo 2 do plano de fixes a vigiar só para
falhas críticas (não para progresso de negócio).

**Opção C — Encerramento ordenado.** Implica: parar todos os timers e containers do bot (backtest
semanal, paper trading, altdata QA/backup), arquivar o código e os dados num snapshot final, e
desligar a stack Docker. Preserva o histórico (git + backup final dos dados PIT) mas para de
gastar qualquer recurso, mesmo que insignificante. Ver passo 3 para os comandos exatos SE esta
opção for escolhida.

**Comandos exatos:** nenhum ainda — este passo é uma conversa/decisão com o José. Registar a
decisão por escrito (memória ou plano Conductor) antes de avançar para qualquer passo seguinte.

**Oracle de aceitação:** existe um registo explícito (memória `MEMORY-trading.md` ou campo do
plano Conductor do passo 2 do plano de fixes) com a frase "José decidiu: Opção [A/B/C]" e a data.

**Rollback:** não aplicável (decisão, não ação de sistema).

**Gotchas:** não assumir que "pausado há 5 meses" significa "José já decidiu B implicitamente" —
as 12 auditorias anteriores já documentaram isto como pendente; forçar uma decisão explícita em
vez de continuar a assumir o status quo.

---

## Passo 2 — SE Opção A (reativar): preparar o terreno para investigação de novas ideias

**Objetivo:** só executar se o José escolher a Opção A no passo 1.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git worktree add -b research/new-strategy-ideas-20261019 \
  /home/servidor/ib-new-strategies-20261019 \
  main
cd /home/servidor/ib-new-strategies-20261019
# Listar as 56 estratégias já testadas e reprovadas, para não repetir ideias
docker exec ib_bot-db-1 psql -U ibbot_app -d ibbot -c "SELECT name FROM strategies ORDER BY name;"
# Ler o relatório de maio (Deflated Sharpe Ratio) para entender QUE TIPO de ideia já foi
# eliminada e porquê, antes de gerar ideias novas
find . -iname "*deflated*" -o -iname "*investibilidade*" 2>/dev/null
```

**Oracle de aceitação:** um documento novo (`docs/research/2026-XX_novas_ideias.md`) com pelo
menos 3 hipóteses de estratégia NÃO cobertas pelas 56 já testadas, cada uma com uma fonte de dados
concreta e disponível (verificar se já existe em `altdata_snapshots` ou se precisa de uma fonte
nova).

**Rollback:**
```bash
git worktree remove /home/servidor/ib-new-strategies-20261019 --force
```

**Gotchas:** qualquer ideia que dependa de "seguir políticos" ou "seguir 13F" já está coberta
pelas 56 reprovadas E compete com ETFs públicos (NANC) — evitar reciclar a mesma categoria de
sinal sem uma vantagem clara e nova.

---

## Passo 3 — SE Opção C (encerrar): parar tudo de forma ordenada

**Objetivo:** só executar se o José escolher a Opção C no passo 1, e só depois de confirmação
explícita adicional (esta é uma ação com impacto — parar serviços — por isso exige confirmação
mesmo dentro de um plano já aprovado).

**Comandos exatos:**
```bash
# 3a. Backup final dos dados PIT antes de parar qualquer coisa
cd /home/servidor/Desktop/cursor-projects/ib_bot
bash infra/scripts/backup_altdata_snapshots.sh
git log -1 --format='%H' # confirmar o backup ficou commitado

# 3b. Parar os timers (NÃO apagar as unidades ainda — só desativar)
sudo systemctl disable --now ib-altdata-qa.timer ib-altdata-backup.timer \
  ib-backtests.timer ib-docker-prune.timer

# 3c. Parar a stack Docker (preserva os volumes, não apaga dados)
docker compose -f docker-compose.yml down

# 3d. Confirmar paragem completa
systemctl list-timers --all | grep -i ib-
docker ps -a --filter name=ib_bot
```

**Oracle de aceitação:**
```bash
systemctl list-timers --all | grep -i ib- # esperado: vazio ou todos "inactive"
docker ps --filter name=ib_bot # esperado: vazio (nenhum container a correr)
```

**Rollback:**
```bash
sudo systemctl enable --now ib-altdata-qa.timer ib-altdata-backup.timer \
  ib-backtests.timer ib-docker-prune.timer
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker compose -f docker-compose.yml up -d
```

**Gotchas:**
- `docker compose down` SEM `-v` preserva os volumes (incluindo a base de dados Postgres) — nunca
  usar `-v` neste passo, isso apagaria `paper_snapshots`/`altdata_snapshots` permanentemente.
- Este passo não apaga o repositório git nem o histórico — só para os processos em execução.
- Confirmar que `ibeam-primary` (fora do compose do bot) também é parado se já não for necessário
  para mais nada no host (verificar com outros donos antes, pode ser usado por outro projeto).

---

## Fecho do plano

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git status --porcelain   # esperado: vazio
```
Registar a decisão final e a opção escolhida no plano Conductor criado no passo 2 do plano de
fixes, marcando-o `done` ou atualizando o seu âmbito conforme a opção.
