# Plano Futuro 1 — Licenciamento B2B do arquivo de dados (alt-data)

## Gate de arranque (obrigatório)

**Só começar quando o Passo 1 do `docs/plans/2026-08-24_plano_fixes.md` estiver concluído E o
José tiver escolhido explicitamente a opção 1 (continuar a acumular para licenciar).** Verificar
com:
```bash
psql conductor -c "SELECT metadata->>'decisao_continuidade' FROM project_plans WHERE id='e36e04ec-de9c-438f-b0e5-434dfa391154'"
```
Tem de conter "licenciamento" ou equivalente registado pelo José. Se devolver vazio/NULL, não
avançar — voltar ao plano de fixes, Passo 1.

## Contexto para o executor

A conclusão mais forte e repetida em 4 rondas de auditoria (memória `project_ib_bot_audit`,
v1→v4, todas confirmando a mesma coisa) é que **o valor real do IB Bot não está nas 56
estratégias de trading (sem edge robusto), mas no arquivo de dados alternativos ponto-no-tempo
(PIT)** que está a ser construído todos os dias desde 2026-07-13. A v4 (autoritativa) diz
textualmente: *"HIGHEST-ROI ACTION: start persisting daily point-in-time snapshots NOW — engine
is live-pull, stores no vintages; the accumulating archive is the only compounding,
un-replicable moat."* Isso já está feito e a crescer sozinho: **471 registos, 43 dias, 11
fontes, a 2026-08-24** (verificar contagem atual antes de agir — cresce ~11/dia).

Os entregáveis técnicos do plano `e36e04ec` fase `a1_altdata_b2b` já existem: exports em
`exports/congress_pit/` (30 partições, 51.967 linhas de índice, SHA-256 verificado), QA 11/11
verde, e um rascunho de one-pager em `docs/altdata_b2b_one_pager_draft.md` (factualmente correto
e limitado: é um arquivo de ÍNDICE de filings, não um feed trade-level). **Este plano parte
desse trabalho já feito — não repetir a extração, só a comercialização.**

Concorrentes de referência (da mesma auditoria): Quiver Quantitative (750k utilizadores, ~5k
pagos, rentável a licenciar os mesmos dados gratuitos); Unusual Whales (royalties sobre ~$307M
em AUM de ETFs NANC/KRUZ). Um único acordo de licenciamento de marca/índice a um emissor de ETF
branco (Tidal/ETF Architect) vale $50-120k ACV — mais do que 3.000 subscritores individuais.

## Passo 1 — Atualizar o dossier de cobertura com os números de hoje

**Objetivo:** o one-pager existente (`docs/altdata_b2b_one_pager_draft.md`) foi escrito com os
números de 2026-08-11 (328 linhas). Antes de qualquer conversa comercial, refrescar com os
números atuais.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "
  SELECT source, count(*) as dias, min(as_of_date), max(as_of_date)
  FROM altdata_snapshots GROUP BY source ORDER BY dias DESC"
cat docs/altdata_b2b_one_pager_draft.md
```

**Oráculo de aceitação:** novo bloco no one-pager (ou ficheiro `reports/licensing_dossier_<data>.md`)
com a tabela fonte×dias atualizada e a cobertura MEDIDA (não declarada) — reutilizar o mesmo
método de `docs/altdata_restore_drill.md` (contagem por dia, dias fora de {9,11} explicitados).

**Rollback:** nenhum (read-only + acrescenta ficheiro).

**Gotchas:** usar SEMPRE a cobertura MEDIDA, nunca a declarada sem verificar — o gate H5 do plano
de hardening (já `done`) existe precisamente para impedir sobre-declaração; não regredir essa
disciplina neste plano comercial.

## Passo 2 — Pesquisa de mercado + lista de 5-10 compradores potenciais

**Objetivo:** identificar quem pagaria por este arquivo (fundos pequenos, newsletters
financeiras, emissores de ETF, plataformas de screening).

**Comandos:** usar a skill `search` (pesquisa web adversarial) com a query "quem licencia dados
de 13F/congressional trading para fintechs pequenas 2026" e "preços de licenciamento de dados
alternativos B2B fintech".

**Oráculo de aceitação:** um ficheiro `reports/licensing_target_list_<data>.md` com pelo menos 5
potenciais compradores, cada um com: nome, o que compram hoje (concorrente atual), contacto
público, faixa de preço estimada.

**Rollback:** nenhum.

**Gotchas:** **não contactar ninguém sem o José aprovar explicitamente cada contacto** — a nota
congelada da fase `a1_altdata_b2b` no Conductor é explícita: "NÃO fazer qualquer contacto
comercial" enquanto a decisão de negócio estiver em HOLD. Este passo é só pesquisa/preparação.

## Passo 3 — Protótipo de API de acesso ao arquivo (read-only, sem custo)

**Objetivo:** expor um endpoint mínimo (autenticado, rate-limited) que sirva o arquivo PIT a um
potencial cliente-piloto, sem gastar dinheiro em infraestrutura nova.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
grep -rn "alt-data\|altdata" backend/app/api/routes/ | grep -i "route\|router" | head -20
# confirmar se a rota /alt-data da branch frontend-v2 (commit 7034b54, ib_bot-v2) já cobre isto
```

**Oráculo de aceitação:** ou (a) confirma-se que a rota `/alt-data` já existe e só falta expô-la
na branch `main`, ou (b) documenta-se exatamente o que falta construir, sem construir nada ainda
— este passo termina em decisão + plano técnico, não em código novo, até haver um cliente-piloto
identificado no Passo 2 E aprovação explícita do José para contactá-lo.

**Rollback:** nenhum.

**Gotchas:** qualquer decisão de gastar dinheiro (hosting extra, subscrição de dados pagos para
enriquecer a oferta) precisa aprovação explícita do José — money-path gated.
