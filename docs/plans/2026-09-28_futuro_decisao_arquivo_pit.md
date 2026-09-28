# Futuro 1 — Decisão de negócio sobre o arquivo de dados PIT (2026-09-28)

**Gate de arranque:** só começa depois do Passo 0 do plano de fixes de 2026-09-28 estar
respondido — verificar com:
```
grep -rl "arquivo PIT\|altdata.*decis" /home/servidor/.claude/projects/-home-servidor/memory/*.md | grep -v bak
```
Se não devolver nenhuma entrada recente (posterior a 2026-09-28) com uma decisão explícita do
José, este plano NÃO deve arrancar — volta ao Passo 0.

## Contexto para o executor

O IB Bot guarda, desde 13 de julho de 2026, uma "fotografia" (PIT — point-in-time) diária de 11
fontes de dados públicas (políticos dos EUA, 13F de fundos, etc.) na tabela `altdata_snapshots`
do Postgres (`ib_bot-db-1`). Em 2026-09-28: **855 linhas, 78 dias distintos**, a crescer ~11
linhas/dia sozinho. Isto já foi proposto como possível produto vendável (achado das auditorias de
maio: "ib_bot → Alt-Data Product", plano Conductor `3702771c`, `superseded`) mas nunca decidido.

## Objetivo

Decidir, com o José, o destino deste arquivo: (a) vender/licenciar como produto de dados
(concorrente de Unusual Whales/Quiver), (b) arquivar e parar de o alimentar, (c) continuar a
acumular sem plano de uso definido, com data de reavaliação marcada.

## Passo 1 — Preparar a decisão com números concretos

**Comandos exatos:**
```
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "select source, count(*), min(captured_at), max(captured_at) from altdata_snapshots group by source order by count desc;"
du -sh /home/servidor/Desktop/cursor-projects/ib_bot/backups/altdata_snapshots/
```
Junta isto a um resumo de 1 página: quantas fontes, quantos dias, tamanho do arquivo, e uma
estimativa de esforço para expor via API paga (o plano `3702771c` já tem o desenho técnico, só
falta reler `docs/altdata_b2b_one_pager_draft.md` no repositório e confirmar se ainda é válido).

**Oracle de aceitação:** documento de 1 página existe em
`docs/plans/2026-09-28_futuro_decisao_arquivo_pit_resumo.md` com os números acima.

## Passo 2 — Levar a decisão ao José

Usa `request_user_approval` com as 3 opções (a/b/c) acima e o resumo do Passo 1 anexado. Regista
a resposta em memória com data.

**Oracle de aceitação:** entrada de memória nova com a decisão, e status deste plano atualizado
no Conductor (`draft` → `done` ou `superseded` conforme a decisão).

**Rollback:** nenhum (decisão de negócio, não uma alteração técnica).

**Gotchas:** não relançar a proposta antiga do plano `3702771c` sem reler primeiro se as
suposições de mercado (concorrentes, preços) ainda são válidas 4 meses depois — o mercado de
dados alternativos move-se rápido.
