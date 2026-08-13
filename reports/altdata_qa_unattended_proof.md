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

## Teste negativo — revalidação final (2026-08-13 02:17:36–02:17:42 WEST)

Foi usado um serviço transitório isolado, nunca o QA real manualmente:

```sh
sudo systemd-run --unit=ib-altdata-qa-negtest-20260813 \
  --property=OnFailure=ib-altdata-qa-alert.service --wait /bin/false
```

O serviço negativo terminou `Result=exit-code`, `ExecMainStatus=1` e o journal
registou `Triggering OnFailure= dependencies`. O handler iniciou de imediato e
terminou sem timeout:

```text
2026-08-13T02:17:36+01:00 ... Starting ib-altdata-qa-alert.service ...
2026-08-13T02:17:41+01:00 ... Deactivated successfully.
2026-08-13T02:17:42+01:00 conductor[...] api-failure logged (notify-only) -> ib_bot: ib_bot/altdata-qa
```

Após o estado final, `systemctl show ib-altdata-qa-alert.service` devolveu
`Result=success`, `ExecMainStatus=0`, `ActiveState=inactive`. A unit instalada
usa `conductor api-failure ... --notify-only`; isto evita o timeout de 120 s
observado no teste de 2026-08-12 antes desta correção.

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
