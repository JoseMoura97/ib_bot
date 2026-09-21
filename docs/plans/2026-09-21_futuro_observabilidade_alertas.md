# Plano Futuro 2/3 — Observabilidade para falhas silenciosas (2026-09-21)

**Gate de arranque:** só começa quando os Passos 1 e 3 do `2026-09-21_plano_fixes.md` estiverem
verdes — verificar com:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git log --oneline -3 -- backend/app/worker/tasks.py | head -3   # deve incluir o commit do fix exc_info
docker system df --format "{{.Type}}: {{.Reclaimable}}" | grep Images   # deve já não mostrar ~31GB
```

## Contexto para o executor

Este projeto teve DOIS incidentes de observabilidade em semanas seguidas, com a mesma raiz:
**"a tarefa correu" não é o mesmo que "a tarefa fez o trabalho esperado", e um alerta configurado
não é o mesmo que um alerta que funciona.**

1. **`paper_rebalance_daily_task`** (descoberto 09-07, ainda ativo a 09-21 — 38 dias corridos): a
   tarefa Celery "sucede" ao nível do sistema de tarefas mesmo quando o rebalanceamento interno
   falha para as 9 estratégias; o erro é só um `logger.warning` sem traceback, sem alerta.
2. **NOVO (09-20): o backtest semanal (`ib-backtests.service`) foi morto por timeout a 80,7% da
   regeneração de gráficos, e o alerta `OnFailure` (`ib_backtests_alert.sh`) FALHOU TAMBÉM** —
   o script chamava `conductor jobs add` com uma sintaxe antiga (faltavam `--dedup-key`/
   `--recovery-message`, exigidos depois de uma mudança de contrato do CLI). Ninguém foi acordado.
   Foi corrigido no mesmo dia, mas só porque um operador reparou manualmente — não havia nenhum
   teste automático que validasse periodicamente "o mecanismo de alerta em si ainda funciona".

Este plano fecha as duas lacunas: alerta de "sucesso vazio" para o paper trading, e um teste de
fumo periódico para os alertas `OnFailure` existentes (para não repetir o quase-incidente de
20-09 com outro timer no futuro).

## Passo 1 — Alerta para `paper_rebalance_daily_task` com 0 sucessos consecutivos

**Objetivo:** disparar um alerta (mesmo canal usado por `ib-altdata-qa-alert.service`) se a tarefa
correr N dias seguidos sem produzir nenhuma linha nova em `paper_trades` para NENHUMA conta.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
systemctl list-units --all | grep -i "ib-.*alert"
cat /etc/systemd/system/ib-altdata-qa-alert.service 2>/dev/null

cat > scripts/check_paper_rebalance_health.py << 'PYEOF'
#!/usr/bin/env python3
"""Verifica se paper_rebalance_daily_task produziu trabalho real nos últimos N dias.
Sai com código != 0 (para o OnFailure do systemd apanhar) se 0 trades novos em N dias."""
import subprocess, sys

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
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -t -A -c "select count(*) from paper_trades where timestamp > (CURRENT_DATE + 1);"
# esperado: 0 (janela no futuro, sempre 0) — usar isto só para confirmar a lógica do script.
python3 scripts/check_paper_rebalance_health.py; echo $?
# esperado: 0 (OK) depois do Passo 1 do plano de fixes ter corrigido o motor.
```

**Rollback:** `sudo systemctl disable --now check-paper-rebalance-health.timer` e apagar a unit.

**Gotchas:** o script e o timer são só leitura da DB (SELECT) — não escrevem nada.

## Passo 2 — Traceback completo em todas as tarefas Celery do worker

**Objetivo:** garantir que NENHUMA tarefa futura apanhe uma exceção e só registe a mensagem, sem
traceback — generalizar a correção do Passo 1 do plano de fixes a todo o
`backend/app/worker/tasks.py`.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
grep -n "logger.warning(f\".*error=" backend/app/worker/tasks.py
```

**Oráculo de aceitação:**
```bash
grep -c "except Exception" backend/app/worker/tasks.py
grep -c "exc_info=True" backend/app/worker/tasks.py
# o segundo número deve ser >= ao número de blocos except que fazem logging de erro.
```

**Rollback:** `git revert <commit>`.

**Gotchas:** não adicionar `exc_info=True` a logs de fluxo normal — só a `except Exception` que
hoje esconde erros reais.

## Passo 3 (NOVO) — Teste de fumo trimestral do mecanismo `OnFailure` dos timers do ib_bot

**Objetivo:** garantir que o incidente de 20-09 (alerta que também falhou) não se repete sem
ninguém notar — testar o próprio alerta, não só o job.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# Ler o script de alerta real primeiro, para entender o contrato atual do CLI usado:
cat infra/scripts/ib_backtests_alert.sh

# Criar um script de teste de fumo que dispara uma falha CONTROLADA de um serviço systemd
# de teste (nunca dos 3 timers reais em produção) e confirma que o OnFailure dispara e que o
# `conductor jobs add` (ou equivalente) aceita os argumentos sem erro de argparse:
sudo systemd-run --unit=ib-alert-smoketest --property="OnFailure=ib-backtests-alert.service" \
  /bin/false
sleep 5
sudo journalctl -u ib-backtests-alert.service --since "-2min" --no-pager | tail -20
```

**Oráculo de aceitação:** o log do serviço de alerta mostra uma execução recente SEM erro de
`argparse`/CLI (o mesmo tipo de erro que causou o silêncio em 20-09) — confirma que o contrato
atual do `conductor jobs add` ainda bate certo com o que o script de alerta envia.

**Rollback:** `sudo systemctl reset-failed ib-alert-smoketest.service` (o serviço de teste é
transiente, desaparece sozinho).

**Gotchas:** usar SEMPRE um serviço de teste transiente (`systemd-run --unit=...-smoketest`),
NUNCA disparar uma falha real em `ib-backtests.service`/`ib-altdata-qa.service`/
`ib-altdata-backup.service` só para testar o alerta — isso interromperia trabalho real. Repetir
este passo a cada trimestre (documentar a data da última execução num comentário no próprio
script de smoke test).
