# Alt-data PIT QA Unattended Proof (h3)

## Instalação e captura preservada

As três units estão instaladas em `/etc/systemd/system/`. O timer
`ib-altdata-qa.timer` está `enabled` e `active (waiting)` desde 2026-08-11
18:30:28 WEST, com link em `timers.target.wants/`; dispara diariamente às
07:00 UTC (08:00 WEST). A service declara
`OnFailure=ib-altdata-qa-alert.service`.

A captura não foi alterada: `ib_bot-beat-1` continua `running`, e
`backend/app/worker/celery_app.py` agenda `altdata_snapshot_daily_task` para
06:00 UTC. O QA corre uma hora depois.

## Teste negativo — KB 668d0069 §4 (verbatim)

O texto abaixo é a evidência histórica literal do KB `668d0069`; não foi
editado. A sua leitura prematura é corrigida na secção seguinte.

```text
== 4. h3 negative test: EXECUTADO PELO MANAGER, PASSOU ==
sudo systemd-run --unit=ib-altdata-qa-negtest \
  --property=OnFailure=ib-altdata-qa-alert.service --property=User=servidor --wait /bin/false
Resultado (journalctl, 2026-08-12 00:03:41 WEST):
  Started ib-altdata-qa-negtest.service - /bin/false.
  ib-altdata-qa-negtest.service: Main process exited, code=exited, status=1/FAILURE
  ib-altdata-qa-negtest.service: Failed with result 'exit-code'.
  ib-altdata-qa-negtest.service: Triggering OnFailure= dependencies.
  ib-altdata-qa-alert.service: multiple trigger source candidates for exit status propagation
    (ib-altdata-qa-negtest.service, ib-altdata-qa.service), skipping.
  Starting ib-altdata-qa-alert.service - Alert ib_bot DM when daily alt-data QA persistence fails...
systemctl show ib-altdata-qa-negtest: Result=exit-code ExecMainStatus=1 ActiveState=failed
systemctl show ib-altdata-qa-alert.service: Result=success ExecMainStatus=0
Depois: sudo systemctl reset-failed ib-altdata-qa-negtest (exit 0). Unit descartável removida.
A linha "multiple trigger source candidates ... skipping" NÃO é falha: refere-se só à
propagação do exit status para o alerta; o OnFailure disparou e o alert service arrancou e
terminou com sucesso. Perna (c) de h3 SATISFEITA — colar este bloco verbatim em
reports/altdata_qa_unattended_proof.md e commitar.
AVISO: o alerta api_failure de ib_bot/altdata-qa às 00:03:41 WEST de 2026-08-12 é ESTE TESTE,
não um incidente real. Não abrir investigação.

```

## Correção fc0448a0 e revalidação final

`fc0448a0` corrigiu a conclusão inicial: o `systemctl show
ib-altdata-qa-alert.service` do KB foi lido antes do desfecho final. Sem
`--notify-only`, `conductor api-failure` entregava o evento rapidamente, mas
depois tentava correr um turno de DM inline e a unit expirava aos 120 segundos
com `Result=timeout`.

O `ExecStart` instalado e o ficheiro no repositório agora usam
`conductor api-failure ... --notify-only`. A revalidação final de 2026-08-13
02:17:36–02:17:42 WEST usou um serviço transitório isolado, nunca o QA real
manualmente:

```sh
sudo systemd-run --unit=ib-altdata-qa-negtest-20260813 \
  --property=OnFailure=ib-altdata-qa-alert.service --wait /bin/false
```

O serviço negativo terminou `Result=exit-code`, `ExecMainStatus=1` e o journal
registou `Triggering OnFailure= dependencies`. O handler iniciou e terminou
sem timeout:

```text
2026-08-13T02:17:36+01:00 ... Starting ib-altdata-qa-alert.service ...
2026-08-13T02:17:41+01:00 ... Deactivated successfully.
2026-08-13T02:17:42+01:00 conductor[...] api-failure logged (notify-only) -> ib_bot: ib_bot/altdata-qa
```

Após o estado final, `systemctl show ib-altdata-qa-alert.service` devolveu
`Result=success`, `ExecMainStatus=0`, `ActiveState=inactive`.

## Recibos autónomos

* **#1 verde:** 2026-08-12 08:00:14 WEST —
  `ib-altdata-qa.service` exit `0/SUCCESS`; commit
  `4a9bae7 qa(altdata): daily receipt 2026-08-12`; push
  `2cad122..4a9bae7 HEAD -> main`; sem turno de agente no intervalo.

