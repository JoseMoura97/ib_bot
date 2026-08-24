# Plano de Fixes — IB Bot (2026-08-24)

## Contexto para o executor (lê isto antes de tudo — permite arrancar do zero, sem a conversa original)

**O que é o projeto:** um sistema de trading automático para a corretora Interactive Brokers (IB)
que testou 56 estratégias baseadas em dados públicos (compras do Congresso dos EUA, filings 13F
de fundos famosos, insiders de empresas). **Já foi confirmado repetidamente (4 auditorias
independentes desde maio de 2026) que nenhuma das 56 estratégias tem edge (vantagem) robusto** —
ver `docs/audits/2026-08-24_audit_profundo.md` secção (d), ALTO #3. O trading ao vivo está
desligado desde julho de 2026 por decisão explícita do José ("dormência seletiva"). O arquivo
diário de dados ponto-no-tempo e o backtest semanal continuam a correr sozinhos por ordem dele.

**Paths absolutos:**
- Repositório principal (worktree `main`): `/home/servidor/Desktop/cursor-projects/ib_bot`
- Worktree `frontend-v2` (decomissionado, stack :8092 morta): `/home/servidor/Desktop/cursor-projects/ib_bot-v2`

**Base de dados:** Postgres 16 dentro do container Docker `ib_bot-db-1`. Acede-se com:
`docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "<query>"`. **NUNCA correr `UPDATE`/`DELETE`
manual nas tabelas `altdata_snapshots`/`altdata_snapshot_corrections`** — têm um gatilho
`altdata_snapshots_reject_mutation` que as torna append-only por desenho (prova de
não-manipulação); qualquer escrita fora do coletor automático invalida essa prova.

**Credenciais:** ficam em `.env` dentro de cada worktree (NUNCA imprimir os valores nos
relatórios — só confirmar "existe"/"está presente"). Credenciais da IB (Gateway) ficam fora do
repositório, geridas pelo `ibeam`/IBC (atualmente desligado). A ligação MCP à IB usa OAuth da
conta do José, gerida fora deste repositório — não precisas dela para nenhum passo abaixo.

**Regras obrigatórias para quem executar este plano:**
- **Qualquer passo que envolva dinheiro real, ordens reais, ou reativar `LIVE_AUTO_REBALANCE`,
  `ibgateway.service` ou `xvfb-ibgw.service` exige aprovação explícita do José antes de
  executar** (usar `request_user_approval` se disponível, ou parar e perguntar). Nenhum passo
  deste plano faz isso — são todos read-only/limpeza/decisão.
- Fazer commit no MESMO turno em que se termina cada passo (nunca deixar trabalho por commitar) —
  isto é regra global do José: trabalho terminado e não commitado é a forma nº1 de o perder.
- Compute pesado (rebuilds Docker completos, backtests completos) deve correr via `runjob` se a
  infraestrutura do host o exigir; os passos abaixo são todos leves (segundos a minutos).
- Antes de marcar qualquer passo como feito, correr o oráculo de aceitação e colar o output —
  nunca assumir sucesso porque "o comando não deu erro na consola".
