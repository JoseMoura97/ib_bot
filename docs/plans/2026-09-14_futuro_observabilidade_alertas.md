# Plano Futuro 3/3 — Observabilidade para falhas silenciosas (2026-09-14)

**Gate de arranque:** só começa quando os Passos 1 e 3 do `2026-09-14_plano_fixes.md` estiverem
verdes — verificar com:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git log --oneline -3 -- backend/app/worker/tasks.py | head -3   # deve incluir o commit do fix exc_info
docker system df --format "{{.Type}}: {{.Reclaimable}}" | grep Images   # deve já não mostrar ~32GB
```

## Contexto para o executor

O Finding CRÍTICO #0 ficou escondido durante pelo menos 31 dias corridos (confirmado dia a dia
entre 08-14 e 09-13 nas auditorias de 09-07 e 09-14), apesar de já ter sido descoberto há uma
semana e ainda não corrigido no momento desta auditoria — porque:
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
(seja no paper trading, seja noutra tarefa diária) apareça num audit em dias, não em semanas ou
meses.

## Passo 1 — Alerta para `paper_rebalance_daily_task` com 0 sucessos consecutivos

**Objetivo:** disparar um alerta (mesmo canal usado por `ib-altdata-qa-alert.service` — verificar
qual é com `systemctl list-units | grep ib-.*alert`) se a tarefa correr N dias seguidos sem
produzir nenhuma linha nova em `paper_trades` para NENHUMA conta.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# Localizar o mecanismo de alerta existente para reutilizar o mesmo canal:
systemctl list-units --all | grep -i "ib-.*alert"
cat /etc/systemd/system/ib-altdata-qa-alert.service 2>/dev/null

# Criar um script de verificação diário (exemplo de esqueleto — adaptar ao formato real do
# alerta existente, não reinventar o canal de notificação):
cat > scripts/check_paper_rebalance_health.py << 'PYEOF'
#!/usr/bin/env python3
"""Verifica se paper_rebalance_daily_task produziu trabalho real nos últimos N dias.
Sai com código != 0 (para o OnFailure do systemd apanhar) se 0 trades novos em N dias."""
import subprocess, sys, datetime

N_DIAS = 3  # janela de tolerância — 1 dia pode ser coincidência de mercado fechado
cmd = [
    "docker", "exec", "ib_bot-db-1", "psql", "-U", "ibbot", "-d", "ibbot", "-t", "-A",
    "-c", f"select count(*) from paper_trades where timestamp > (CURRENT_DATE - {N_DIAS});"
]
out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
count = int(out)
if count == 0:
    print(f"ALERTA: 0 trades novos em paper_trades nos últimos {N_DIAS} dias — "
          f"paper_rebalance_daily_task pode estar a falhar silenciosamente.")
    sys.exit(1)
print(f"OK: {count} trades novos nos últimos {N_DIAS} dias.")
sys.exit(0)
PYEOF
chmod +x scripts/check_paper_rebalance_health.py
```

Depois, criar unit systemd + timer seguindo o MESMO padrão de `ib-altdata-qa.service`/`.timer`
(copiar a estrutura, trocar o `ExecStart` para o script acima, e o `OnFailure=` para o mesmo
serviço de alerta já usado por `ib-altdata-qa-alert.service`).

**Oráculo de aceitação:**
```bash
# Teste negativo: forçar o script a ver 0 trades (ex.: apontar para uma janela de 0 dias) e
# confirmar que sai com código 1:
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -t -A -c "select count(*) from paper_trades where timestamp > (CURRENT_DATE + 1);"
# esperado: 0 (janela no futuro, sempre 0) — usar isto só para confirmar a lógica do script, não
# como teste em produção.

# Teste positivo real (depois do Passo 1 do plano de fixes corrigir o motor):
python3 scripts/check_paper_rebalance_health.py
echo $?
# esperado: 0 (OK) se o motor estiver mesmo a gerar trades.
```

**Rollback:** `sudo systemctl disable --now check-paper-rebalance-health.timer` e apagar a unit.

**Gotchas:** o script E o timer são só leitura da DB (SELECT) — não escrevem nada. O `OnFailure=`
do systemd é o mecanismo de notificação, igual ao já usado pelos outros 2 alertas do ib_bot; não
inventar um canal novo.

## Passo 2 — Traceback completo em todas as tarefas Celery do worker

**Objetivo:** garantir que NENHUMA tarefa futura apanhe uma exceção e só regista a mensagem, sem
traceback — generalizar a correção do Passo 1 do plano de fixes a todo o `backend/app/worker/tasks.py`.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
grep -n "logger.warning(f\".*error=" backend/app/worker/tasks.py
# Rever cada ocorrência: se a exceção é apanhada e só um `logger.warning` sem exc_info é emitido,
# trocar para `logger.error(..., exc_info=True)` (warning → error muda a severidade visível em
# dashboards de log; exc_info=True adiciona o traceback).
```

**Oráculo de aceitação:**
```bash
grep -c "except Exception" backend/app/worker/tasks.py
grep -c "exc_info=True" backend/app/worker/tasks.py
# o segundo número deve ser >= ao número de blocos except que fazem logging de erro (não
# necessariamente igual ao primeiro — alguns except podem ser re-raise puro, o que já propaga).
```

**Rollback:** `git revert <commit>`.

**Gotchas:** não adicionar `exc_info=True` a logs de `INFO`/`DEBUG` de fluxo normal — só a
`except Exception` que hoje esconde erros reais. Não mudar o comportamento de retry/falha da
tarefa em si, só a visibilidade do log.