O time-gate da aceitação ainda requer os recibos autónomos #2 e #3 dos disparos
de 2026-08-13 e 2026-08-14 às 08:00 WEST. É proibido iniciar
`ib-altdata-qa.service` manualmente: só o timer pode produzir esses recibos.

Re-check de fecho:

```sh
test -L /etc/systemd/system/timers.target.wants/ib-altdata-qa.timer && \
grep -q '^OnFailure=ib-altdata-qa-alert.service$' /etc/systemd/system/ib-altdata-qa.service && \
test -f /home/servidor/Desktop/cursor-projects/ib_bot/reports/altdata_qa_unattended_proof.md && \
[ "$(journalctl -u ib-altdata-qa.service --since '-4 days' --no-pager | grep -c 'Finished ib-altdata-qa.service - IB Bot daily versioned QA for altdata_snapshots')" -ge 3 ]
```

## Re-check live 2026-08-13 — fase ainda não concluída

O anterior bloco de fecho não é suficiente. A unit e o timer continuam
correctamente instalados, mas o primeiro disparo autónomo de 2026-08-13 falhou
antes de um agente reconstruir a imagem Docker e o voltar a iniciar. Esse
segundo arranque é deliberadamente excluído da métrica de operação sem agente.

```text
2026-08-13T08:00:00+01:00 Starting ib-altdata-qa.service
2026-08-13T08:00:07+01:00 Main process exited, status=2/INVALIDARGUMENT
verify_altdata_chain.py: error: unrecognized arguments: --extend

2026-08-13T08:14:24+01:00 Starting ib-altdata-qa.service
2026-08-13T08:14:35+01:00 [main eb2d6f9] qa(altdata): daily receipt 2026-08-13
2026-08-13T08:14:38+01:00 Finished ib-altdata-qa.service
```

A causa foi a imagem `worker` ainda anterior ao parser `--extend`; a execução
verde às 08:14 foi manual após o rebuild, pelo que o streak autónomo é **0** e
tem de reiniciar nos disparos do timer de 2026-08-14, 2026-08-15 e
2026-08-16 às 08:00 WEST.

O `OnFailure` também revelou um defeito real: às 08:00 a service de alerta
arrancou, mas a notificação foi suprimida porque o teste negativo das 02:17
tinha ocupado a cooldown de 720 minutos:

```text
events: 2026-08-13 02:17:37 notify:api_failure ib_bot/altdata-qa
events: 2026-08-13 08:00:08 notify:api_failure_suppressed ib_bot/altdata-qa
```

O ficheiro versionado `infra/systemd/ib-altdata-qa-alert.service` corrige a
causa: usa `--cooldown-min 0 --notify-only`. Cada activação falhada do QA tem
um único `OnFailure` do systemd, mas já não pode ser ocultada por um alerta de
teste ou por uma falha de outro dia.

O worker não tem privilégio para instalar essa alteração (a preflight devolve
`sudo: The "no new privileges" flag is set`). O worktree já contém o commit
versionado; o operador privilegiado deve executar exactamente a partir dele:

```sh
cd /home/servidor/Desktop/cursor-projects/ib_bot/.worktrees/phase-h3_unattended_operation-b331
sudo install -m 0644 infra/systemd/ib-altdata-qa-alert.service /etc/systemd/system/ib-altdata-qa-alert.service
sudo systemctl daemon-reload
/usr/local/bin/conductor api-failure --project ib_bot --service altdata-qa --detail "h3 controlled cooldown seed" --hint "controlled test only" --cooldown-min 720 --notify-only
sudo systemd-run --unit=ib-altdata-qa-negtest-cooldown-20260813 --property=OnFailure=ib-altdata-qa-alert.service --wait /bin/false || test $? -eq 1
journalctl --since '2026-08-13 00:00:00' --no-pager -o short-iso | grep -E 'ib-altdata-qa-negtest-cooldown-20260813|ib-altdata-qa-alert|api-failure'
sudo systemctl reset-failed ib-altdata-qa-negtest-cooldown-20260813
```

The required positive result is the controlled service exiting `1/FAILURE`,
`Triggering OnFailure= dependencies`, a fresh `api-failure logged (notify-only)
-> ib_bot: ib_bot/altdata-qa` after the cooldown seed, and
`ib-altdata-qa-alert.service Result=success ExecMainStatus=0`. This test is
not complete until those literal journal lines are pasted here.
