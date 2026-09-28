# Futuro 3 — Alertas para falhas silenciosas (2026-09-28)

**Gate de arranque:** só começa quando o Passo 1 do plano de fixes de 2026-09-28 estiver `done` —
verificar com:
```
git -C /home/servidor/Desktop/cursor-projects/ib_bot log --oneline --grep="paper_rebalance" -5
```
Deve mostrar o commit do fix já mesclado em `main`.

## Contexto para o executor

Duas falhas silenciosas já foram encontradas neste projeto em 2 meses: (1) o
`paper_rebalance_daily_task` a falhar 45+ dias sem ninguém notar (bug corrigido no Futuro 1 deste
pacote), e (2) o backtest semanal quase falhar por timeout em 2026-09-20 sem o alerta `OnFailure`
disparar (esse já foi corrigido no mesmo dia por outro operador). O padrão comum: "existe um
alerta configurado" não é o mesmo que "o alerta funciona". Este plano garante que o próximo bug
deste tipo é detetado em dias, não semanas.

## Objetivo

1. Garantir que `paper_rebalance_daily_task` dispara um alerta visível sempre que
   `PaperRebalanceLog.status == "ERROR"` (não só um log warning).
2. Um teste de fumo trimestral do mecanismo de alerta do backtest semanal (matar o job de
   propósito e confirmar que a notificação chega).

## Passo 1 — Alerta ativo para paper rebalance

**Comandos exatos:** dentro de um worktree novo (nunca no checkout principal — ver `AGENTS.md`):
```
git -C /home/servidor/Desktop/cursor-projects/ib_bot worktree add -b feat/paper-rebalance-alert \
  /home/servidor/ib-bot-alert-20260928 main
```
Editar `backend/app/worker/tasks.py` para que o bloco `except Exception as e:` (linha ~559)
chame o mesmo mecanismo `conductor api-failure --project ib_bot --service paper-rebalance
--notify-only` usado por `ib-altdata-qa-alert.service`, em vez de só `logger.warning`.

**Oracle de aceitação:** teste automatizado que força um erro sintético dentro de
`paper_rebalance_daily_task` (mock) e confirma que uma notificação `notify:api_failure` é
inserida (ver como `ib-altdata-qa-alert.service` já faz isto, comentário no próprio ficheiro
systemd explica o padrão `--notify-only` e porquê é obrigatório, não opcional).

**Rollback:** `git worktree remove /home/servidor/ib-bot-alert-20260928 --force`, não integrar em
`main`.

**Gotchas:** **não** chames `domain_turn(dm, ...)` diretamente (turno de agente completo) a partir
de dentro do worker Celery — o comentário em `ib-altdata-qa-alert.service` documenta um incidente
real (2026-08-12) em que isso causou um timeout de 120s e um alarme que falha sempre. Usa sempre
`--notify-only`.

## Passo 2 — Teste de fumo trimestral do alerta do backtest semanal

**Comandos exatos:** agendar (via Conductor, não systemd solto) uma verificação trimestral:
```
conductor jobs add --mode run_cmd --owner ib_bot \
  --run-cmd 'systemctl kill --signal=SIGKILL ib-backtests.service && sleep 5 && journalctl -u ib-backtests-alert.service --since "5 min ago" | grep -q "notify:api_failure"' \
  --deadline-min 30 --dedup-key ib-backtests-alert-smoketest-quarterly \
  --recovery-message "Verificar se o alerta OnFailure do ib-backtests disparou; se não, o contrato do CLI conductor jobs add pode ter mudado outra vez (ver incidente 2026-09-20)." \
  --resume-message "VERIFICAR se a notificação notify:api_failure chegou no journalctl e no feed do ib_bot DM, depois continuar."
```

**Oracle de aceitação:** notificação `notify:api_failure` visível no feed do domain manager
`ib_bot` dentro de 5 minutos do kill sintético.

**Rollback:** nenhum (o `ib-backtests.timer` volta a disparar normalmente no próximo horário
agendado; o kill sintético não deixa estado pendente).

**Gotchas:** faz isto fora de uma janela em que o backtest semanal real esteja a correr (não
domingo de madrugada), para não confundir um teste com uma falha real.
