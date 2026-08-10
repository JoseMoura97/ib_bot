# Plano de fixes — IB Bot — 2026-08-10

## Contexto para o executor (lê isto antes de tudo — assume zero contexto anterior)

**O que é este projeto:** um robô de trading algorítmico ligado à Interactive
Brokers (corretora), atualmente **PAUSADO** por decisão do José (CIO,
não-programador em vários domínios). Não há alpha (vantagem real) comprovado
em nenhuma das 56 estratégias que ele simula; zero ordens reais foram emitidas
alguma vez. O objetivo deste plano **não é reativar trading**, é corrigir gaps
operacionais encontrados no audit `docs/audits/2026-08-10_audit_profundo.md`
(lê esse ficheiro primeiro — tem toda a evidência ground-truth) e fechar
findings que já vinham do audit anterior (`docs/audits/2026-07-20_audit_profundo.md`)
e que ainda não foram corrigidos.

**Paths absolutos importantes:**
- Repo principal: `/home/servidor/Desktop/cursor-projects/ib_bot` (branch
  `main`, é o canónico — usa sempre este).
- Repo irmão do estudo de opções (já morto, só ler, não mexer):
  `/home/servidor/Desktop/cursor-projects/trading`.
- Worktrees secundários (não precisas mexer neles neste plano, exceto o passo
  5): `/home/servidor/Desktop/cursor-projects/ib_bot-v2` (branch
  `frontend-v2`, decomissionado), `/home/servidor/Desktop/cursor-projects/ib_bot-altdata-wt`
  (branch `alt-data-consolidation`).

**Bases de dados / credenciais (ONDE estão, nunca os valores em texto):**
- Postgres do ib_bot corre dentro do container Docker `ib_bot-db-1`.
  Utilizador `ibbot`, DB `ibbot` (confirmados em `docker-compose.yml`, não
  segredo — a password também está nesse ficheiro em texto claro porque é só
  usada dentro da rede Docker interna, nunca exposta). Comando de acesso:
  `docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "<SQL>"`.
- Conta IB real: acedida só via MCP (`get_account_summary`,
  `get_account_positions`, etc.), nunca diretamente — não há credenciais para
  copiar, o acesso já está autorizado ao agente na sessão.
- Conductor (orquestrador da frota): usa o CLI `conductor` (ex.: `conductor
  plan show ib_bot -v`), disponível em `/usr/local/bin/conductor` — não
  precisa de password extra no host.

**Regras obrigatórias (não negociáveis):**
- **Money-path gated via `request_user_approval`**: qualquer alteração que
  toque em dinheiro real (ordens, contas live, saldo) precisa de aprovação
  explícita do José antes de executar — nenhum passo deste plano toca em
  dinheiro real (tudo é paper ou leitura), mas se descobrires que precisas,
  PARA e pede aprovação.
- **Commit no mesmo turno**: quando um passo terminar com sucesso (oráculo de
  aceitação verde), faz `git add` + `git commit` desse passo *no mesmo
  turno*, não deixes trabalho por commitar entre passos.
- **`runjob` para heavy compute**: nenhum passo deste plano precisa de
  computação pesada nova. Se algum vier a precisar, usa `runjob --mem 8G --
  <cmd>`.
- **READ-ONLY em produção fora dos passos explicitamente descritos**: não
  reinicies serviços, não pares timers, não faças `docker restart` a menos
  que o passo o diga explicitamente com o comando exato.
- Todos os comandos abaixo foram **testados nesta sessão de audit**
  (2026-08-10) contra o estado real do servidor — copia-os exatamente.
  Confirma sempre o resultado antes de avançar para o passo seguinte.

---

## Passo 1 — Corrigir (ou desligar em segurança) `paper_rebalance_daily_task` — finding CRÍTICO C1

