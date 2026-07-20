# Plano de fixes — IB Bot — 2026-07-20

## Contexto para o executor (lê isto antes de tudo — assume zero contexto anterior)

**O que é este projeto:** um robô de trading algorítmico ligado à
Interactive Brokers (corretora), atualmente **PAUSADO** por decisão do
José (CIO, não-programador). Não há alpha (vantagem real) comprovado em
nenhuma das 56 estratégias que ele simula; zero ordens reais foram
emitidas alguma vez. O objetivo deste plano **não é reativar trading**, é
corrigir gaps operacionais encontrados no audit `docs/audits/2026-07-20_audit_profundo.md`
(lê esse ficheiro primeiro — tem toda a evidência ground-truth).

**Paths absolutos importantes:**
- Repo principal: `/home/servidor/Desktop/cursor-projects/ib_bot` (branch `main`, é o canónico — usa sempre este).
- Repo irmão do estudo de opções: `/home/servidor/Desktop/cursor-projects/trading` (estudo `0006-earnings-vol`, já morto/arquivado — não mexer, só ler).
- Worktrees secundários (não precisas mexer neles neste plano):
  `/home/servidor/Desktop/cursor-projects/ib_bot-v2` (branch `frontend-v2`, decomissionado),
  `/home/servidor/Desktop/cursor-projects/ib_bot-altdata-wt` (branch `alt-data-consolidation`).

**Bases de dados / credenciais (ONDE estão, nunca os valores em texto):**
- Postgres do ib_bot corre dentro do container Docker `ib_bot-db-1`.
  Utilizador/DB/password estão em `docker exec ib_bot-db-1 env | grep POSTGRES`
  (não imprimir a password em logs partilhados — usa sempre `docker exec` para
  correr SQL, nunca copies a password para um ficheiro).
  Comando de acesso: `docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "<SQL>"`.
- Conta IB real: acedida só via MCP (`get_account_summary` etc.), nunca
  diretamente — não há credenciais para copiar, o acesso já está autorizado
  ao agente.
- Conductor (orquestrador da frota): `psql conductor -c "<SQL>"` (leitura
  local, sem password extra necessária no host).

**Regras obrigatórias (não negociáveis):**
- **Money-path gated via `request_user_approval`**: qualquer alteração que
  toque em dinheiro real (ordens, contas live, saldo) precisa de aprovação
  explícita do José antes de executar — nenhum passo deste plano toca em
  dinheiro real, mas se descobrires que precisas, PARA e pede aprovação.
- **Commit no mesmo turno**: quando um passo terminar com sucesso (oráculo
  de aceitação verde), faz `git add` + `git commit` desse passo *no mesmo
  turno*, não deixes trabalho por commitar entre passos.
- **`runjob` para heavy compute**: nenhum passo deste plano precisa de
  computação pesada nova (o backtest semanal já corre contido via
  `systemd` com `MemoryMax=24G` — não precisas de recriar isso). Se algum
  passo vier a precisar, usa `runjob --mem 24G -- <cmd>`.
- **READ-ONLY em produção fora dos passos explicitamente descritos**: não
  reinicies serviços, não pares timers, não faças `docker restart` a menos
  que o passo o diga explicitamente com o comando exato.
- Todos os comandos abaixo foram **testados nesta sessão de audit** (2026-07-20)
  contra o estado real do servidor — copia-os exatamente.

---

## Passo 1 — Confirmar que o disparo NORMAL do backtest semanal (domingo 2026-07-26 04:15 UTC) sucede sem intervenção manual

**Objetivo:** fechar o finding ALTO A1 — a única corrida bem-sucedida até
agora (2026-07-19) foi uma remediação manual como root, depois de 5
falhas seguidas por falta de memória. O fix de código já está em `main`
(commits `8835568`, `b4358ae`, `6439026`), mas nunca foi provado num
disparo automático e não-assistido do `ib-backtests.timer`.

Este passo **não muda código** — é uma verificação agendada. Como o
disparo só acontece no futuro (2026-07-26), regista um job do Conductor
que acorda nessa data e verifica.

**Comandos exatos:**

