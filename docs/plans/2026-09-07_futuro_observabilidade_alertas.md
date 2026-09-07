# Plano Futuro 3/3 — Observabilidade para falhas silenciosas (2026-09-07)

**Gate de arranque:** só começa quando os Passos 1 e 3 do `2026-09-07_plano_fixes.md` estiverem
verdes — verificar com:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git log --oneline -3 -- backend/app/worker/tasks.py | head -3   # deve incluir o commit do fix exc_info
docker system df --format "{{.Type}}: {{.Reclaimable}}" | grep Images   # deve já não mostrar ~32GB
```

## Contexto para o executor

O Finding CRÍTICO #0 do audit de 2026-09-07 ficou escondido durante pelo menos 24 dias, e as 3
auditorias anteriores (08-17, 08-24, 08-31) não o detetaram, porque:
1. A tarefa Celery "sucedia" ao nível do sistema de tarefas (`Task ... succeeded`), mesmo com o
   rebalanceamento interno a falhar — não havia sinal de falha visível em `systemctl` nem em
   greps óbvios por "FAILED"/"ERROR".
2. O erro era registado só como `logger.warning(...)`, sem *traceback*, tornando impossível saber
   a causa sem reproduzir manualmente.
3. Não existe nenhum alerta automático para "a tarefa X correu mas fez 0 trabalho útil N dias
   seguidos" — só existe para falhas óbvias (`ib-altdata-qa-alert.service`,
   `ib-backtests-alert.service`, que respondem a `OnFailure` do systemd, não a "sucesso vazio"
   dentro de uma tarefa Celery).

Este plano fecha essa lacuna de observabilidade, para que a PRÓXIMA vez que algo assim aconteça
(seja no paper trading, seja noutra tarefa diária) apareça num audit em dias, não em semanas.

## Passo 1 — Alerta para `paper_rebalance_daily_task` com 0 sucessos consecutivos

**Objetivo:** disparar um alerta (mesmo canal usado por `ib-altdata-qa-alert.service` — acordar o
gestor de domínio `ib_bot` no Conductor) se a tarefa correr N dias seguidos sem NENHUM
rebalanceamento bem-sucedido (todas as contas em erro).

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
grep -n "class PaperRebalanceLog" -A 15 backend/app/models/*.py 2>/dev/null
# Confirma se já existe uma tabela de log estruturado (o audit de 09-07 encontrou o CÓDIGO que
# tenta escrever PaperRebalanceLog em tasks.py, mas não confirmou se a tabela existe na DB —
# verificar primeiro:
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "\dt" | grep -i paper_rebalance_log
```
Se a tabela **não existir** (a query do audit de 2026-09-07 devolveu `relation
"paper_rebalance_log" does not exist"` ao tentar o nome em minúsculas com underscore — confirmar o
nome real da tabela gerado pelo ORM, pode ter um nome diferente por convenção do SQLAlchemy),
identificar o nome real:
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "\dt" | grep -i rebalance
```
Depois, criar um script simples que corre depois da tarefa diária (novo `celery beat` entry ou
script standalone via `ib-altdata-qa-alert.service`-style systemd `OnFailure`):
```python
# backend/app/worker/tasks.py — adicionar ao fim de paper_rebalance_daily_task, antes do finally:
from app.models.paper import PaperRebalanceLog
from datetime import datetime, timedelta
recent = db.query(PaperRebalanceLog).filter(
    PaperRebalanceLog.created_at >= datetime.utcnow() - timedelta(days=3)
).all()
if recent and all(r.status == "ERROR" for r in recent):
    logger.error(
        f"paper_rebalance_daily: {len(recent)} consecutive ERROR entries in last 3 days — "
        f"ALERT: rebalance engine likely broken, see docs/audits/2026-09-07_audit_profundo.md Finding #0"
    )
```
Usar `logger.error` (não `warning`) — isto já é suficiente para aparecer num grep de
"ERROR" em auditorias futuras, e pode ser ligado a um `OnFailure` systemd se a tarefa passar a
lançar exceção nesse cenário (decisão de desenho: preferir alerta visível a falha dura, para não
travar as outras contas/portfolios que possam estar a funcionar bem).

**Oráculo de aceitação:**
```bash
docker logs ib_bot-worker-1 --since 5m | grep "ALERT: rebalance engine likely broken"
# Corrido depois de simular 3 dias de erro (ou, mais simples, correr a tarefa 3x seguidas
# manualmente com o bug do Passo 1 do plano de fixes ainda presente num branch de teste) —
# confirma que o alerta dispara quando deveria.
```

**Rollback:** `git revert` do commit deste passo.

**Gotchas:** este alerta é um `logger.error`, não impede a tarefa de continuar a tentar todos os
dias (é intencional — não queremos parar de tentar só porque falhou antes).

## Passo 2 — Checklist de "tarefas diárias com sucesso vazio" para o audit seguinte

**Objetivo:** adicionar ao processo de auditoria (não ao código) um passo explícito que teria
apanhado este bug mais cedo, para reduzir o risco de haver um "Finding #0" equivalente escondido
noutra tarefa.

**Comandos (para o PRÓXIMO audit correr, não para correr agora):**
```bash
# Lista todas as tarefas Celery agendadas no beat:
grep -A 3 "celery_app.conf.beat_schedule" -A 60 /home/servidor/Desktop/cursor-projects/ib_bot/backend/app/worker/celery_app.py
# Para CADA tarefa listada, correr:
docker logs ib_bot-worker-1 --since 200h 2>&1 | grep "<nome_da_tarefa>" | grep -i "error\|warning" | tail -10
# Se qualquer tarefa mostrar o MESMO erro todos os dias, é um Finding #0-equivalente — investigar
# antes de assumir que "a tarefa correu" == "a tarefa funcionou".
```

**Oráculo de aceitação:** o próximo `docs/audits/*.md` tem uma subsecção explícita "Verificação
de sucesso vazio em tarefas diárias" com o resultado deste grep para cada tarefa do
`beat_schedule`.

**Rollback:** N/A (processo de auditoria, não código).

## Passo 3 — Aplicar o mesmo padrão de alerta ao `altdata_snapshot_daily_task` (prevenção)

**Objetivo:** esta tarefa está saudável hoje (11/11 fontes, confirmado no audit de 09-07), mas não
tem proteção contra o mesmo tipo de falha silenciosa parcial (ex.: 8/11 fontes a ter sucesso mas
reportado como `overall_status: ok` por engano). Confirmar que `mandatory_failed_sources > 0` já
dispara `ib-altdata-qa-alert.service` corretamente (parece que sim, por desenho, mas confirmar
com um teste negativo é mais barato que descobrir que não dispara quando precisar).

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
grep -n "mandatory_failed_sources\|overall_status" backend/app/worker/tasks.py | head -20
# Confirmar que existe um caminho de código que muda overall_status para algo != "ok" quando
# mandatory_failed_sources > 0, e que ib-altdata-qa-alert.service (systemd OnFailure) de facto
# lê esse status para decidir se dispara.
```

**Oráculo de aceitação:** teste unitário existente ou novo
(`backend/tests/test_altdata_snapshot_daily.py` ou nome equivalente) que injeta uma fonte
obrigatória falhada e confirma `overall_status != "ok"`. Se já existir um teste assim, só
confirmar que passa (`pytest backend/tests/... -k altdata_snapshot -v`); se não existir, é
trabalho novo deste passo.

**Rollback:** N/A (teste só, não muda comportamento de produção neste passo).
