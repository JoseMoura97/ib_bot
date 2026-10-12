# Plano de Fixes — IB Bot (2026-10-12)

## Contexto para o executor (lê isto primeiro, sem precisar da conversa original)

**O que é este projeto:** o `ib_bot` é um robô de trading automático (compra/venda de ações) que
usava a conta do José na Interactive Brokers (IB, a corretora). Testou 56 estratégias e todas
reprovaram num teste estatístico rigoroso (Deflated Sharpe Ratio) em maio de 2026 — nenhuma tem
edge real. O projeto está **PAUSED** (pausado) desde então: não se decide o próximo passo de
negócio, mas processos automáticos (backtests semanais, arquivo de dados diário, paper trading)
continuam a correr sozinhos. **NUNCA houve uma ordem real executada** (`ib_orders=0` desde sempre)
e o gateway que ligaria à IB está desligado desde 2026-08-27. Lê
`docs/audits/2026-10-12_audit_profundo.md` (o audit que gerou este plano) para o estado completo.

**Paths importantes:**
- Repositório: `/home/servidor/Desktop/cursor-projects/ib_bot` (branch `main`, único checkout que
  os timers automáticos usam — NUNCA mudar a sua branch, ver `AGENTS.md` no root do repo).
- Para trabalho de edição/teste, criar um worktree separado: `git worktree add -b <branch>
  <path-separado> main` e trabalhar lá. Só integrar em `main` depois de validado.
- Base de dados do bot: Postgres dentro do container `ib_bot-db-1` (user `ibbot`, db `ibbot`).
  Acede-se com `docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "<query>"`.
- Credenciais: ficheiro `/home/servidor/Desktop/cursor-projects/ib_bot/.env` (permissões 600, só o
  utilizador `servidor`). **Nunca imprimir os valores** — só confirmar que as chaves/flags
  existem com `grep -E "^NOME_DA_CHAVE=" .env` (sem mostrar o valor em logs partilhados, exceto
  flags não-secretas como `ENABLE_LIVE_TRADING`/`TRADING_HALT`).
- Código do bug principal: `backend/app/api/routes/paper.py` (rota `paper_rebalance_execute` /
  `paper_rebalance_execute_core`), chamada pela tarefa Celery `paper_rebalance_daily_task`.
- Logs da tarefa: tabela `paper_rebalance_logs` na BD; logs do container:
  `docker logs ib_bot-worker-1`.

**Regras obrigatórias para quem executar este plano:**
1. **READ-ONLY em produção real** — este projeto nunca deve enviar ordens reais. Qualquer alteração
   de código que toque em `ENABLE_LIVE_TRADING`, `ib_orders`, ou no caminho de execução real
   (`backend/app/live/`, se existir) exige aprovação explícita do José antes de aplicar
   (`request_user_approval` ou pedido direto) — isto é "money-path", mesmo que `ENABLE_LIVE_TRADING`
   esteja hoje em `false`. Os fixes abaixo tocam SÓ no caminho de **paper trading** (dinheiro
   fictício) — não é money-path real, mas documenta-se a mesma disciplina.
2. **Commit no mesmo turn.** Depois de cada passo verificado (oracle de aceitação a passar), fazer
   `git commit` imediatamente nesse mesmo turno — não deixar trabalho stageado.
3. **`runjob` para trabalho pesado.** Se algum passo precisar de correr o backtest completo
   (`run_all_backtests.py`, ~28 min) ou outro job pesado, usar
   `runjob --mem 4G --cpu 4 -- <comando>` em vez de correr diretamente.
4. **Nunca editar um payload de `*-release-<sha>`** — este projeto não usa o sistema de release do
   cluster polymarket, não é relevante aqui, mas a disciplina de nunca sobrescrever artefactos
   publicados aplica-se da mesma forma: commitar, nunca editar histórico.
5. **Timers não podem ficar sem o seu checkout.** O checkout principal (`main` em
   `/home/servidor/Desktop/cursor-projects/ib_bot`) é usado por `ib-altdata-backup.service` e
   `ib-altdata-qa.service` todas as noites — nunca o deixar com `git status` sujo depois de um
   passo (cada passo abaixo termina com commit limpo).

---

## Passo 1 — Diagnosticar a causa raiz do `insufficient cash` na conta paper 2

