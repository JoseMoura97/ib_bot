# Plano de fixes — IB Bot (2026-10-05)

## Contexto para o executor (lê isto antes de tocares em qualquer coisa)

Este ficheiro tem de dar a um modelo/agente FRACO, sem esta conversa, tudo o que precisa para
executar do zero.

**O que é o projeto:** o IB Bot é um robô de trading que testou 56 estratégias de investimento
(copiar políticos dos EUA, fundos como Warren Buffett, etc.) contra a corretora Interactive
Brokers (IB). Está **PAUSADO desde julho de 2026** ao nível de decisão de negócio: o motor de
execução real (que enviaria ordens verdadeiras) está desligado e deve continuar desligado. Duas
coisas continuam a correr sozinhas todos os dias: (1) um arquivo de dados públicos
("point-in-time" / PIT) e (2) um simulador de "paper trading" (dinheiro falso) — a conta 1 deste
simulador foi corrigida em 2026-09-28, mas a conta 2 continua a falhar com um erro diferente
(ver Passo 1).

**Paths importantes:**
- Repositório principal (onde os jobs agendados publicam): `/home/servidor/Desktop/cursor-projects/ib_bot`
  — **branch `main` só para jobs agendados**, nunca faças trabalho de teste/investigação aqui
  diretamente (regra em `AGENTS.md` do próprio repo, imposta desde 2026-09-24 pelo commit
  `486b6e3`). Para qualquer investigação/edição, cria um worktree novo primeiro:
  ```
  git -C /home/servidor/Desktop/cursor-projects/ib_bot worktree add -b <branch-nova> <caminho-novo-fora-do-repo> main
  ```
