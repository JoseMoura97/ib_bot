# Plano Futuro 1 — Licenciamento B2B do arquivo de dados (alt-data)

## Gate de arranque (obrigatório)

**Só começar quando o Passo 1 E o Passo 2 do `docs/plans/undefined_plano_fixes.md` estiverem
verdes E o José tiver escolhido explicitamente esta opção (opção 1) na conversa do Passo 2.**
Verificar com:
```bash
bash /home/servidor/Desktop/cursor-projects/ib_bot/infra/scripts/verify_h3_soak.sh   # exit 0
psql conductor -c "SELECT metadata->>'decisao_continuidade' FROM project_plans WHERE id='04bf8af8-6614-4f12-9d57-772f7af2b67d'"   # tem de conter "licenciamento" ou equivalente registado pelo José
```
Se qualquer um destes falhar, não avançar — voltar ao plano de fixes.

## Contexto para o executor

A conclusão mais forte e repetida em 4 rondas de auditoria (memória `project_ib_bot_audit`,
v1→v4, todas confirmando a mesma coisa) é que **o valor real do IB Bot não está nas 56
estratégias de trading (sem edge robusto), mas no arquivo de dados alternativos ponto-no-tempo
(PIT)** que está a ser construído todos os dias desde 2026-07-13. A v4 (autoritativa) diz
textualmente: *"HIGHEST-ROI ACTION: start persisting daily point-in-time snapshots NOW — engine
is live-pull, stores no vintages; the accumulating archive is the only compounding,
un-replicable moat."* Isso já está feito (394 dias-fonte capturados a 2026-08-17). Este plano é
o passo seguinte: transformar esse arquivo num produto vendável.

Concorrentes de referência (da mesma auditoria): Quiver Quantitative (750k utilizadores, ~5k
pagos, rentável a licenciar os mesmos dados gratuitos); Unusual Whales (royalties sobre ~$307M
em AUM de ETFs NANC/KRUZ). Um único acordo de licenciamento de marca/índice a um emissor de ETF
branco (Tidal/ETF Architect) vale $50-120k ACV — mais do que 3.000 subscritores individuais.

## Passo 1 — Medir o valor real do arquivo acumulado hoje

**Objetivo:** produzir um dossier objetivo do que existe, para conversas comerciais.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "
  SELECT source, count(*) as dias, min(as_of_date), max(as_of_date)
  FROM altdata_snapshots GROUP BY source ORDER BY dias DESC"
cat reports/altdata_coverage_audit.json 2>/dev/null | head -50
```

**Oráculo de aceitação:** output colado num novo ficheiro
`reports/licensing_dossier_<data>.md` com a tabela fonte×dias e a cobertura medida (não
declarada) do gate H5.

**Rollback:** nenhum (read-only).

**Gotchas:** usar SEMPRE a cobertura MEDIDA (`coverage_measured` de
`reports/altdata_coverage_audit.json`), nunca a declarada sem verificar — o gate H5 do plano
de hardening existe precisamente para impedir sobre-declaração.

## Passo 2 — Pesquisa de mercado + lista de 5-10 compradores potenciais

**Objetivo:** identificar quem pagaria por este arquivo (fundos pequenos, newsletters
financeiras, emissores de ETF, plataformas de screening).

**Comandos:** usar a skill `search` (pesquisa web adversarial) com a query "quem licencia
dados de 13F/congressional trading para fintechs pequenas 2026" e "preços de licenciamento
de dados alternativos B2B fintech".

**Oráculo de aceitação:** um ficheiro `reports/licensing_target_list_<data>.md` com pelo menos
5 potenciais compradores, cada um com: nome, o que compram hoje (concorrente atual), contacto
público, faixa de preço estimada.

**Rollback:** nenhum.

**Gotchas:** não contactar ninguém sem o José aprovar — este passo é só pesquisa.

## Passo 3 — Protótipo de API de acesso ao arquivo (read-only, sem custo)

**Objetivo:** expor um endpoint mínimo (autenticado, rate-limited) que sirva o arquivo PIT a um
potencial cliente-piloto, sem gastar dinheiro em infraestrutura nova.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
grep -rn "alt-data\|altdata" backend/app/api/routes/ | grep -i "route\|router" | head -20
# confirmar se já existe uma rota /alt-data (memória menciona Phase 4 em ib_bot-v2: "/alt-data REST API")
```

**Oráculo de aceitação:** ou (a) confirma-se que a rota `/alt-data` da branch `frontend-v2`
(commit `7034b54`) já cobre isto e só falta expô-la na branch `main`, ou (b) documenta-se
exatamente o que falta construir, sem construir nada ainda — este passo termina em decisão +
plano técnico, não em código novo, até haver um cliente-piloto identificado no Passo 2.

**Rollback:** nenhum.

**Gotchas:** qualquer decisão de gastar dinheiro (hosting extra, subscrição de dados pagos para
enriquecer a oferta) precisa aprovação explícita do José — money-path gated.