**Objetivo:** encontrar exatamente porque o rebalanceamento da conta 2 falha com
`HTTPException 400: insufficient cash` todos os dias desde 2026-09-28 (14+ dias), sem ainda
corrigir nada.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot

# 1a. Ver o histórico completo do erro (confirmar que é sempre o mesmo, sem variação)
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT account_id, status, n_orders, timestamp, details FROM paper_rebalance_logs \
   WHERE account_id = 2 AND timestamp >= '2026-09-28' ORDER BY timestamp;"

# 1b. Ver o estado atual da conta 2 (caixa disponível vs. o que o rebalance tentaria gastar)
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT account_id, timestamp, equity, cash FROM paper_snapshots WHERE account_id = 2 \
   ORDER BY timestamp DESC LIMIT 3;"

# 1c. Ler o código do caminho de rebalance da conta 2 (pesos combinados + ordem de colocação)
sed -n '200,420p' backend/app/api/routes/paper.py

# 1d. Procurar onde a validação de caixa disponível deveria estar ANTES de tentar colocar ordens
grep -n "insufficient cash\|available_cash\|place_market_order" backend/app/api/routes/paper.py
```

**O que procurar:** o audit de 2026-10-05 já aponta o código suspeito — `paper.py:264-414`
constrói pesos combinados por estratégia e chama `place_market_order` perna a perna, SEM validar
se a soma do que vai gastar cabe na caixa disponível ANTES de começar. Confirmar isto lendo o
código (passo 1c/1d) e decidir se:
- (a) os pesos da conta 2 estão desatualizados/errados (ex.: a assumir um `equity` maior do que o
  `cash` real disponível), ou
- (b) falta mesmo uma validação de pré-condição "soma(ordens propostas) <= cash disponível" antes
  de disparar qualquer `place_market_order`.

**Oracle de aceitação:** produzir, no fim deste passo, uma frase clara tipo "a causa raiz é X,
na linha Y de paper.py" — sem isto, não avançar para o passo 2. Não há commit neste passo (é só
leitura/diagnóstico).

**Rollback:** nenhum (passo read-only).

**Gotchas:**
- A conta 1 (`quarterly`) não serve de comparação direta porque só rebalanceou uma vez (28-set) —
  não há segundo evento para comparar o cálculo de pesos.
- Não confundir `equity` (caixa + valor das posições a preço de mercado) com `cash` (só o
  dinheiro livre) — o bug provavelmente vem de usar `equity` em vez de `cash` disponível num
  cálculo de quanto gastar.

---

## Passo 2 — Corrigir a validação de caixa antes de colocar ordens (conta 2)

**Objetivo:** aplicar o fix mínimo identificado no passo 1, validando ANTES de qualquer
`place_market_order` que a soma das ordens propostas não excede o `cash` disponível da conta —
e, se exceder, ajustar proporcionalmente (reduzir as ordens na mesma proporção) ou rejeitar com
um erro claro e ACIONÁVEL (não um `400` genérico que mata o rebalance inteiro sem registo útil).

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git worktree add -b fix/paper-rebalance-insufficient-cash-20261012 \
  /home/servidor/ib-paper-cash-fix-20261012 \
  main
# (worktree add corre-se DENTRO do repo principal — /home/servidor NÃO é um repositório git;
#  o path do worktree é o 2º argumento, o commit-ish 'main' é o 3º)
cd /home/servidor/ib-paper-cash-fix-20261012

# editar backend/app/api/routes/paper.py: adicionar validação de caixa disponível
# ANTES do loop que chama place_market_order (linha exata depende do achado do passo 1).
# Exemplo de guarda a inserir (ajustar nomes de variável ao código real):
#   total_notional_needed = sum(abs(order.qty * order.price) for order in proposed_orders)
#   if total_notional_needed > available_cash:
#       scale = available_cash / total_notional_needed if total_notional_needed > 0 else 0
#       proposed_orders = [scale_order(o, scale) for o in proposed_orders]
#       logger.warning(f"paper_rebalance account={account_id}: scaled orders by {scale:.3f} "
#                      f"to fit available cash {available_cash}")

# correr os testes existentes do rebalance
docker compose -f /home/servidor/Desktop/cursor-projects/ib_bot/docker-compose.yml \
  exec -T worker pytest backend/tests -k "paper_rebalance" -v
# (dentro do container worker o workdir é /app e só existe /app/backend/tests — NÃO /app/tests;
#  confirmado com `docker exec ib_bot-worker-1 sh -c "ls /app/tests"` -> No such file or directory.
#  Alternativa equivalente: usar o .venv local do repo principal, que resolve o path via
#  testpaths=backend/tests no pytest.ini)
cd /home/servidor/Desktop/cursor-projects/ib_bot && .venv/bin/pytest -k "paper_rebalance" -v
```

