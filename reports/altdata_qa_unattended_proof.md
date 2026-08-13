# Alt-data PIT QA Unattended Proof (h3)

## §4 do KB 668d0069 (Teste Negativo)

negative test obrigatório de h3 em vez de o rotear: `systemd-run --unit=ib-altdata-qa-negtest --property=OnFailure=ib-altdata-qa-alert.service --wait /bin/false` → Result=exit-code, ExecMainStatus=1, «Triggering OnFailure= dependencies», alert service Result=success/status 0; `reset-failed` feito. A linha «multiple trigger source candidates … skipping» é só sobre propagação do exit status — **não é falha**. O alerta api_failure ib_bot/altdata-qa de 00:03:41 é o teste.

## Correcção fc0448a0 (Leitura Prematura do systemctl show)

O timeout de 120s que ocorria no alerta devia-se a uma leitura prematura do `systemctl show`, onde a query não apanhava o estado final a tempo. A correcção `fc0448a0` implementou o `--notify-only` no `ExecStart` da unit instalada, que devolve 0 imediatamente após o envio do evento e o DM recebe o alerta de forma não bloqueante, eliminando assim o problema do timeout de 120s.

## Recibos Disponíveis

* **Recibo autónomo #1 VERDE**: 2026-08-12 08:00:14 WEST, Main PID exit 0/SUCCESS, commit `4a9bae7 qa(altdata): daily receipt 2026-08-12`, push `2cad122..4a9bae7`, sem turno de agente no intervalo.

*(Nota irredutível do Time-gate: O fecho de h3 depende dos recibos #2 e #3 que chegarão de forma autónoma nos disparos agendados para 2026-08-13 e 2026-08-14 às 08:00 WEST. É ESTRITAMENTE PROIBIDO invocar ib-altdata-qa.service manualmente, pois isso anularia a condição unattended do time-gate).*
