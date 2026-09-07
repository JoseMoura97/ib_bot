# Plano Futuro 1/3 — Decisão de negócio sobre o arquivo PIT (2026-09-07)

**Gate de arranque:** só começa quando o Passo 0 do `2026-09-07_plano_fixes.md` estiver verde —
verificar com:
```bash
ls -la /home/servidor/.claude/projects/-home-servidor/memory/ | grep -i "ib_bot.*2026-09\|ib_bot.*decisao"
```
Se não existir um ficheiro de memória com a resposta do José sobre o destino do arquivo PIT, **não
avances** — volta a apresentar a pergunta do passo 0, não presumas uma direção.

## Contexto para o executor

O arquivo "ponto-no-tempo" (PIT — *point-in-time*, uma "fotografia" diária de dados públicos que
nunca muda depois de guardada) cresce ~11 linhas/dia desde 13 de julho de 2026, sem que exista
uma decisão de negócio sobre o que fazer com ele. Está em `altdata_snapshots` (Postgres, container
`ib_bot-db-1`) e é replicado para fora da máquina por `ib-altdata-backup.timer` (commits
`backup(altdata): PIT table ...` neste repo). Em 2026-09-07 tinha 625 linhas, 57 dias distintos,
11 fontes de dados (CFTC, FINRA, FRED, House disclosure ×2, SEC ×2, Nasdaq, USAspending, 13F
Berkshire, 13F Scion). Isto tem valor real (não se pode reconstruir um dia passado depois de a
fonte mudar), mas também custo real (armazenamento crescente, engenharia de manutenção, atenção
do José em cada audit).

Três caminhos possíveis, cada um com objetivo e critério de sucesso diferentes — **este plano só
executa o caminho que o José escolher no passo 0 do plano de fixes**, não decide por ele.

## Fase A — Se a decisão for "vender/licenciar dados" (produto B2B tipo Unusual Whales/Quiver)

**Objetivo:** validar se há procura real ANTES de construir mais nada — o plano Conductor
`3702771c` ("ib_bot → Alt-Data Product") já foi tentado e ficou `superseded`; não repetir sem
evidência nova de procura.

**Comandos:**
```bash
# 1. Rever porque é que 3702771c falhou/foi superseded antes de tentar de novo:
psql -U servidor -d conductor -c "SELECT jsonb_pretty(phases) FROM project_plans WHERE id='3702771c-9af4-4309-a08b-2714c7d5921e';" | less
# 2. Se a razão anterior já não se aplica (ex.: novo canal de distribuição identificado pelo
#    José), documentar a validação de procura ANTES de qualquer trabalho de engenharia:
#    - Pelo menos 3 conversas/sinais concretos de compradores potenciais, não suposição.
```

**Oráculo de aceitação:** existe um documento (`docs/business/pit_demand_validation.md` ou
similar) com pelo menos 3 evidências concretas de procura antes de qualquer código de produto
novo ser escrito. Sem isso, este ramo do plano fica `blocked` — não construir.

**Rollback:** N/A (fase de validação, não constrói nada).

**Gotchas:** não repetir o erro documentado no audit de 2026-08-31 ("HOLD explícito: NÃO reabrir,
NÃO voltar a cardar, NÃO fazer qualquer contacto comercial" no plano `e36e04ec`, fase
`a1_altdata_b2b`) sem uma decisão NOVA e explícita do José que substitua esse HOLD.

## Fase B — Se a decisão for "arquivar e desligar" (encerramento ordenado)

**Objetivo:** parar de gastar recursos num ativo sem destino, preservando o histórico já
capturado (não apagar dados — só parar de os continuar a criar).

**Comandos:**
```bash
# 1. Confirmar quantos dias/linhas existem antes de qualquer mudança (para o registo):
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -t -A -c "select count(*), count(distinct captured_at::date), min(captured_at), max(captured_at) from altdata_snapshots"

# 2. Fazer um último backup manual completo antes de desligar o timer automático:
docker exec ib_bot-db-1 pg_dump -U ibbot -d ibbot -t altdata_snapshots -F c -f /tmp/altdata_final_archive_$(date +%Y%m%dT%H%M%SZ).dump
docker cp ib_bot-db-1:/tmp/altdata_final_archive_*.dump /home/servidor/Desktop/cursor-projects/ib_bot/backups/

# 3. Desligar os timers (READ-ONLY do audit não se aplica aqui — é o plano futuro executado só
#    após decisão explícita do José no passo 0):
sudo systemctl disable --now ib-altdata-backup.timer ib-altdata-qa.timer
# Nota: desligar exige sudo — este comando fica fora do que um agente pode correr sozinho sem
# elevação; se a sessão não tiver sudo, reportar ao José para ele confirmar/correr.
```

**Oráculo de aceitação:**
```bash
systemctl is-active ib-altdata-backup.timer ib-altdata-qa.timer
# esperado: "inactive" para os dois
ls -la /home/servidor/Desktop/cursor-projects/ib_bot/backups/ | grep altdata_final_archive
# esperado: ficheiro presente, com tamanho > 0
```

**Rollback:** `sudo systemctl enable --now ib-altdata-backup.timer ib-altdata-qa.timer` — os dados
já capturados na tabela nunca são apagados por este plano (é *append-only* por desenho, gatilho
`altdata_snapshots_reject_mutation` confirmado ativo em auditorias anteriores).

**Gotchas:** não desligar `ib-backtests.timer` neste passo — é uma decisão separada (o backtest
semanal serve para revalidar as 56 estratégias periodicamente mesmo sem o arquivo a crescer).

## Fase C — Se a decisão for "continuar a acumular sem mudança" (status quo consciente)

**Objetivo:** só documentar explicitamente que esta é uma escolha ativa, não uma omissão, para
que a próxima auditoria não trate isto como um finding não resolvido pela 5ª vez.

**Comandos:** nenhum — só atualizar o audit seguinte para citar a decisão registada no passo 0
como "decisão José 2026-09-07: manter status quo, reavaliar em <data>" em vez de repetir o
finding como se fosse novo.

**Oráculo de aceitação:** o próximo audit (`docs/audits/2026-09-1X_audit_profundo.md` ou
seguinte) cita esta decisão explicitamente na secção de findings, com data e razão, em vez de
listar "arquivo sem destino" como CRÍTICO/ALTO outra vez.