```bash
# 1a. Confirmar que o timer ainda está agendado corretamente (deve mostrar
#     próximo disparo perto de 2026-07-26 04:15 UTC / 05:15 ou 05:16 WEST)
systemctl list-timers ib-backtests.timer --all

# 1b. Registar um job de verificação futura (ajusta a data/hora exatas
#     devolvidas por 1a; exemplo de invocação — o teu ambiente pode ter um
#     wrapper diferente para 'register_job', usa o disponível na tua sessão)
# Objetivo do job: no dia seguinte ao disparo (>= 2026-07-26 06:00 UTC),
# correr o comando do oráculo de aceitação abaixo e reportar o resultado
# ao DM ib_bot no Conductor.
```

**Oráculo de aceitação (correr depois de 2026-07-26 05:30 UTC / ~06:30 WEST):**

```bash
systemctl show ib-backtests.service --property=Result,ExecMainStatus,MemoryPeak,InactiveEnterTimestamp
```

Esperado: `Result=success`, `ExecMainStatus=0`, `MemoryPeak` bem abaixo de
`25769803776` (24 GiB), `InactiveEnterTimestamp` posterior a
`2026-07-26 04:15:00 UTC`. Confirmar também:

```bash
docker exec ib_bot-db-1 true 2>&1  # sanity: container ainda vivo
grep -c '"' /home/servidor/Desktop/cursor-projects/ib_bot/.cache/plot_data.json  # sanity: ficheiro não vazio
python3 -c "import json; d=json.load(open('/home/servidor/Desktop/cursor-projects/ib_bot/.cache/plot_data.json')); print(len(d['strategies']))"
```

Esperado: `54` (ou mais, se estratégias novas forem adicionadas
entretanto) — **nunca menos**, e sem "No tickers found" em
`/var/log/ib-backtests.log` desse dia:

```bash
journalctl -u ib-backtests.service --since "2026-07-26 04:00" --until "2026-07-26 12:00" | grep -iE 'error|fail'
grep -c "No tickers found" /var/log/ib-backtests.log
```

Esperado: sem `Failed`/`error` no journal; contagem de "No tickers found" = `0`.

**Se falhar:** não tentes corrigir sozinho no momento — regista a falha
como finding no próximo audit semanal e acorda o DM ib_bot no Conductor
(o `OnFailure=ib-backtests-alert.service` já dispara automaticamente; só
confirma que o alerta chegou: `journalctl -u ib-backtests-alert.service --since "2026-07-26"`).

**Rollback:** nenhum — este passo é só verificação, não muda nada no
sistema.

**Gotchas:**
- O ficheiro `.cache/plot_data.json` também é tocado pelo coletor diário
  de alt-data (`~05:00 UTC` todos os dias) — o `mtime` sozinho não prova
  que o backtest correu; usa sempre o `systemctl show` como fonte de
  verdade, não o `mtime` do ficheiro.
- Não confundir `ib-backtests.timer` (semanal, ib_bot) com
  `historical-backfill.timer` (diário, é do Polymarket — projeto
  diferente, não mexer).

---

## Passo 2 — Fechar o buraco de auditoria no endpoint de funding do paper trading

**Objetivo:** corrigir o finding ALTO A2 — `POST /api/paper/accounts/{account_id}/fund`
altera `paper_cash.balance` diretamente sem deixar rasto. Não é dinheiro
real, mas é um padrão de código perigoso a corrigir antes que seja
copiado para algum caminho real.