**Oracle de aceitação:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot && .venv/bin/pytest -k "paper_rebalance" -v
```
→ esperado: todos os testes de `paper_rebalance` passam (0 failed), incluindo um teste NOVO que
simula explicitamente o cenário "caixa insuficiente" e confirma que a ordem é escalada/rejeitada
de forma controlada (não um `tuple index out of range` nem um `400` sem contexto).

**Rollback:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git worktree remove /home/servidor/ib-paper-cash-fix-20261012 --force
```
(o worktree é descartável; `main` não é tocado até ao passo 3).

**Gotchas:**
- NÃO testar isto disparando a tarefa Celery real em produção (`docker exec ib_bot-worker-1 ...`)
  sem primeiro confirmar em testes unitários — a tarefa corre automaticamente às 15:00 WEST todos
  os dias; se o fix estiver errado, é melhor falhar num teste do que na BD de produção outra vez.
- Se o achado do passo 1 for "os pesos da conta 2 estão simplesmente errados" (não um bug de
  validação), o fix correto pode ser diferente (corrigir o cálculo de pesos em vez de adicionar
  uma guarda de caixa) — adaptar este passo ao diagnóstico real, não aplicar a guarda às cegas.

---

## Passo 3 — Integrar o fix em `main` e verificar em produção

**Objetivo:** publicar o fix no checkout principal e confirmar que o próximo disparo da tarefa
(15:00 WEST) resolve o erro sem introduzir um novo.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git fetch /home/servidor/ib-paper-cash-fix-20261012 \
  fix/paper-rebalance-insufficient-cash-20261012:fix/paper-rebalance-insufficient-cash-20261012
git merge --no-ff fix/paper-rebalance-insufficient-cash-20261012 \
  -m "fix(paper): validate available cash before placing rebalance orders (account 2, 14gg insufficient cash)"
git push origin main

# Reconstruir e reiniciar o worker (só o worker, não o gateway nem qualquer caminho real)
docker compose -f docker-compose.yml build worker beat
docker compose -f docker-compose.yml up -d worker beat

# Confirmar que arrancou sem erro
docker logs ib_bot-worker-1 --tail 50
```

**Oracle de aceitação:** no dia seguinte (ou forçando manualmente a tarefa, se o José autorizar
correr `paper_rebalance_daily_task` fora de hora para testar), confirmar:
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT account_id, status, n_orders, timestamp, details->>'error' FROM paper_rebalance_logs \
   WHERE account_id = 2 ORDER BY timestamp DESC LIMIT 1;"
```
→ esperado: `status != 'ERROR'` (idealmente `SUCCESS`, ou um erro novo e diferente — nesse caso
voltar ao passo 1 com o novo erro).

**Rollback:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git revert <hash-do-merge-commit>
git push origin main
docker compose -f docker-compose.yml build worker beat
docker compose -f docker-compose.yml up -d worker beat
```

**Gotchas:**
- O `docker compose build` reconstrói as imagens do worker/beat — vai ADICIONAR a imagens Docker
  (ver achado #3/#8 do audit), não é motivo para não fazer, só para não esquecer o passo 5 abaixo.
- `git push origin main` — confirmar que o remoto é `github.com:JoseMoura97/ib_bot.git` (mesmo
  remoto usado pelos jobs automáticos) antes de publicar.
- Não fazer isto a menos de 1h de uma corrida agendada do `ib-altdata-backup.service`/
  `ib-altdata-qa.service` (04:3x e 08:00 WEST) para evitar qualquer condição de corrida com o
  checkout principal — fazer de manhã/tarde, fora dessas janelas.

---

## Passo 4 — Remover/atualizar os ficheiros de audit desatualizados dentro do repo

**Objetivo:** corrigir o achado MÉDIO #4 (`docs/audits/ib_bot/metrics.json`/`section.json`
desatualizados desde 07-12, repetido em 3 auditorias).

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git rm docs/audits/ib_bot/metrics.json docs/audits/ib_bot/section.json
git commit -m "chore(audits): remove stale ib_bot/metrics.json+section.json (0006 reconciled since 2026-07-16; superseded by audit-session metrics.json outside the repo)"
git push origin main
```

