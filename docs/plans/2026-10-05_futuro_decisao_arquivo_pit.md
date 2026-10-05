# Futuro 1 — Decisão de negócio sobre o arquivo de dados PIT (2026-10-05)

**Gate de arranque:** só começa quando o Passo 4 do plano de fixes de 2026-10-05 estiver
respondido — verificar com:
```
grep -rl "arquivo PIT\|altdata.*decis" /home/servidor/.claude/projects/-home-servidor/memory/*.md | grep -v bak
```
Se não devolver nenhuma entrada posterior a 2026-10-05 com uma decisão explícita do José, este
plano NÃO deve arrancar — volta ao Passo 4 do plano de fixes.

## Contexto para o executor

O IB Bot guarda, desde 13 de julho de 2026, uma "fotografia" (PIT — point-in-time, ou seja: os
dados exatamente como estavam num certo dia, para nunca se poder usar informação que só apareceu
depois) diária de 11 fontes de dados públicas (políticos dos EUA, 13F de fundos, etc.) na tabela
`altdata_snapshots` do Postgres (container `ib_bot-db-1`). Em 2026-10-05: **932 linhas, 85 dias
distintos**, a crescer ~11 linhas/dia sozinho, sem intervenção humana. Isto já foi proposto como
possível produto vendável (plano Conductor `3702771c`, `superseded`, e o gate de "pronto para
decisão" já fechou em 2026-08-11 com o one-pager escrito) mas **nunca decidido** — já passaram
quase 2 meses de HOLD.

## Objetivo

Decidir, com o José, o destino deste arquivo: (a) vender/licenciar como produto de dados
(concorrente de Unusual Whales/Quiver), (b) arquivar e parar de o alimentar, (c) continuar a
acumular sem plano de uso definido, com data de reavaliação marcada (ex.: 3 meses).

## Passo 1 — Preparar a decisão com números concretos e atualizados

**Comandos exatos:**
```
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "select source, count(*), min(captured_at), max(captured_at) from altdata_snapshots group by source order by count desc;"
du -sh /home/servidor/Desktop/cursor-projects/ib_bot/backups/altdata_snapshots/
cat /home/servidor/Desktop/cursor-projects/ib_bot/docs/altdata_b2b_one_pager_draft.md
```
Atualiza o one-pager existente (não o reescrevas do zero) com os números de hoje: quantas
fontes, quantos dias, tamanho do arquivo offsite, e confirma se o desenho técnico do plano
`3702771c` ainda é válido 5 meses depois (concorrentes, preços de mercado de dados alternativos
podem ter mudado).

**Oracle de aceitação:** `docs/altdata_b2b_one_pager_draft.md` tem uma secção "Atualizado em
2026-10-0X" com os números novos acima.

## Passo 2 — Levar a decisão ao José

Usa `request_user_approval` com as 3 opções (a/b/c) acima e o one-pager atualizado do Passo 1
anexado. Regista a resposta em memória com data.

**Oracle de aceitação:** entrada de memória nova com a decisão, e (se a resposta for (a) ou (b))
um novo plano Conductor `draft`/`approved` para o slug `ib_bot` com essa decisão como objetivo. Se
a resposta for (c), regista a data de reavaliação marcada e arma um `job` Conductor
(`conductor jobs add --mode run_cmd ...` com `wake_kind=time`) para essa data, não confies em
"lembrar-se sozinho".

**Rollback:** nenhum (decisão de negócio, não uma alteração técnica).

**Gotchas:** não relançar a proposta antiga do plano `3702771c` sem reler primeiro se as
suposições de mercado (concorrentes, preços) ainda são válidas — o mercado de dados alternativos
move-se rápido, e já passaram 5 meses desde o desenho original.