**Objetivo:** a tarefa Celery que rebalanceia as 2 contas paper falha **100%
das vezes desde 2026-05-27** (`IndexError: tuple index out of range`),
silenciosamente (o erro é apanhado e a tarefa Celery é marcada `succeeded`).
Isto é a causa raiz de "porque não há paper trades novas desde maio". Duas
saídas aceitáveis: (A) encontrar e corrigir o bug real; (B) se o bug não for
trivial de corrigir nesta sessão, desativar explicitamente a tarefa (com um
`log.warning` claro e um `FEATURE_FLAG` documentado) até haver decisão de
retomar o projeto — nunca deixar uma tarefa a falhar 100% das vezes a correr
diariamente sem que isso apareça nalgum lado visível.

**1a. Reproduzir o erro com traceback completo (a mensagem atual não tem
linha de código nenhuma — primeiro passo é sempre conseguir o traceback):**

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker exec -it ib_bot-worker-1 python3 -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from app.worker.tasks import paper_rebalance_daily_task
try:
    paper_rebalance_daily_task()
except Exception:
    import traceback; traceback.print_exc()
"
```

Se a tarefa correr sem lançar (porque o código já apanha a exceção
internamente), obtém o traceback assim em vez disso — chama diretamente a
função interna que falha (`paper_rebalance_execute` via
`paper_rebalance_preview`, ver `backend/app/worker/tasks.py:534-544` e
`backend/app/api/routes/paper.py:248` em diante):

```bash
docker exec -it ib_bot-worker-1 python3 -c "
from app.core.database import SessionLocal
from app.models.allocation import PortfolioAllocation
from app.api.schemas import PaperRebalanceRequest as PRReq
from app.api.routes.paper import paper_rebalance_execute
from uuid import UUID
import traceback

db = SessionLocal()
allocs = db.query(PortfolioAllocation).filter(PortfolioAllocation.mode=='paper').all()
for a in allocs:
    print('alloc', a.account_id, a.portfolio_id, a.amount)
    try:
        body = PRReq(portfolio_id=UUID(str(a.portfolio_id)), allocation_amount=float(a.amount), account_id=int(a.account_id))
        paper_rebalance_execute(body, db)
    except Exception:
        traceback.print_exc()