**2a. Localizar o endpoint:**

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
grep -rn "def fund" backend/ | grep -v test
grep -rn "/fund" backend/ --include="*.py" | grep -v test
```

**2b. Criar a tabela de auditoria (migração Alembic — o projeto já usa
Alembic para migrações; confirma a pasta exata antes de criar):**

```bash
find backend -iname "alembic.ini" -o -iname "versions" -type d
```

Cria uma nova revisão Alembic (usa o comando que o `alembic.ini`
encontrado indicar, tipicamente dentro do container ou virtualenv do
backend):

```bash
docker exec ib_bot-api-1 sh -c "cd /app/backend && alembic revision -m 'add paper_funding_ledger'"
```

No ficheiro de migração gerado, criar a tabela:

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

**2c. Atualizar o endpoint** para exigir `reason` e `actor` no corpo do
pedido e escrever uma linha em `paper_funding_ledger` na MESMA transação
que atualiza `paper_cash.balance` (não em transações separadas — se uma
falhar, a outra tem de falhar também).

**2d. Aplicar a migração:**

```bash
docker exec ib_bot-api-1 sh -c "cd /app/backend && alembic upgrade head"
```

**Oráculo de aceitação:**

```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "\d paper_funding_ledger"
```

Esperado: tabela existe com as colunas `id, account_id, amount, reason, actor, created_at`.

```bash
# Testar que um POST sem 'reason' é rejeitado (não deve mudar saldo nenhum)
curl -sS -X POST http://localhost:8001/api/paper/accounts/1/fund \
  -H "Content-Type: application/json" -d '{"amount": 1}' -w "\n%{http_code}\n"
```

Esperado: código HTTP `4xx` (pedido inválido, falta `reason`/`actor`).

```bash
# Testar que um POST válido cria a linha de ledger E atualiza o saldo
curl -sS -X POST http://localhost:8001/api/paper/accounts/1/fund \
  -H "Content-Type: application/json" \
  -d '{"amount": 0.01, "reason": "oracle-test-2026-07-20", "actor": "audit-fix-verify"}' \
  -w "\n%{http_code}\n"
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "SELECT * FROM paper_funding_ledger WHERE reason='oracle-test-2026-07-20'"
```

Esperado: HTTP `200`, e exatamente 1 linha na tabela com `amount=0.01`.
**Depois de confirmar**, reverte o saldo de teste (`amount: -0.01`, mesma
`reason`) para não deixar lixo na conta 1 (que é a conta de controlo
sempre em $100.000,00 flat — não a mexer no valor real).

**Rollback:**

```bash
docker exec ib_bot-api-1 sh -c "cd /app/backend && alembic downgrade -1"
```

**Gotchas:**
- A conta 1 (`paper_cash.id=1`) está **sempre em $100.000,00 flat** — é a
  conta de controlo/vazia. Usa-a para o teste do oráculo (não a conta 2,
  que tem o histórico real com o crédito de $70.000 por explicar — não
  mexer nessa).
- Não apagar nem alterar retroativamente o crédito histórico de $70.000
  da conta 2 — esse é um facto histórico já documentado em
  `docs/audits/2026-07-12_paper_ledger_reconciliacao.md`; o objetivo deste
  passo é só prevenir recorrência, não reescrever o passado.

---

## Passo 3 — Adicionar retenção ao cache de preços em disco

**Objetivo:** fechar o finding MÉDIO M2 — `.cache/yf_prices/` (473 MB,
2.752 ficheiros hoje) cresce sem limite há meses.

**Comandos exatos:**

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# Verificar o estado atual antes de mudar nada
find .cache/yf_prices -type f | wc -l
du -sh .cache/yf_prices
```

Adicionar um script `scripts/prune_yf_cache.py` que apaga ficheiros
`.pkl` com `mtime` mais antigo que 180 dias, e um `cron`/`systemd timer`
mensal a correr esse script (segue o padrão dos outros timers do
projeto — ver `infra/systemd/` ou equivalente no repo para o template
exato de unit file usado).

**Oráculo de aceitação:**

```bash
python3 scripts/prune_yf_cache.py --dry-run
```

Esperado: lista ficheiros candidatos a apagar (mais de 180 dias) sem
apagar nada (hoje deve devolver 0 candidatos, porque o cache mais antigo
tem poucos meses — isso é esperado e correto, o script só precisa de
existir e funcionar quando chegar a hora).

```bash
systemctl list-timers | grep prune_yf_cache
```

Esperado: novo timer listado, próximo disparo dentro de 31 dias.

**Rollback:** `systemctl disable --now prune-yf-cache.timer` + apagar o
ficheiro do script; nenhum dado é destruído por reverter isto (o script só
apaga cache, nunca dados fonte).

