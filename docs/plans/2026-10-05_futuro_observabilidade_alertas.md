# Futuro 2 — Alertas para falhas silenciosas (2026-10-05)

**Gate de arranque:** só começa quando o Passo 1 do plano de fixes de 2026-10-05 estiver `done` —
verificar com:
```
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT account_id, status FROM paper_rebalance_logs WHERE account_id=2 ORDER BY timestamp DESC LIMIT 3;"
```
Deve devolver 3 linhas sem `status=ERROR` (ou `ERROR` só por uma razão de negócio documentada,
não um crash) antes de começar este plano.

## Contexto para o executor

Três falhas silenciosas já foram encontradas neste projeto em 3 meses: (1) o
`paper_rebalance_daily_task` a falhar 45+ dias sem ninguém notar na conta 1 e na conta 2 (parte
corrigida em 09-28, parte ainda em aberto — ver Futuro 1 do plano de fixes); (2) o backtest
semanal quase falhar por timeout em 2026-09-20 sem o alerta `OnFailure` disparar (corrigido no
mesmo dia); (3) o backup noturno PIT recusou-se corretamente a correr em 2026-10-05 por dirty
tree — este NÃO foi silencioso (a guarda `require_main()` funcionou como desenhada), mas mostra
que o padrão "algo falha, ninguém vê" continua a aparecer de formas novas. O padrão comum: "existe
um alerta configurado" não é o mesmo que "o alerta chega a alguém a tempo".

## Objetivo

1. Garantir que `paper_rebalance_daily_task` dispara um alerta visível sempre que
   `paper_rebalance_logs.status == 'ERROR'` (não só uma linha na tabela que ninguém consulta).
2. Um teste de fumo trimestral do mecanismo de alerta do backtest semanal (matar o job de
   propósito e confirmar que a notificação chega) — herdado do plano equivalente de 09-28, ainda
   não feito.
3. Um alerta dedicado para `ib-altdata-backup.service`/`ib-altdata-qa.service` quando falham por
   `working tree is dirty` (o cenário de hoje de madrugada) — hoje só aparece no `journalctl`, sem
   notificação ativa.

## Passo 1 — Alerta ativo para paper rebalance

**Comandos exatos:** dentro de um worktree novo (nunca no checkout principal — ver `AGENTS.md`):
```
git -C /home/servidor/Desktop/cursor-projects/ib_bot worktree add -b feat/paper-rebalance-alert-20261005 \
  /home/servidor/ib-bot-alert-20261005 main
```
Editar `backend/app/worker/tasks.py`, no bloco `except Exception as e:` dentro de
`paper_rebalance_daily_task` (já tem `logger.exception` com traceback desde o fix de 09-28), para
também chamar o mesmo mecanismo `conductor api-failure --project ib_bot --service
paper-rebalance --notify-only` usado por `ib-altdata-qa-alert.service`.

**Oracle de aceitação:** teste automatizado que força um erro sintético dentro de
`paper_rebalance_daily_task` (mock) e confirma que uma notificação `notify:api_failure` é
inserida (ver padrão já implementado em `ib-altdata-qa-alert.service`, cujo comentário explica o
porquê do `--notify-only`).

**Rollback:** `git worktree remove /home/servidor/ib-bot-alert-20261005 --force`, não integrar em
`main`.

**Gotchas:** **não** chames `domain_turn(dm, ...)` (turno de agente completo) a partir de dentro
do worker Celery — incidente real de 2026-08-12 documentado no comentário do próprio ficheiro
systemd: isso causa timeout de 120s e um alarme que falha sempre. Usa sempre `--notify-only`.

## Passo 2 — Alerta para falhas de "dirty tree" no backup/QA PIT

**Comandos exatos:**
```
grep -n "refusing to run" /home/servidor/Desktop/cursor-projects/ib_bot/infra/scripts/backup_altdata_snapshots.sh
```
Adicionar, no mesmo ponto onde o script faz `exit 2` por tree sujo, uma chamada a
`conductor api-failure --project ib_bot --service altdata-backup --notify-only --reason dirty_tree`
antes do `exit`, para que a falha chegue ao feed do domain manager em vez de só ao `journalctl`.

**Oracle de aceitação:** correr o script manualmente num clone de teste do repo (nunca no
checkout principal) com uma alteração não commitada propositada, confirmar `exit 2` E confirmar
que a notificação `notify:api_failure` aparece no feed do Conductor para `ib_bot`.

**Rollback:** `git checkout -- infra/scripts/backup_altdata_snapshots.sh` no worktree de teste; não
tocar no checkout principal.

**Gotchas:** testar sempre contra um clone/worktree isolado, nunca contra o checkout principal
real — um teste malfeito aqui pode deixar o checkout principal genuinamente sujo e bloquear o
backup real da próxima madrugada.

## Passo 3 — Teste de fumo trimestral do alerta do backtest semanal

**Comandos exatos:** agendar (via Conductor, não systemd solto) uma verificação trimestral:
```
conductor jobs add --mode run_cmd --owner ib_bot \
  --run-cmd 'systemctl kill --signal=SIGKILL ib-backtests.service && sleep 5 && journalctl -u ib-backtests-alert.service --since "5 min ago" | grep -q "notify:api_failure"' \
  --deadline-min 30 --dedup-key ib-backtests-alert-smoketest-quarterly \
  --recovery-message "Verificar se o alerta OnFailure do ib-backtests disparou; se não, o contrato do CLI conductor jobs add pode ter mudado (ver incidente 2026-09-20)." \
  --resume-message "VERIFICAR se a notificação notify:api_failure chegou no journalctl e no feed do ib_bot DM, depois continuar."
```

**Oracle de aceitação:** notificação `notify:api_failure` visível no feed do domain manager
`ib_bot` dentro de 5 minutos do kill sintético.

**Rollback:** nenhum (o `ib-backtests.timer` volta a disparar normalmente no próximo horário
agendado; o kill sintético não deixa estado pendente).

**Gotchas:** fazer isto fora de uma janela em que o backtest semanal real esteja a correr (não
domingo de madrugada), para não confundir um teste com uma falha real.