"
```

(Se `app.core.database` não for o módulo certo — o audit encontrou um
`ModuleNotFoundError` ao tentar isto de fora do container — confirma o import
correto com `docker exec ib_bot-worker-1 python3 -c "import app; print(app.__file__)"`
e `grep -rn "SessionLocal" backend/app/core/*.py`.)

**Oráculo de aceitação do 1a:** o comando produz um traceback com nome de
ficheiro + número de linha exatos onde `IndexError` é lançado (não apenas a
mensagem `tuple index out of range`).

**1b. Corrigir o bug na linha exata identificada em 1a.** Suspeita mais
provável (documentada no audit, não confirmada em código): o caminho
`RebalancingBacktestEngine._generate_rebalance_events` /
`_clean_weight_map` (`backend/app/api/routes/paper.py:276-301`), chamado
porque `QUIVER_API_KEY` está de facto configurada no ambiente do worker
(confirma com `docker exec ib_bot-worker-1 env | grep QUIVER_API_KEY` — no
momento do audit tinha um valor não-vazio, portanto o caminho "sem API key"
que usa `{"SPY": 1.0}` como fallback NÃO é o que corre). Se a causa for uma
chamada à API da Quiver a devolver vazio/erro (chave expirada, endpoint
descontinuado), a correção mínima é: (i) `try/except` à volta de cada
`bt._generate_rebalance_events(...)` **por estratégia**, dentro do loop
`for s in strategies` em `paper_rebalance_preview`, para uma estratégia
partida não derrubar as outras; (ii) logar o erro completo (`logger.exception`,
não só `str(e)`) para o próximo bug ter traceback completo de imediato.

**1c. Se não for corrigível nesta sessão (ex.: precisa de nova chave Quiver ou
decisão de produto):** desativar a tarefa explicitamente em vez de a deixar
falhar silenciosamente:

```python
# backend/app/worker/tasks.py, dentro de paper_rebalance_daily_task(), logo a seguir ao docstring:
import os
if os.getenv("PAPER_REBALANCE_ENABLED", "true").lower() == "false":
    logger.warning("paper_rebalance_daily: disabled via PAPER_REBALANCE_ENABLED=false, skipping")
    return
```

E define `PAPER_REBALANCE_ENABLED=false` no `docker-compose.yml` (serviço
`worker` e `beat`) com um comentário a apontar para este finding. Isto não
resolve o bug, mas torna o estado "desligado por decisão" em vez de "a falhar
silenciosamente todos os dias".

**Oráculo de aceitação (qualquer que seja a via 1b ou 1c):**

```bash
# Corre a tarefa manualmente e confirma o resultado esperado
docker exec ib_bot-worker-1 python3 -c "
from app.worker.tasks import paper_rebalance_daily_task
paper_rebalance_daily_task()
"
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "SELECT status, count(*) FROM paper_rebalance_logs WHERE timestamp > now() - interval '10 minutes' GROUP BY status"
```

Esperado (via 1b, bug corrigido): pelo menos 1 linha `SUCCESS` nova.
Esperado (via 1c, desligado): **zero** linhas novas (nem `SUCCESS` nem
`ERROR`) — a tarefa saiu cedo sem tentar nada — e
`docker logs ib_bot-worker-1 --since 5m | grep "disabled via PAPER_REBALANCE_ENABLED"`
mostra a linha de log.

**Rollback:**
```bash
git revert <commit deste passo>
docker compose -f /home/servidor/Desktop/cursor-projects/ib_bot/docker-compose.yml up -d --build worker beat
```

**Gotchas:**
- Não mexer na conta 1 (controlo, sempre $100k) nem apagar histórico da
  conta 2 — este passo só corrige a automação, não reescreve dados passados.
- Se corrigires o bug (via 1b) e ele passar a gerar trades novas, isso vai
  alterar `paper_cash.balance`/`paper_positions` da conta 2 pela primeira vez
  desde maio — confirma com o José antes de deixar isto correr sem
  supervisão continuada (é paper, mas muda o estado de uma conta que serve de
  referência a relatórios).
- Nunca alterar o `ERROR` das 150 linhas antigas em `paper_rebalance_logs` —
  são histórico, não apagar/reescrever.

---

## Passo 2 — Fechar o buraco de auditoria no endpoint de funding do paper trading — finding ALTO A1 (era A2 em 07-20)

**Objetivo:** `POST /paper/accounts/{account_id}/fund`
(`backend/app/api/routes/paper.py:95-102`) altera `paper_cash.balance`
diretamente sem deixar rasto. O desenho já foi especificado no plano de
07-20 e nunca foi aplicado — aplica-o agora.

**2a. Confirmar que a tabela ainda não existe (deve devolver vazio):**

```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT to_regclass('public.paper_funding_ledger');"
```

**2b. Criar a migração Alembic:**

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
find backend -iname "alembic.ini" -o -iname "versions" -type d
docker exec ib_bot-api-1 sh -c "cd /app/backend && alembic revision -m 'add paper_funding_ledger'"
```

No ficheiro de migração gerado:

```python
def upgrade():
    op.create_table(
        "paper_funding_ledger",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("paper_cash.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("actor", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

def downgrade():
    op.drop_table("paper_funding_ledger")
```

**2c. Atualizar o endpoint** (`backend/app/api/routes/paper.py:95-102`) para
exigir `reason` e `actor` no corpo do pedido (`PaperFundIn` schema) e escrever
uma linha em `paper_funding_ledger` **na mesma transação** que atualiza
`paper_cash.balance`:

```python
@router.post("/accounts/{account_id}/fund", response_model=PaperAccountOut)
def fund_paper_account(account_id: int, body: PaperFundIn, db: Session = Depends(get_db)):
    acct = ensure_paper_account(db, int(account_id))
    acct.balance = float(acct.balance) + float(body.amount)
    db.add(acct)
    db.add(PaperFundingLedger(
        account_id=int(account_id), amount=float(body.amount),
        reason=body.reason, actor=body.actor,
    ))
    db.commit()
    db.refresh(acct)
    return _account_out(acct)
```

(Adiciona `reason: str` e `actor: str` — ambos obrigatórios, sem default —
ao schema `PaperFundIn` em `backend/app/api/schemas.py`.)

**2d. Aplicar a migração:**

```bash
docker exec ib_bot-api-1 sh -c "cd /app/backend && alembic upgrade head"
```

**Oráculo de aceitação:**

```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "\d paper_funding_ledger"
# Esperado: tabela existe com id, account_id, amount, reason, actor, created_at

curl -sS -X POST http://localhost:8001/paper/accounts/1/fund \
  -H "Content-Type: application/json" -d '{"amount": 1}' -w "\n%{http_code}\n"
# Esperado: 4xx (falta reason/actor)

curl -sS -X POST http://localhost:8001/paper/accounts/1/fund \
  -H "Content-Type: application/json" \
  -d '{"amount": 0.01, "reason": "oracle-test-2026-08-10", "actor": "audit-fix-verify"}' \
  -w "\n%{http_code}\n"
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "SELECT * FROM paper_funding_ledger WHERE reason='oracle-test-2026-08-10'"
# Esperado: HTTP 200, exatamente 1 linha
```

**Depois de confirmar**, reverte o saldo de teste (`amount: -0.01`, mesma
`reason`) para não deixar lixo na conta 1.

**Rollback:**
```bash
docker exec ib_bot-api-1 sh -c "cd /app/backend && alembic downgrade -1"
```

**Gotchas:**
- Usa a conta 1 (`$100.000,00` flat, controlo) para o teste — nunca a conta
  2 (histórico real com o crédito de $70.000 por explicar).
- Não apagar/alterar retroativamente o crédito histórico de $70.000 da conta
  2 — é facto histórico documentado, este passo só previne recorrência.
- O prefixo da rota é `/paper/...`, **sem** `/api` (confirmado via
  `/openapi.json`).

---

## Passo 3 — Retenção do cache de preços em disco — finding MÉDIO M1 (era M2 em 07-20)

**Objetivo:** `.cache/yf_prices/` tem 487 MB / 2.756 ficheiros e cresce sem
limpeza há meses.

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
find .cache/yf_prices -type f | wc -l
du -sh .cache/yf_prices
```

Cria `scripts/prune_yf_cache.py` que apaga ficheiros `.pkl` com `mtime` mais
antigo que 180 dias, com `--dry-run` por default (só apaga com `--execute`).
Adiciona um `systemd timer` mensal (`prune-yf-cache.timer`/`.service`, segue
o padrão de `infra/systemd/` ou o template usado por `ib-backtests.timer`).

**Oráculo de aceitação:**
```bash
python3 scripts/prune_yf_cache.py --dry-run
# Esperado: 0 candidatos hoje (cache mais antigo tem poucos meses) — script
# só precisa de existir e funcionar corretamente, não de apagar nada agora
systemctl list-timers --all | grep prune-yf-cache
# Esperado: timer listado, próximo disparo dentro de 31 dias
```

**Rollback:** `systemctl disable --now prune-yf-cache.timer` + apagar o
script — nenhum dado fonte é destruído (só apaga cache derivado).

**Gotchas:** nunca apagar ficheiros com `mtime` recente — o backtest semanal
usa este cache para evitar re-descarregar da Yahoo Finance.

---

## Passo 4 — Teste de regressão real para as 56 estratégias — finding MÉDIO M2 (era M3 em 07-20, ainda em falta)

**Objetivo:** `backend/tests/test_backtest_regression.py` existe mas não
cobre contagem de estratégias nem "No tickers found" — cria o teste que
falta.

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
```

Adiciona um novo teste `backend/tests/test_strategy_catalog_regression.py`
que lê o `plot_data.json` mais recente (gerado pela `ib-backtests.timer`, não
disparar um backtest completo em CI) e falha se:
- `len(strategies) < 56` (número confirmado hoje, 2026-08-10 — ajusta se o
  catálogo crescer de propósito, nunca diminuir sem decisão explícita), ou
- alguma entrada tiver `dates` vazio, ou
- `/var/log/ib-backtests.log` (últimas 2000 linhas) contiver "No tickers
  found".

**Oráculo de aceitação:**
```bash
docker exec ib_bot-api-1 sh -c "cd /app/backend && python -m pytest -k strategy_catalog_regression -v"
# Esperado: 1 passed
```

**Rollback:** remover o ficheiro de teste novo — não afeta produção.

**Gotchas:** não disparar o backtest completo (61 min) em CI — ler sempre o
`plot_data.json` já gerado pelo timer semanal.

---

## Passo 5 — `git push` do main local para origin — finding MÉDIO M3

**Objetivo:** o repo local está 15 commits à frente de `origin/main` desde
07-20 (nunca publicado). Fecha o ponto único de falha.

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git status   # confirmar limpo antes
git log --oneline origin/main..HEAD | wc -l   # confirmar quantos commits por publicar
git push origin main
```

**Oráculo de aceitação:**
```bash
git status
# Esperado: "Your branch is up to date with 'origin/main'."
```

**Rollback:** não aplicável — publicar commits já testados/committed
localmente não é destrutivo; se precisares de desfazer no remoto,
`git revert` os commits específicos, nunca `push --force`.

**Gotchas:** faz isto DEPOIS dos passos 1-4 (inclui os commits desses fixes
no mesmo push).

---

## Passo 6 — Limpar worktree residual da fase `f5` (já `done` há quase um mês) — finding BAIXO B1

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git worktree list
git worktree remove .worktrees/phase-f5_altdata_arquivo-6090
```

**Oráculo de aceitação:**
```bash
git worktree list | grep -c "phase-f5_altdata_arquivo-6090"
# Esperado: 0
```

**Rollback:** não aplicável (a branch `conductor/phase-f5_altdata_arquivo-6090`
continua a existir no repo; recria o worktree com `git worktree add` se
precisares).

---

## Passo 7 — Atualizar `section.json`/`metrics.json` e registar este audit na memória — finding BAIXO B2

**Objetivo:** garantir que os artefactos de audit (`docs/audits/ib_bot/section.json`,
`docs/audits/ib_bot/metrics.json`) refletem o estado de HOJE, não a fotografia
de 07-12 (já corrigido nesta sessão de audit — este passo é só o registo na
memória do agente, para o próximo audit continuar a manter isto atualizado).

```bash
# usar a skill/mecanismo de memória do ambiente para acrescentar uma entrada
# a project_ib_bot.md com: data 2026-08-10, resumo de C1/A1/A2 (novos e
# carregados), e confirmação de que os fixes deste plano foram aplicados
# (ou o que ficou pendente)
```

**Oráculo de aceitação:**
```bash
grep -c "2026-08-10" /home/servidor/.claude/projects/-home-servidor/memory/project_ib_bot.md
# Esperado: >= 1
```

**Rollback:** editar o ficheiro de memória para remover a entrada (é
texto simples, append-only por convenção — nunca reescrever o topo).

---

## Ordem recomendada de execução

1 (CRÍTICO, primeiro) → 2 → 3 → 4 → 5 → 6 → 7. O passo 1 é o único
CRÍTICO e não depende de nenhum outro; os passos 2-4 são independentes entre
si e podem correr em paralelo se preferires; o passo 5 (`git push`) deve ser
o último antes do 6-7 para incluir tudo no mesmo push.