- Segundo worktree (checkout antigo do frontend v2, Next.js) — ainda existe em disco mas a stack
  Docker e o serviço systemd que o serviam já não existem (ver achado #2 do audit de hoje):
  `/home/servidor/Desktop/cursor-projects/ib_bot-v2`. Não precisas de tocar nele para este plano.
- Stack Docker Compose (a única viva): dentro do repo principal, containers `ib_bot-api-1`,
  `ib_bot-worker-1`, `ib_bot-beat-1`, `ib_bot-db-1` (Postgres), `ib_bot-redis-1`, `ib_bot-web-1`,
  `ib_bot-nginx-1`.
- Base de dados: Postgres dentro do container `ib_bot-db-1`. Acesso:
  `docker exec -it ib_bot-db-1 psql -U ibbot -d ibbot`. **NÃO exposta ao host** (sem porta
  publicada) — só acessível via `docker exec`.
- Credenciais: `.env` na raiz do repo principal (não o leias/imprimas nesta tarefa a menos que
  seja estritamente necessário para o fix; nunca commites segredos).
- Conta pessoal do José na IB é lida via o conector MCP `Interactive Brokers (IBKR)`
  (`get_account_summary`, `get_account_positions`, etc.), ou — se esse MCP não estiver
  autorizado na tua sessão — via o registo diário do timer `lifeos-ib-refresh.service`
  (`journalctl -u lifeos-ib-refresh.service`). Esta conta **não tem nada a ver com o bot**, é a
  conta pessoal dele, gerida manualmente. Não mexer.

**Regras duras para quem executar este plano:**
- **Money-path (qualquer coisa que possa levar a uma ordem real):** exige aprovação síncrona do
  José via `request_user_approval` ANTES de qualquer alteração a `system/execution/`,
  `backend/app/api/routes/live.py`, ao gateway (`ibgateway.service`/`xvfb-ibgw.service`), ou a
  qualquer variável `LIVE_*`/`ENABLE_LIVE_TRADING`. **Nenhum passo deste plano deveria precisar
  disto** — o paper trading não é money-path (dinheiro fictício), mas se achares a meio que
  precisas de tocar em algo da lista acima, PARA e pergunta primeiro.
- **Commit no mesmo turn:** depois de qualquer alteração de código verificada, faz commit no
  mesmo turno (branch de trabalho, nunca direto em `main` do checkout principal — ver regra
  `AGENTS.md` acima). Integração em `main` é uma decisão deliberada (merge depois de testar no
  worktree), não automática.
- **`runjob` para trabalho pesado:** se algum passo abaixo precisar de correr o backtest completo
  das 56 estratégias (pode demorar >1h), usa
  `runjob --mem 8G --cpu 8 --name ib-bot-fix-verify -- <comando>`, nunca um processo solto.
- **Não dupliques planos:** antes de começares, confirma que não há já um plano `executing` para
  `ib_bot` no Conductor:
  ```
  psql -U servidor -d conductor -c "SELECT id,status,title FROM project_plans WHERE slug='ib_bot' AND status IN ('draft','approved','executing','paused','gated');"
  ```
  Se devolver alguma linha, PARA e avisa o José antes de continuar (pode já estar a ser feito).

---

## Passo 1 — Diagnosticar e corrigir o erro `insufficient cash` na conta 2 do paper rebalance

**Objetivo:** a tarefa diária `paper_rebalance_daily_task` falha todos os dias desde 2026-09-28
para a conta 2 (`portfolio_id=d2e87bea-0cd8-4175-82b0-3282ec8828dc`) com
`HTTPException: 400: insufficient cash`, enquanto a conta 1 já executa normalmente desde o mesmo
dia. Encontrar a causa e corrigir, sem tocar em dinheiro real (é tudo paper).

**Comandos exatos — passo 1a, reproduzir e ler o erro completo (read-only, dentro do worktree, não no checkout principal):**
```
git -C /home/servidor/Desktop/cursor-projects/ib_bot worktree add -b fix/paper-rebalance-acct2-cash-20261005 \
  /home/servidor/ib-bot-fix-acct2-cash-20261005 main

docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT account_id, status, n_orders, timestamp, details->>'error', details->>'traceback' \
   FROM paper_rebalance_logs WHERE account_id=2 AND status='ERROR' ORDER BY timestamp DESC LIMIT 1;"

docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT id, cash, equity FROM paper_cash WHERE id=2;"
```
Isto dá o traceback completo (já guardado desde o fix de 09-28) e o caixa disponível real da
conta 2 no momento do erro.

**Comandos exatos — passo 1b, ler o código relevante:**
```
sed -n '1,80p' /home/servidor/ib-bot-fix-acct2-cash-20261005/backend/app/api/routes/paper.py | grep -n "insufficient cash" -A5 -B20
sed -n '264,414p' /home/servidor/ib-bot-fix-acct2-cash-20261005/backend/app/api/routes/paper.py
sed -n '480,572p' /home/servidor/ib-bot-fix-acct2-cash-20261005/backend/app/worker/tasks.py
```
Procura onde o `allocation_amount`/pesos combinados são calculados para a conta 2 vs conta 1 —
a hipótese mais provável (a confirmar com os dados do passo 1a, não assumir) é que o
`allocation_amount` passado pela tarefa diária para a conta 2 (mais rica, ~$180k, 9 estratégias
combinadas) ultrapassa o caixa disponível quando combinado com posições já abertas, enquanto a
conta 1 (mais pequena) não tinha esse problema por acaso de escala.

**Oracle de aceitação:**
1. Ficheiro `backend/tests/test_paper_rebalance_cycles.py` ganha um teste novo que reproduz
   exatamente este cenário (conta com caixa insuficiente para os pesos combinados calculados) e
   confirma que, depois do fix, a função devolve uma resposta tratada (ex.: reduzir pesos
   proporcionalmente até caber no caixa disponível, ou pular a perna que não cabe e registar
   `status=PARTIAL` em vez de abortar tudo com `400`) em vez de levantar excepção.
2. `pytest backend/tests/test_paper_rebalance_cycles.py -v` → todos os testes passam, incluindo o
   novo.
3. Depois de mergear para `main` (ver regra de commit acima) e esperar 1 corrida real do timer
   (15:00 WEST do dia seguinte), confirmar com:
   ```
   docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
     "SELECT account_id, status, n_orders FROM paper_rebalance_logs WHERE account_id=2 ORDER BY timestamp DESC LIMIT 1;"
   ```
   deve devolver `status` diferente de `ERROR` (ou `ERROR` com uma razão de negócio explícita e
   documentada, não um crash).

**Rollback:**
```
git -C /home/servidor/Desktop/cursor-projects/ib_bot worktree remove /home/servidor/ib-bot-fix-acct2-cash-20261005 --force
```
Se já tiver sido mergeado para `main`: `git -C /home/servidor/Desktop/cursor-projects/ib_bot revert <sha-do-merge>`.

**Gotchas:**
- Não misturar isto com o fix de 09-28 (`1391c6f`) — esse já está em `main`, não o refazer.
- Não assumir a causa sem ler o traceback real do passo 1a primeiro — "insufficient cash" pode
  também ser uma proteção legítima a funcionar corretamente contra um bug diferente a montante
  (ex.: um peso calculado errado a pedir 200% do caixa). Confirma com números reais antes de
  decidir que tipo de fix aplicar.
- É dinheiro fictício (paper) — não há aprovação de `request_user_approval` necessária para este
  passo, só para qualquer coisa que tocasse no caminho de execução real (`system/execution/`).

---

## Passo 2 — Confirmar recuperação automática do `ib-altdata-backup.service`

**Objetivo:** a unidade falhou hoje de madrugada (04:34 WEST) por "working tree is dirty"; a
causa já foi corrigida no mesmo turno por outro operador (commit `1668947`). Confirmar que o
próximo disparo normal (amanhã, ~04:3x WEST) recupera sozinho, sem intervenção.

**Comandos exatos (correr no dia seguinte a este plano ser lido, depois das ~04:40 WEST):**
```
systemctl status ib-altdata-backup.service --no-pager
journalctl -u ib-altdata-backup.service --since "today" --no-pager | tail -20
git -C /home/servidor/Desktop/cursor-projects/ib_bot log -1 --format='%h %s'
```

**Oracle de aceitação:** `systemctl status` mostra `Active: inactive (dead)` com
`Result: success` (não `failed`), o `journalctl` mostra um commit `backup(altdata): PIT table ...`
publicado com sucesso, e o `git log -1` mostra esse commit como o mais recente em `main`.

**Rollback:** nenhum (é só uma verificação).

**Gotchas:** se a unidade falhar de novo por um motivo diferente, NÃO assumir que é o mesmo bug
de "dirty tree" — ler a mensagem de erro completa primeiro (`journalctl`) antes de qualquer
decisão.

---

## Passo 3 — Limpar imagens e build cache Docker (61 GB + 36 GB reclamáveis)

**Objetivo:** recuperar espaço em disco sem risco — são todas imagens/camadas não usadas por
nenhum container vivo.

**Comandos exatos:**
```
docker system df
docker ps -a --format '{{.Names}}' | grep -i ib_bot   # confirmar que os 7 containers vivos continuam Up ANTES de limpar
docker image prune -a -f --filter "until=48h"
docker builder prune -f --filter "until=48h"
docker system df   # confirmar depois
```
O filtro `until=48h` evita apagar camadas de build em uso por uma build em curso (se alguma
estiver a correr neste momento — confirmar com `docker ps` que não há `docker build`/`docker
compose build` ativo antes de correr isto).

**Oracle de aceitação:** segundo `docker system df`, `Images` reclamável cai para perto de 0 GB
(só as imagens dos 7 containers vivos ficam), e os 7 containers `ib_bot-*` continuam `Up` depois
(`docker ps -a --filter name=ib_bot`).

**Rollback:** nenhum (imagens apagadas podem ser recriadas com `docker compose build`/`docker
compose pull` se algum dia forem precisas de novo; não há perda de dados, só de camadas em cache).

**Gotchas:** correr isto fora da janela do backtest semanal (domingo ~04:15-05:45 WEST) e fora da
janela do backup/QA noturnos (~04:3x e ~08:00 WEST), para não competir por I/O de disco com um job
agendado a meio da corrida.

---

## Passo 4 — Levar a decisão pendente do arquivo PIT ao José (quase 2 meses em aberto)

**Objetivo:** fechar o ciclo "auditoria escreve, ninguém decide" sobre o destino do arquivo
`altdata_snapshots` (932 linhas, 85 dias, a crescer ~11/dia), que está pronto para decisão desde
2026-08-11 (one-pager já escrito em `docs/altdata_b2b_one_pager_draft.md`).

**Comandos exatos:**
```
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "select source, count(*), min(captured_at), max(captured_at) from altdata_snapshots group by source order by count desc;"
cat /home/servidor/Desktop/cursor-projects/ib_bot/docs/altdata_b2b_one_pager_draft.md
```
Confirmar que o one-pager ainda reflete números atuais (fontes, dias, tamanho); se desatualizado,
atualizar os números antes de enviar. Depois usar `request_user_approval` com as 3 opções já
identificadas pelas auditorias anteriores: (a) avançar com outreach comercial de licenciamento
B2B, (b) arquivar e parar de alimentar, (c) continuar a acumular sem plano de uso, com data de
reavaliação marcada (ex.: dentro de 3 meses).

**Oracle de aceitação:** entrada de memória nova com a decisão e data, e (se a resposta for
(a) ou (b)) o plano Conductor correspondente passa de `superseded`/inexistente para um novo plano
`draft`/`approved` com essa decisão como objetivo.

**Rollback:** nenhum (é uma decisão de negócio, não uma alteração técnica).

**Gotchas:** não reenviar a proposta antiga do plano `3702771c` sem reler se as suposições de
mercado (concorrentes Unusual Whales/Quiver, preços) ainda são válidas 5 meses depois.

---

## Passo 5 — Atualizar ou remover os ficheiros desatualizados `docs/audits/ib_bot/*.json`

**Objetivo:** `docs/audits/ib_bot/metrics.json` e `section.json`, deixados pela 1ª auditoria
(07-12) dentro do próprio repositório do projeto (em vez do caminho de scratch fora do repo),
descrevem o estudo 0006 como "por reconciliar" — já reconciliado (KILL) desde 07-16. Isto pode
confundir um agente futuro que leia o repo sem o histórico completo das auditorias.

**Comandos exatos:**
```
git -C /home/servidor/Desktop/cursor-projects/ib_bot log --follow --oneline -- docs/audits/ib_bot/metrics.json
git -C /home/servidor/Desktop/cursor-projects/ib_bot rm docs/audits/ib_bot/metrics.json docs/audits/ib_bot/section.json
git -C /home/servidor/Desktop/cursor-projects/ib_bot commit -m "chore: remove stale scratch audit json left in repo by 2026-07-12 audit"
```
(Fazer isto num worktree/branch de trabalho, não direto em `main`, e mergear depois de confirmar
que nenhum outro processo automático lê esses caminhos — confirmar com
`grep -rn "docs/audits/ib_bot" /home/servidor/Desktop/cursor-projects/ib_bot --include=*.py
--include=*.sh` antes de remover.)

**Oracle de aceitação:** `grep` acima devolve zero referências de código a esses caminhos (só
documentação/histórico, se alguma), e depois da remoção `git log` confirma o commit.

**Rollback:** `git revert <sha>` (os ficheiros voltam).

**Gotchas:** se o `grep` encontrar alguma referência de código viva, PARA — não remover, só
atualizar o conteúdo dos JSON em vez de apagar os ficheiros.