- **Este é o SEGUNDO plano de fixes seguido (o primeiro, `docs/plans/undefined_plano_fixes.md`
  de 2026-08-17, não foi executado — ver auditoria 2026-08-24, Finding ALTO #1). Se estás a ler
  isto numa auditoria futura e este plano também não foi executado, é o sinal mais forte possível
  de que ninguém está a agir sobre estas auditorias — reportar isso ao José em vez de escrever um
  6º plano idêntico.**

---

## Passo 1 — Levar ao José a decisão de continuidade do arquivo PIT (repetido do plano anterior, ainda não respondido)

**Objetivo:** o arquivo de dados ponto-no-tempo (`altdata_snapshots`) cresce sozinho todos os
dias (471 linhas, 43 dias, 11 fontes, a 2026-08-24) para um produto (as 56 estratégias) já
comprovadamente sem edge. A decisão de negócio sobre o que fazer com ele nunca foi tomada — está
formalmente "em HOLD" desde a triagem de julho e ninguém voltou a perguntar ao José desde 08-17.

**Comandos exatos (para reunir a evidência a apresentar):**
```bash
psql conductor -c "SELECT id,status,title FROM project_plans WHERE slug='ib_bot' ORDER BY id"
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT count(*), min(as_of_date), max(as_of_date) FROM altdata_snapshots"
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT count(*) FROM paper_snapshots WHERE account_id=2"
cat /home/servidor/Desktop/cursor-projects/ib_bot/docs/altdata_b2b_one_pager_draft.md
```

**Apresentar ao José (pergunta estruturada, não um comando), com as 3 opções dos planos futuros
deste audit:**
1. Continuar a acumular o arquivo PIT sem uso ativo (custo: compute contínuo + disco a crescer;
   benefício: opção futura de licenciar/vender os dados — ver
   `docs/plans/2026-08-24_futuro_licenciamento_dados.md`).
2. Redirecionar o esforço de engenharia para validar as ~30 estratégias 13F "dormentes" nunca
   testadas com o motor deflacionado — ver `docs/plans/2026-08-24_futuro_busca_edge_dormente.md`.
3. Desligar os timers de arquivo/backup/QA/backtest e arquivar o projeto por completo — ver
   `docs/plans/2026-08-24_futuro_encerramento_ordenado.md`.

**Oráculo de aceitação:** decisão explícita do José registada em memória (skill `/memory`) e, se
aplicável, em `project_plans.metadata` do plano `e36e04ec` no Conductor.

**Rollback:** não aplicável (é uma decisão, não uma mudança de sistema).

**Gotchas:** não interpretar o silêncio do José como "opção 1 confirmada". A auditoria de 08-17
já fez esta mesma pergunta e não obteve resposta registada — não assumir que "já foi respondido
noutro lado" sem confirmar com `grep -rl "ib_bot" ~/.claude/projects/-home-servidor/memory/` e ler
os ficheiros tocados desde 2026-08-17.

---

## Passo 2 — Consolidar os dois frontends vivos (systemd :3001 vs Docker :8090)

**Objetivo:** eliminar a confusão de "qual frontend é o real" (Finding ALTO #2 da auditoria
2026-08-24). Manter só o systemd `ib-bot-v2-frontend.service` (porta 3001), que fala com a API v1
real (:8001) e não implica correr uma stack Docker inteira (api/worker/beat/db/redis) só para
servir uma segunda cópia. Desligar o par Docker `nginx-1`/`web-1` (porta 8090).

**Comandos exatos:**
```bash
# 1. Confirmar qual serve dados reais AGORA (não assumir)
curl -s -o /dev/null -w "3001: %{http_code}\n" http://localhost:3001
curl -s -o /dev/null -w "8090: %{http_code}\n" http://localhost:8090

# 2. Confirmar com o José qual manter (o audit recomenda manter :3001)

# 3. Só depois de confirmação, parar o par docker 8090 (NÃO apagar containers, só parar):
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker compose -f docker-compose.prod.yml stop web nginx
```

**Oráculo de aceitação:**
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8090   # erro de ligação / connection refused
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001   # 2xx/3xx, continua vivo
docker ps --filter "name=ib_bot-web-1" --filter "name=ib_bot-nginx-1"   # não lista nenhum como Up
```

**Rollback:** `docker compose -f docker-compose.prod.yml start web nginx` — reativa em segundos,
sem perda de dados (nginx/web não guardam estado próprio).

**Gotchas:**
- Confirmar PRIMEIRO com `curl` qual dos dois está realmente a ser usado por algum bookmark do
  José antes de parar.
- Este passo é reversível e de baixo risco (não é money-path), mas mesmo assim documentar
  claramente ao José o que se fez — é o tipo de "routine next step" que já está autorizado sem
  pedir confirmação extra, mas o José precisa de saber que aconteceu.

---

## Passo 3 — Limpar imagens Docker e build cache não usados

**Objetivo:** recuperar disco (32,36 GB de imagens 100% reclamáveis, medido nesta sessão via
`docker system df`) sem tocar em containers vivos.

**Comandos exatos:**
```bash
docker system df
docker image prune -a --filter "until=168h" --force   # remove imagens não usadas há mais de 7 dias
docker builder prune --force
docker system df   # confirmar redução
```

**Oráculo de aceitação:** o segundo `docker system df` mostra `RECLAIMABLE` para `Images`
visivelmente menor que os 32,36 GB iniciais; `docker ps` continua a mostrar os mesmos containers
`ib_bot-*` `Up` sem interrupção (`ib_bot-api-1`, `ib_bot-beat-1`, `ib_bot-worker-1`,
`ib_bot-db-1`, `ib_bot-redis-1`, e `ib_bot-web-1`/`ib_bot-nginx-1` se o Passo 2 não tiver corrido
ainda).

**Rollback:** nenhum necessário — imagens removidas podem ser reconstruídas com
`docker compose build` se algum passo futuro do Conductor precisar delas de novo (mais lento na
próxima corrida, sem perda de dados).

**Gotchas:** NÃO usar `docker system prune -a` sem filtro de tempo — pode apagar imagens de que
fases `in_progress` do Conductor (worktrees em `.worktrees/phase-*`) dependam ativamente. Usar
sempre o filtro `--filter "until=168h"`. Verificar antes com `psql conductor -c "SELECT id,status
FROM project_plans WHERE slug='ib_bot' AND status IN ('approved','executing')"` — se devolver
alguma linha, parar e confirmar com o José antes de limpar.

---

## Passo 4 — Arrumar resíduos no root do repositório (repetido do plano anterior, ainda não feito)

**Objetivo:** remover ficheiros órfãos que poluem a raiz (Finding BAIXO #8 da auditoria
2026-08-24), confirmados ainda presentes nesta sessão.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
grep -rn "alembic_validation" backend/ 2>/dev/null   # deve devolver vazio antes de apagar
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
antes de apagar (o `grep` acima deve devolver vazio ou só referências em ficheiros já
arquivados).

---

## Passo 5 — Documentar/decidir o propósito da conta paper 1 (parada em $100.000)

**Objetivo:** a conta paper `account_id=1` está sempre em `cash=equity=100000` há 91 snapshots —
provavelmente uma conta de controlo/baseline nunca documentada (Finding BAIXO #9).

**Comandos exatos:**
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT * FROM paper_cash WHERE id=1"
grep -rn "account_id.*=.*1\b" /home/servidor/Desktop/cursor-projects/ib_bot/backend --include="*.py" | grep -iv "account_id.*2" | head -20
```

**Oráculo de aceitação:** uma frase documentada (em `docs/RUNBOOK.md` ou memória) explicando o
propósito da conta 1 — "conta de controlo, nunca rebalanceada, serve para X" — ou confirmação de
que é lixo residual seguro de ignorar.

**Rollback:** não aplicável, é só documentação.

**Gotchas:** não apagar a conta nem os seus snapshots sem confirmar primeiro que nenhum código
ativo a lê para comparação (ex.: dashboards que mostram "conta 1 vs conta 2" lado a lado).
