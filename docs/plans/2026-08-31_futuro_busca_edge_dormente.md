# Plano Futuro — Busca de Edge Dormente nas ~30 Estratégias 13F Nunca Testadas (2026-08-31)

## Gate de arranque (OBRIGATÓRIO — não começar sem isto)

**Só começa quando o José escolher explicitamente a opção 2 ("testar as ~30 estratégias 13F
dormentes") no Passo 0/1 do `docs/plans/2026-08-31_plano_fixes.md`.**

Verificar com:
```bash
grep -rl "ib_bot" /home/servidor/.claude/projects/-home-servidor/memory/ | xargs grep -l "opção 2\|edge dormente\|13F.*dormente" 2>/dev/null
psql conductor -c "SELECT id,status,metadata FROM project_plans WHERE slug='ib_bot' AND id='e36e04ec-de9c-438f-b0e5-434dfa391154'"
```
Se nenhum dos dois comandos mostrar evidência de decisão explícita do José por esta opção, **NÃO
avançar** — voltar ao plano de fixes e resolver o Passo 0 primeiro.

## Contexto para o executor

O motor de backtest do ib_bot testou 56 estratégias, mas o audit v4 (memória
`project_ib_bot_audit.md`, AUTORITATIVA, 2026-05) descobriu que o teste original tinha um viés:
media alfa (ganho por competência) misturado com beta (ganho só por o mercado subir). Depois de
corrigir isso e aplicar o Deflated Sharpe Ratio (teste que pune ter tentado 56 ideias — quanto
mais tentas, maior a hipótese de uma parecer boa só por sorte), **nenhuma das 56 passou**.

Só que essas 56 eram as estratégias "populares" (seguir compras do Congresso, seguir Michael
Burry, seguir Warren Buffett). Existe um catálogo maior de ~30 variações baseadas em filings 13F
(o relatório trimestral que fundos grandes são obrigados a publicar) que nunca foram corridas
pelo motor de backtest corrigido/deflacionado — só pelo motor v1 original com o viés já
identificado. Esta é a única categoria de estratégias do catálogo do ib_bot que ainda não recebeu
um veredito final com a metodologia correta.

**Paths absolutos:**
- Repo: `/home/servidor/Desktop/cursor-projects/ib_bot`
- Motor de backtest corrigido: `backend/app/services/backtest_engine.py` (ou `backtest_engine.py`
  na raiz, dependendo de qual está a ser usado pelo timer `ib-backtests.service` — confirmar com
  `systemctl cat ib-backtests.service` antes de editar nada).
- Catálogo de estratégias: procurar `grep -rl "13F\|thirteen_f" backend/app/strategies/` ou
  equivalente.

**Credenciais:** nenhuma nova necessária — os filings 13F já estão no arquivo PIT
(`altdata_snapshots`, fontes `sec_13f_berkshire_hathaway`, `sec_13f_scion_asset_management`) e/ou
via fonte SEC EDGAR pública já usada pelo coletor `altdata_snapshot_daily_task`.

**Regras:**
- Isto é 100% backtest histórico — zero risco de dinheiro real, zero necessidade de aprovação de
  money-path.
- Compute pesado (correr as ~30 estratégias × múltiplos anos de histórico) DEVE ir via `runjob`
  (ver regra global do José) — não correr como processo solto.
- Aplicar a MESMA metodologia do audit v4 desde o início (Deflated Sharpe Ratio, split
  treino/holdout, teste de decaimento de sinal pós-2023) — não repetir o erro do motor v1.

---

## Passo 1 — Levantar o catálogo real de estratégias 13F nunca testadas

**Objetivo:** confirmar exatamente quantas e quais estratégias 13F existem no catálogo mas nunca
passaram pelo motor v4/deflacionado.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
grep -rln "13f\|thirteen_f\|ThirteenF" backend/app/strategies/ backend/app/services/ 2>/dev/null
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT id, name, status FROM strategies WHERE name ILIKE '%13f%' OR name ILIKE '%13-f%' ORDER BY name;"
```

**Oráculo de aceitação:** uma lista concreta (nome + id) de N estratégias 13F, com uma coluna
"testada com motor deflacionado? sim/não" preenchida a partir de `strategy_results`/
`portfolio_results` cruzado com a data do audit v4 (2026-05).

**Rollback:** não aplicável (é levantamento, read-only).

**Gotchas:** não confundir "existe no catálogo" com "corre no timer semanal" — algumas
estratégias podem estar desativadas (`status != 'active'`) por razões não relacionadas com edge
(ex.: fonte de dados descontinuada).

---

## Passo 2 — Correr o motor de backtest deflacionado nas estratégias identificadas

**Objetivo:** aplicar a mesma vara de medir do audit v4 (que reprovou as 56 originais) às ~30
estratégias 13F nunca testadas.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
runjob --mem 8G --cpu 4 --name ib-bot-13f-backtest -- python3 backtest_engine.py --strategies-file <lista_do_passo_1.txt> --deflated-sharpe --holdout-split 0.3 --output docs/audits/2026-08-31_13f_backtest_results.json
```
(Ajustar os argumentos exatos ao CLI real do `backtest_engine.py` — confirmar com
`python3 backtest_engine.py --help` antes de correr a versão final.)

**Oráculo de aceitação:** ficheiro `docs/audits/2026-08-31_13f_backtest_results.json` (ou nome
equivalente) existe, e contém, para cada estratégia testada, pelo menos: Sharpe Ratio bruto,
Deflated Sharpe Ratio, p-value, e resultado holdout (não só treino).

**Rollback:** apagar o ficheiro de resultados — não há mutação de estado do sistema.

**Gotchas:** usar `runjob` mesmo que pareça rápido — 30 estratégias × vários anos de dados
históricos pode consumir RAM significativa se o motor carregar tudo em memória de uma vez (já
houve 2 kills por `systemd-oomd` no backtest semanal em julho — ver auditoria 2026-08-24, marco
07-18/19).

---

## Passo 3 — Reportar veredito final e decidir próximo passo

**Objetivo:** fechar o loop com um veredito claro: alguma das 13F sobrevive ao Deflated Sharpe
Ratio + holdout, ou confirma-se o padrão de "zero edge robusto" das outras 3 tentativas
(56 originais, PEAD, earnings-vol)?

**Comandos exatos:** nenhum novo — é síntese do Passo 2.

**Oráculo de aceitação:** um documento curto (`docs/audits/2026-08-31_13f_veredito.md` ou anexo
à próxima auditoria) com a conclusão em 1 parágrafo + tabela de resultados, e uma recomendação
explícita: (a) alguma estratégia 13F sobrevive → considerar paper-trading real dela por 60-90
dias antes de qualquer capital real; (b) nenhuma sobrevive → esta foi a 4ª tentativa
independente de encontrar edge no ib_bot, forte sinal para avançar para
`docs/plans/2026-08-31_futuro_encerramento_ordenado.md`.

**Rollback:** não aplicável.

**Gotchas:** não deixar este passo pendurado como "análise em curso" para sempre — dar um prazo
de 1 sessão de trabalho entre o Passo 2 e o Passo 3; se o resultado for ambíguo, tratar como
"não sobreviveu" (o histórico do projeto mostra 3/3 tentativas anteriores a falharem sob esta
mesma vara de medir — o prior é fortemente contra encontrar edge).