**Gotchas:** nunca apagar ficheiros com `mtime` recente — o backtest usa
este cache para evitar re-descarregar da Yahoo Finance; apagar cache
"quente" por engano faz o próximo backtest ser mais lento/pesado (mas não
incorreto).

---

## Passo 4 — Teste de regressão para as 56 estratégias

**Objetivo:** fechar o finding MÉDIO M3 — nenhum teste automático falha
se uma estratégia voltar a quebrar silenciosamente (como "SMB Factor
Regime" já fez no passado).

**Comandos exatos:**

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
find . -iname "test_backtest*" -o -iname "*test*strateg*" | grep -v node_modules | grep -v .venv
```

Adicionar/estender um teste (pytest) que corre o gerador de `plot_data.json`
num universo pequeno/rápido (ou lê o `plot_data.json` mais recente gerado
pela `ib-backtests.timer`) e falha se:
- `len(strategies) < 54` (o número de hoje — ajusta se o catálogo crescer
  de propósito), ou
- alguma entrada tiver `dates` vazio, ou
- o log mais recente contiver "No tickers found".

**Oráculo de aceitação:**

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker exec ib_bot-api-1 sh -c "cd /app/backend && python -m pytest -k strategy_regression -v"
```

Esperado: teste passa (`1 passed`) contra o `plot_data.json` atual.

**Rollback:** remover o ficheiro de teste novo — não afeta produção
(testes não correm em produção).

**Gotchas:** este teste deve correr contra o `plot_data.json` **já
gerado** (não deve disparar um backtest completo de 61 minutos em CI —
isso violaria a disciplina de `runjob`/heavy-compute se corresse sem
contenção).

---

## Passo 5 — Limpar worktree residual da fase `f5` (já `done`)

**Objetivo:** fechar o finding BAIXO B1.

**Comandos exatos:**

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git worktree list
git worktree remove .worktrees/phase-f5_altdata_arquivo-6090
```

**Oráculo de aceitação:**

```bash
git worktree list | grep -c "phase-f5_altdata_arquivo-6090"
```

Esperado: `0`.

**Rollback:** não aplicável (a branch `conductor/phase-f5_altdata_arquivo-6090`
continua a existir no repo, só o worktree em disco é removido; podes
recriar com `git worktree add` se precisares).

**Gotchas:** confirmar primeiro que a fase `f5` está mesmo `done` no
Conductor antes de remover (`psql conductor -c "SELECT jsonb_path_query(phases, '$[*] ? (@.id==\"f5_altdata_arquivo\")')  FROM project_plans WHERE slug='ib_bot' AND status='executing'"` — ou o equivalente `jsonb_agg` usado no audit).

---

## Passo 6 — Registar este audit e os fixes na memória do projeto

**Objetivo:** garantir que o próximo agente (humano ou IA) que abrir este
projeto vê o estado atualizado, não uma foto desatualizada.

**Comandos exatos:** usar a skill/mecanismo de memória do teu ambiente
(tipicamente `/memory` ou equivalente) para acrescentar uma entrada a
`project_ib_bot.md` com: data 2026-07-20, resumo de que A1/A2/M1/M2/M3
foram corrigidos (ou o que ficou pendente), e o novo estado dos 8/8
serviços verificados nesta sessão.

**Oráculo de aceitação:**

```bash
grep -c "2026-07-20" /home/servidor/.claude/projects/-home-servidor/memory/project_ib_bot.md
```

Esperado: `>= 1`.

**Rollback:** editar o ficheiro de memória para remover a entrada
(memórias são texto simples, não uma DB transacional).

**Gotchas:** não sobrescrever as entradas anteriores (2026-07-13 até
2026-07-19) — a memória é um log append-only por convenção deste projeto;
acrescenta ao fundo, não reescrevas o topo.

---

## Ordem recomendada de execução

1 → 2 → 3 → 4 → 5 → 6 (nenhuma depende tecnicamente da anterior exceto
o passo 1, que só pode ser *fechado* depois de 2026-07-26 — podes
registar o job de verificação já hoje e avançar para os passos 2-6 em
paralelo).
