# Plano Futuro 1/3 — Decisão de negócio sobre o arquivo PIT (2026-09-21)

**Gate de arranque:** só começa quando o Passo 0 do `2026-09-21_plano_fixes.md` estiver verde —
verificar com:
```bash
ls -la /home/servidor/.claude/projects/-home-servidor/memory/ | grep -i "ib_bot.*decisao"
# esperado: pelo menos um ficheiro, datado de 2026-09-21 ou mais recente
```
Se o ficheiro não existir, **não avançar** — significa que o José ainda não respondeu à pergunta
síncrona do Passo 0. Este é o 7º plano seguido a repetir este gate (07-12, 07-20, 08-10, 08-24,
08-31, 09-07, 09-14 já continham uma versão dele); a decisão continua por tomar.

## Contexto para o executor

O robô tira uma "fotografia" (snapshot) diária de 11 fontes de dados públicas (menções no
Congresso, 13F de fundos, apostas contra empresas, etc.) desde 13 de julho de 2026, ininterrupto.
Hoje (2026-09-21) a tabela `altdata_snapshots` tem **778 linhas em 71 dias distintos**, a crescer
~11 linhas/dia. O trabalho de engenharia para manter isto (backup noturno offsite, QA diária,
separação de dono na DB) já está feito e fechado (plano Conductor `04bf8af8`, `done`). O que
**nunca foi decidido** é o DESTINO deste arquivo: vender como produto B2B (competir com Unusual
Whales/Quiver — plano `3702771c` chegou a explorar isto e foi `superseded`), continuar a acumular
sem plano até alguém decidir, ou arquivar e desligar os timers.

Cada semana que passa sem decisão é mais dados acumulados (bom se a decisão for "vender", neutro
se for "não decidir nunca", mau porque o disco e a atenção continuam a ser gastos sem propósito
claro).

## Passo 1 — Apresentar as 3 opções com números reais ao José

**Objetivo:** dar ao José a informação mínima para decidir, não mais uma pergunta aberta.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "select source, count(*) from altdata_snapshots group by source order by count(*) desc;"
du -sh /home/servidor/Desktop/cursor-projects/ib_bot/.cache /home/servidor/Desktop/cursor-projects/ib_bot/backend 2>/dev/null
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -t -A -c \
  "select pg_size_pretty(pg_total_relation_size('altdata_snapshots'));"
```
Usar `request_user_approval` (ou canal síncrono equivalente) com estes 3 números concretos + as 3
opções (vender B2B / continuar sem plano / arquivar e parar).

**Oráculo de aceitação:** entrada de memória (`reference_ib_bot_*pit_decisao*.md` ou secção nova em
`MEMORY-trading.md`) com a opção escolhida, datada de hoje ou mais recente.

**Rollback:** nenhum (decisão, não sistema).

**Gotchas:** não avançar para o Passo 2 sem a decisão explícita — este plano é sobre OBTER a
decisão, o Passo 2 só existe condicional a "vender B2B" ser a escolha.

## Passo 2 (SÓ SE a decisão for "vender B2B") — Levantamento do esforço mínimo de produtização

**Objetivo:** dimensionar o trabalho real antes de o José se comprometer, sem construir nada
ainda.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
find backend/app/api/routes -iname "*altdata*"
grep -rn "altdata" backend/app/api/routes/*.py | grep -i "router\|@app\|@router" | head -20
```
Produzir um documento curto (`docs/plans/2026-09-21_estimativa_b2b_altdata.md`, se este passo for
executado) com: quantos endpoints já existem, o que falta (auth de clientes externos, billing,
rate limiting, documentação), e uma estimativa de esforço em dias, não em promessas.

**Oráculo de aceitação:** o documento existe e lista pelo menos os 4 itens acima com estimativa
numérica.

**Rollback:** apagar o documento (não afeta sistema).

**Gotchas:** este passo é só levantamento — não implementar nenhum endpoint novo, não expor a API
publicamente, não criar nenhuma conta de cliente. Qualquer passo de implementação real exige um
novo plano próprio, aprovado depois deste levantamento.

## Passo 3 (SÓ SE a decisão for "arquivar e parar") — Desligar os timers com segurança

**Objetivo:** parar a acumulação sem perder o histórico já capturado.

**Comandos:**
```bash
# Confirmar backup offsite mais recente ANTES de desligar (não parar sem confirmar que o
# histórico já está seguro):
sudo systemctl status ib-altdata-backup.service --no-pager | grep -A2 "Trigger\|since"
sudo systemctl disable --now ib-altdata-qa.timer ib-altdata-backup.timer
```

**Oráculo de aceitação:**
```bash
systemctl list-timers --all | grep -c "ib-altdata"
# esperado: 0 (nenhum timer ativo)
```

**Rollback:** `sudo systemctl enable --now ib-altdata-qa.timer ib-altdata-backup.timer`.

**Gotchas:** NUNCA desligar `ib-altdata-backup.timer` antes de confirmar que o backup mais recente
está mesmo offsite e íntegro — perder o único arquivo PIT existente seria irreversível e
destruiria o único ativo de dados que este projeto ainda produz de forma consistente.
