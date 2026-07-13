# Plano futuro — Arquivo point-in-time de alt-data → caminho de licenciamento B2B — 2026-07-12

**GATE DE ARRANQUE**: só começa quando o Passo 3 do plano de fixes estiver verde (o arquivo
diário `altdata_snapshots` a crescer). Verificar com:
`docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc "SELECT count(DISTINCT captured_at::date) FROM altdata_snapshots"`
→ deve devolver ≥ 14 (duas semanas de vintages) antes de gastar 1 minuto neste plano.

## Contexto para o executor

- **Porquê isto**: o audit v4 do ib_bot (2026-05-26, AUTHORITATIVE — ver memória
  `project_ib_bot_audit.md`) concluiu que as estratégias não têm alpha vendável, mas que há
  valor real no MOTOR e nos DADOS: a Quiver Quantitative fatura ~$2.5M/ano a licenciar
  exatamente os mesmos dados públicos gratuitos; a Unusual Whales recebe royalties de ETFs
  com ~$307M under management. O ativo que nós podemos ter e eles não replicam é um **arquivo
  point-in-time** (cada dia guardado como era nesse dia — permite backtests honestos, que é
  o que um comprador institucional exige).
- **O que já existe**: coletores gratuitos funcionais no repo
  `/home/servidor/Desktop/cursor-projects/ib_bot` (EDGAR 13F, FINRA short, CFTC COT,
  USASpending, congress trades, Form 4, extração LLM de financial disclosures anuais);
  tabela `altdata_snapshots` na DB `ib_bot-db-1` (a encher desde o fix). Fragilidade
  conhecida: o scraper Capitol Trades é SPOF (ponto único de falha) para dados de políticos.
- **Regras**: nada de dinheiro sem `request_user_approval`; commits no mesmo turno; qualquer
  scraping respeita rate limits (EDGAR exige User-Agent identificado).

### Passo 1 — Robustecer o arquivo (qualidade de dado vendável)

**Objetivo**: o arquivo diário passa a ter garantias: cobertura por fonte, checksum, e um
teste de reconstrução ("consigo reconstruir o dia D só com vintages ≤ D").

**Comandos**:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# criar script de QA diário que valida o snapshot do dia
cat > scripts/qa_altdata_snapshots.py <<'EOF'
# le altdata_snapshots do dia, verifica: todas as fontes esperadas presentes,
# payload nao-vazio, row count vs media movel 7d (alerta se cair >50%)
EOF
# implementar de verdade + agendar no timer do passo 3 do plano de fixes (correr apos o snapshot)
git add scripts/ && git commit -m "feat(altdata): QA diario do arquivo point-in-time"
```

**Oracle de aceitação**: 7 dias seguidos com QA verde:
`docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc "SELECT captured_at::date, count(*) FROM altdata_snapshots GROUP BY 1 ORDER BY 1 DESC LIMIT 7"`
→ 7 dias consecutivos, contagens estáveis; e o log do QA sem alertas.

**Rollback**: desligar o QA (o arquivo continua).

**Gotchas**: falhas de fonte upstream (site em baixo) NÃO devem matar o snapshot inteiro —
gravar as fontes que responderam e marcar as falhadas.

### Passo 2 — Prova de valor: 1 dataset "licenciável" empacotado

**Objetivo**: transformar 1 fonte (sugestão: congressional trades com timestamps de
disclosure point-in-time) num dataset com README, dicionário de campos, e amostra de 30 dias
— o formato que um comprador (fundo/fintech/emissor de ETF) espera ver.

**Comandos**: exportar de `altdata_snapshots` para parquet particionado por dia +
`DATASHEET.md` (fontes, latência, lacunas conhecidas, licença dos dados de origem — dados
públicos do governo dos EUA). Commit no repo.

**Oracle de aceitação**: `ls exports/congress_pit/` mostra ≥30 partições diárias + DATASHEET;
um `pd.read_parquet` do conjunto abre limpo e um spot-check de 3 trades conhecidos bate certo
com o site oficial de disclosures.

**Rollback**: n/a.

**Gotchas**: verificação legal ligeira antes de qualquer contacto comercial (dados públicos
podem ser redistribuídos, mas dados da Quiver paga NÃO — o dataset tem de vir 100% das
fontes livres; o audit v2 mapeou quais são).

### Passo 3 — Decisão comercial (gated a José)

**Objetivo**: com ≥60 dias de arquivo + 1 dataset empacotado, José decide se contacta
potenciais compradores (white-label ETF: Tidal/ETF Architect; fintechs; fundos). ACV
estimado no audit v3/v4: $50-120k/deal. Este passo é 100% do José — o executor só prepara o
material (one-pager com o que o arquivo tem que a concorrência não tem).

**Oracle de aceitação**: one-pager entregue a José (via canal normal, NÃO Telegram-spam) +
resposta dele registada no plano do conductor.

**Rollback**: n/a.

**Gotchas**: não prometer histórico que não temos — o nosso arquivo point-in-time começa em
2026-07 (data do fix); o que vendemos é o COMPROMISSO de vintages + o motor de reconstrução
histórica via EDGAR (que é point-in-time por natureza, filed_dates).