**Oracle de aceitação:**
```bash
ls docs/audits/ib_bot/ 2>&1
```
→ esperado: `No such file or directory` (diretório removido por ficar vazio) ou diretório vazio.

**Rollback:**
```bash
git revert <hash-do-commit>
git push origin main
```

**Gotchas:** nenhum — ficheiros sem dependências de código (confirmado com
`grep -rn "docs/audits/ib_bot" --include="*.py" --include="*.sh" .` antes de remover, para garantir
que nenhum script os lê).

---

## Passo 5 — Decidir e registar a rotina de limpeza Docker

**Objetivo:** fechar o achado ALTO #3/#8 (imagens/build cache Docker a flutuar sem ação
atribuível) com uma decisão explícita, não outra promessa vaga.

**Comandos exatos (opção escolhida: automatizar com timer semanal, baixo risco):**
```bash
sudo tee /etc/systemd/system/ib-docker-prune.service > /dev/null << 'EOF'
[Unit]
Description=IB Bot weekly docker image/build-cache prune (keeps last 30 days)
[Service]
Type=oneshot
ExecStart=/usr/bin/docker image prune -af --filter "until=720h"
ExecStart=/usr/bin/docker builder prune -af --filter "until=720h"
EOF

sudo tee /etc/systemd/system/ib-docker-prune.timer > /dev/null << 'EOF'
[Unit]
Description=Weekly docker prune for ib_bot host images
[Timer]
OnCalendar=Sun 06:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ib-docker-prune.timer
```

**Oracle de aceitação:**
```bash
systemctl is-enabled ib-docker-prune.timer && systemctl is-active ib-docker-prune.timer
```
→ esperado: `enabled` e `active`. Confirmar manualmente uma corrida:
```bash
sudo systemctl start ib-docker-prune.service && journalctl -u ib-docker-prune.service -n 10
```
→ esperado: `status=0/SUCCESS`, sem erro.

**Rollback:**
```bash
sudo systemctl disable --now ib-docker-prune.timer
sudo rm /etc/systemd/system/ib-docker-prune.service /etc/systemd/system/ib-docker-prune.timer
sudo systemctl daemon-reload
```

**Gotchas:**
- `until=720h` (30 dias) evita apagar imagens que o `ib-backtests.service` semanal ainda possa
  precisar de reconstruir rapidamente a partir de cache — ajustar se o disco voltar a aproximar-se
  de 90%+.
- Este timer **não** afeta `theta-terminal`/`polytrader-bot-master`/`trading` — só limpa imagens
  globais do Docker no host; se outros projetos tiverem imagens importantes sem uso recente,
  confirmar com o dono antes do primeiro disparo (consultar `docker images` e perguntar se há
  dúvida).

---

## Passo 6 — Registar em memória os caminhos consolidados (achado BAIXO #6)

**Objetivo:** fechar o achado repetido desde 10-05 sobre nomes de memória obsoletos no brief.

**Comandos exatos:** usar a skill `/memory` (ou escrever diretamente) para adicionar, em
`MEMORY-trading.md` (dentro de `/home/servidor/.claude/projects/-home-servidor/memory/`), uma
linha explícita:
```
- Os nomes `project_ib_bot.md`/`project_ib_bot_audit.md`/`project_pead.md`/`project_earnings_vol.md`
  (usados em briefs antigos) foram consolidados em `MEMORY-trading.md` + `reference_ib_bot_*.md`.
  Não procurar por esses nomes exatos — já não existem.
```

**Oracle de aceitação:**
```bash
grep -n "project_ib_bot.md\|project_pead.md\|project_earnings_vol.md" \
  /home/servidor/.claude/projects/-home-servidor/memory/MEMORY-trading.md
```
→ esperado: a linha nova aparece.

**Rollback:** editar o ficheiro e remover a linha (é só texto, sem efeito em sistemas).

**Gotchas:** este passo não tem `git commit` associado (memória não vive no repo `ib_bot`) — não
esquecer isto não conta para o commit final deste plano.

---

## Fecho do plano

Depois dos passos 1-5 (o passo 6 é memória, fora do repo), confirmar estado limpo e publicar:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git status --porcelain   # esperado: vazio
git log --oneline -6     # confirmar os commits dos passos 2-4 estão lá
```
