# Plano de Fixes — IB Bot

## Contexto para o executor (lê isto antes de tudo — permite arrancar do zero, sem esta conversa)

**O que é o projeto:** um sistema de trading automático para Interactive Brokers (IB) que testa
56 estratégias baseadas em dados públicos (compras do Congresso dos EUA, filings 13F de fundos,
insiders, etc.). **Já foi decidido e confirmado várias vezes que nenhuma das 56 estratégias tem
edge (vantagem) robusto** — ver `docs/audits/undefined_audit_profundo.md` secção (d), ALTO #1.
O projeto está em **"dormência seletiva"**: trading ao vivo desligado, mas o arquivo diário de
dados e o backtest semanal continuam a correr sozinhos por ordem explícita do José.

**Paths absolutos:**
- Repositório principal (worktree `main`): `/home/servidor/Desktop/cursor-projects/ib_bot`
- Worktree `frontend-v2` (descomissionada): `/home/servidor/Desktop/cursor-projects/ib_bot-v2`
- Worktree `alt-data-consolidation`: `/home/servidor/Desktop/cursor-projects/ib_bot-altdata-wt`
- Worktrees de fases do Conductor: `/home/servidor/Desktop/cursor-projects/ib_bot/.worktrees/*`

**Base de dados:** Postgres 16 dentro do container Docker `ib_bot-db-1`. Acede-se com:
`docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "<query>"`. **NUNCA correr `UPDATE`/`DELETE`
manual nas tabelas `altdata_snapshots`/`altdata_snapshot_corrections`** — são append-only por
desenho (gate H4 do plano ativo do Conductor); qualquer escrita fora do coletor automático
invalida a prova de imutabilidade.

**Credenciais:** ficam em `.env` dentro de cada worktree (NUNCA imprimir os valores nos
relatórios — só confirmar "existe"/"está presente"). Credenciais da IB (Gateway) ficam fora do
repositório, geridas pelo `ibeam`/IBC (atualmente desligado). A ligação MCP à IB usa OAuth da
conta do José, gerida fora deste repositório.

**Regras obrigatórias para quem executar este plano:**
- **Qualquer passo que envolva dinheiro real, ordens reais, ou reativar `LIVE_AUTO_REBALANCE`,
  `ibgateway.service` ou `xvfb-ibgw.service` exige aprovação explícita do José antes de
  executar** (usar `request_user_approval` se disponível, ou parar e perguntar). Nenhum passo
  deste plano faz isso — são todos read-only/limpeza/decisão.
- Fazer commit no MESMO turno em que se termina cada passo (nunca deixar trabalho por commitar).
- Compute pesado (rebuilds Docker completos, backtests completos) deve correr via `runjob` se
  a infraestrutura do host o exigir; os passos abaixo são todos leves (segundos a poucos
  minutos), não precisam de `runjob`.
- **Nunca escrever por cima de um payload de release existente** — não aplicável aqui (não há
  sistema de release-deploy neste projeto), mas nunca editar `docker-compose.prod.yml.bak.*`
  como se fosse o ficheiro vivo.
- Antes de marcar qualquer passo como feito, correr o oráculo de aceitação e colar o output —
  nunca assumir sucesso porque "o comando não deu erro na consola".

---

## Passo 1 — Confirmar o fecho do gate H3 (operação sem agente) do plano ativo do Conductor

**Objetivo:** verificar (não forçar) que os 3 disparos autónomos consecutivos do timer de QA
diário (14, 15, 16 de agosto) mais o disparo de hoje continuam válidos, e que o script
verificador reconhece o gate como fechado.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git pull origin main
bash infra/scripts/verify_h3_soak.sh
```

**Oráculo de aceitação:** o comando termina com `exit 0` e a última linha NÃO contém
`H3_SOAK_RED`. Se ainda disser `H3_SOAK_RED NO_RUNTIME_RECEIPT <data-de-hoje>`, o timer de hoje
ainda não disparou (dispara às 08:00 WEST) — não é uma falha, é esperar. Repetir depois das
08:05 WEST do dia seguinte à execução deste passo.

**Rollback:** nenhum — este passo é só leitura, não escreve nada.

**Gotchas:**
- NÃO corra `ib-altdata-qa.service` manualmente para "acelerar" — a memória
  `reference_ib_bot_h3_timer_soak_gate_20260814.md` é explícita: um disparo manual (mesmo que
  tenha sucesso) NÃO conta para o soak e pode corromper a prova de "sem agente".
- Se o gate ficar preso (`in_progress` há mais de 5 dias sem progresso), reportar ao José em vez
  de tentar "consertar" o script verificador — editar o oráculo para passar invalida a prova.

---

## Passo 2 — Levar ao José a decisão de continuidade do plano de hardening de dados

**Objetivo:** o plano `04bf8af8` (Conductor) está a construir um arquivo de dados perfeito
(imutável, replicado, sem agente) para um produto (56 estratégias) já comprovadamente sem edge
robusto. Isto não é um bug de código — é uma decisão de negócio em falta. Este passo não
executa código; produz a pergunta certa para o José decidir.

**Comandos exatos (para reunir a evidência a apresentar):**
```bash
psql conductor -c "SELECT id,status,title FROM project_plans WHERE slug='ib_bot' ORDER BY id"
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT count(*), min(as_of_date), max(as_of_date) FROM altdata_snapshots"
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT count(*) FROM paper_snapshots WHERE account_id=2"
```

**Apresentar ao José (não é um comando, é uma pergunta estruturada), com as 3 opções dos
planos futuros deste audit:**
1. Continuar a acumular o arquivo PIT sem uso ativo (custo: engenharia + compute contínuos,
   benefício: opção futura de licenciar/vender os dados — ver
   `docs/plans/undefined_futuro_licenciamento_dados.md`).
2. Redirecionar o esforço de engenharia para validar as ~30 estratégias 13F "dormentes" nunca
   testadas com o motor deflacionado — ver `docs/plans/undefined_futuro_busca_edge_dormente.md`.
3. Desligar os timers de arquivo/backup/QA e arquivar o projeto por completo (parar o
   compounding do dataset) — só se o José decidir que nenhuma das opções acima vale a pena.

**Oráculo de aceitação:** decisão explícita do José registada em memória (`/memory` skill) e,
se aplicável, no `project_plans.metadata` do plano `04bf8af8` ou `e36e04ec`.

**Rollback:** não aplicável (é uma decisão, não uma mudança de sistema).

**Gotchas:** não interpretar o silêncio do José como "opção 1 confirmada" — isto é
especificamente o tipo de decisão ambígua/de grande impacto que justifica uma pergunta direta
em vez de assumir.

---

## Passo 3 — Consolidar os dois frontends vivos (systemd :3001 vs Docker :8090)

**Objetivo:** eliminar a confusão de "qual frontend é o real" documentada no finding ALTO #3.
Manter só o systemd `ib-bot-v2-frontend.service` (porta 3001), que fala com a API v1 real
(:8001), e desligar o par Docker `nginx-1`/`web-1` (porta 8090) que aponta para uma stack não
usada diariamente.

**Comandos exatos:**
```bash
# 1. Confirmar qual serve dados reais AGORA (não assumir)
curl -s -o /dev/null -w "3001: %{http_code}\n" http://localhost:3001
curl -s -o /dev/null -w "8090: %{http_code}\n" http://localhost:8090

# 2. Confirmar com o José qual manter (o audit recomenda manter :3001, que fala com a API viva)

# 3. Só depois de confirmação, parar o par docker 8090 (NÃO apagar containers, só parar):
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker compose -f docker-compose.prod.yml stop web nginx
```

**Oráculo de aceitação:** `curl -s -o /dev/null -w "%{http_code}" http://localhost:8090` devolve
erro de ligação (porta fechada); `curl -s -o /dev/null -w "%{http_code}" http://localhost:3001`
continua a devolver `2xx`/`3xx` (vivo). `docker ps` já não lista `ib_bot-web-1`/`ib_bot-nginx-1`
como `Up`.

**Rollback:** `docker compose -f docker-compose.prod.yml start web nginx` — reativa em segundos,
não há perda de dados (nginx/web não guardam estado).

**Gotchas:**
- Confirmar PRIMEIRO com `curl` qual dos dois está realmente a ser usado por algum bookmark do
  José antes de parar — não assumir que 8090 está morto só porque a memória diz que "v2" foi
  desligado; a memória fala da stack de BACKEND v2 (:8092), não desta combinação nginx/web
  específica.
- Este passo é reversível e de baixo risco (não money-path), mas ainda assim aviso o José antes
  de parar um serviço já a correr, por disciplina — é o tipo de "routine next step" que o CLAUDE.md
  já autoriza a fazer sem pedir confirmação extra, mas documentar o que se fez.

---

## Passo 4 — Limpar imagens Docker e build cache não usados

**Objetivo:** recuperar disco (36,3 GB de imagens + 5,7 GB de build cache reclamáveis,
medido nesta sessão) sem tocar em containers vivos.

**Comandos exatos:**
```bash
docker system df
docker image prune -a --filter "until=168h" --force   # remove imagens não usadas há mais de 7 dias
docker builder prune --force
docker system df   # confirmar redução
```

**Oráculo de aceitação:** o segundo `docker system df` mostra `RECLAIMABLE` para `Images` e
`Build Cache` visivelmente menor que a leitura inicial; `docker ps` continua a mostrar os
mesmos 7 containers `ib_bot-*` `Up` sem interrupção.

**Rollback:** nenhum necessário — imagens removidas podem ser reconstruídas com
`docker compose build` se algum passo do Conductor precisar delas de novo (mais lento na
próxima corrida, mas sem perda de dados).

**Gotchas:** NÃO usar `docker system prune -a` sem filtro de tempo — isso apagaria imagens de
que fases `in_progress` do Conductor (ex.: worktrees `.worktrees/phase-h3_unattended_operation-b331`)
possam depender ativamente. Usar sempre o filtro `--filter "until=168h"`.

---

## Passo 5 — Arrumar resíduos no root do repositório

**Objetivo:** remover ficheiros órfãos que poluem a raiz (finding BAIXO #9), sem tocar em
código funcional.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git rm --cached '$LOG' 2>/dev/null; rm -f '$LOG'
rm -f alembic_validation.db
mkdir -p archive/legacy_backtest_results
git mv backtest_results_2026_05_12.json backtest_results_corrected.json backtest_results_final.json archive/legacy_backtest_results/ 2>/dev/null || true
rm -f docker-compose.prod.yml.bak.1778273314
git add -A
git commit -m "chore: arrumar resíduos no root (logs antigos, resultados de backtest legados, bak file)"
```

**Oráculo de aceitação:** `git status --porcelain` devolve vazio depois do commit; `ls` na raiz
já não mostra `$LOG`, `alembic_validation.db`, nem `docker-compose.prod.yml.bak.*`.

**Rollback:** `git revert <hash-do-commit>` restaura tudo.

**Gotchas:** confirmar que `alembic_validation.db` não é referenciado por nenhum teste ativo
antes de apagar — `grep -rn "alembic_validation" backend/` deve devolver vazio ou só
referências em ficheiros já arquivados.
