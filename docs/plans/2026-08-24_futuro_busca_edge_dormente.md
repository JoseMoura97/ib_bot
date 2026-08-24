# Plano Futuro 2 — Testar as ~30 estratégias 13F "dormentes" nunca avaliadas

## Gate de arranque (obrigatório)

**Só começar quando o Passo 1 do `docs/plans/2026-08-24_plano_fixes.md` estiver concluído E o
José tiver escolhido explicitamente a opção 2 (redirecionar esforço para busca de edge).**
Verificar com:
```bash
psql conductor -c "SELECT metadata->>'decisao_continuidade' FROM project_plans WHERE id='e36e04ec-de9c-438f-b0e5-434dfa391154'"
```
Tem de conter "busca_edge" ou equivalente registado pelo José. Se não, não avançar.

## Contexto para o executor

A auditoria v4 (memória `project_ib_bot_audit`, autoritativa, 2026-05-26) caçou 6 clones 13F
famosos (Druckenmiller, Tepper, Klarman, Buffett, Loeb, Tiger Global) com o motor deflacionado
market-neutral e NENHUM passou a fasquia de sorte (~0.8-1.06 Sharpe esperado por acaso em 36
testes); o melhor foi Druckenmiller com 0.41. Mas essa caça cobriu só 6 dos **~30 clones que
existem no código (`quiver_strategy_rules.py`) mas nunca foram corridos no registo oficial
`run_all_backtests`**. Este plano fecha esse buraco: testar os ~24 que faltam, com o MESMO
rigor estatístico (Deflated Sharpe + split de decaimento + teste de fragilidade), para não
repetir o erro do audit v1-v3 (achar uma estratégia "boa" sem corrigir para múltiplos testes).

**Nota de disciplina (reforçada pela auditoria de 2026-08-24):** três buscas de edge
independentes neste ecossistema (56 estratégias do ib_bot, PEAD no repo `trading`, earnings-vol
0006) morreram todas com a mesma disciplina estatística — deflação, split fora-da-amostra, teste
de fragilidade. Este plano não é uma exceção "porque desta vez pode ser diferente" — é aplicar a
MESMA fasquia rigorosa às ~24 estratégias que ainda não a passaram por nunca terem sido testadas
(não por já terem passado num teste mais fraco).

## Passo 1 — Listar os clones nunca testados

**Objetivo:** ter a lista exata do que falta, não uma estimativa.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
find . -iname "*strategy_rules*" -not -path "*/node_modules/*"
# usar o path real encontrado acima no lugar de quiver_strategy_rules abaixo
python3 -c "
from quiver_strategy_rules import STRATEGY_RULES  # ajustar import conforme o módulo real
print(len(STRATEGY_RULES))
for k in STRATEGY_RULES: print(k)
" 2>&1 | tee /tmp/all_strategies.txt
grep -oE '\"[A-Za-z_ ]+\"' backend/*/run_all_backtests.py 2>/dev/null | sort -u | tee /tmp/tested_strategies.txt
diff /tmp/all_strategies.txt /tmp/tested_strategies.txt
```

**Oráculo de aceitação:** lista final em `reports/dormant_clones_list_<data>.md` com nome exato
de cada estratégia nunca corrida, confirmado por diff, não por memória.

**Rollback:** nenhum (read-only).

**Gotchas:** os nomes/paths exatos dos módulos podem ter mudado desde maio — confirmar com
`find . -iname "*strategy_rules*"` antes de assumir o caminho do comando acima (não copiar o
path cegamente).

## Passo 2 — Correr o motor deflacionado sobre os clones em falta

**Objetivo:** aplicar exatamente o mesmo standard estatístico que já matou as outras 56 (e os 6
clones já testados) — Deflated Sharpe Ratio, split de decaimento em fev-2023, teste de
fragilidade (top-2-meses % do ganho).

**Comandos exatos (adaptar ao nome real do runner deflacionado usado no audit v4):**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
source .venv/bin/activate 2>/dev/null || python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -q
python3 -c "
from rebalancing_backtest_engine import RebalancingBacktestEngine
engine = RebalancingBacktestEngine(quiver_api_key='', price_source='yfinance')
for name in open('/tmp/dormant_only.txt'):
    name = name.strip()
    result = engine.run_rebalancing_backtest(name, '2018-01-01', '2026-08-24', alpha_only=True)
    print(name, result.get('sharpe_ratio'), result.get('cagr'), result.get('alpha'), result.get('beta'))
" | tee reports/dormant_clones_deflated_<data>.txt
```

**Oráculo de aceitação:** ficheiro `reports/dormant_clones_deflated_<data>.txt` com uma linha
por estratégia testada, Sharpe alpha-only calculado; nenhuma conclusão de "tem edge" sem passar
também pelo Deflated Sharpe (recalcular com o número real de testes = 56 + N novos) e pelo split
de decaimento fev-2023.

**Rollback:** nenhum (é um script de leitura/simulação, não escreve na produção).

**Gotchas:**
- Usar `runjob --mem 24G` se o backtest completo demorar mais que alguns minutos ou usar muita
  RAM — não correr solto (lição do incidente de OOM de 2026-07-19 no backtest semanal).
- **NÃO declarar "achei edge" com um único Sharpe bruto.** Qualquer sobrevivente tem de passar:
  (a) Deflated Sharpe > fasquia esperada por acaso para o número TOTAL de testes já feitos neste
  projeto (~56+N, não só os N novos); (b) não decair depois do split fev-2023; (c) não depender
  de 1-2 meses de sorte (top-2-meses < 50% do ganho total).

## Passo 3 — Se (e só se) sobreviver algo ao Passo 2, paper-trade 3-6 meses antes de qualquer decisão de capital

**Objetivo:** nunca ir de "backtest limpo" direto para dinheiro real — replicar a disciplina já
usada no estudo earnings-vol/0006 (que morreu no gate de paper trading, não no backtest).

**Comandos exatos:** adicionar a estratégia sobrevivente ao Celery beat `paper_rebalance_daily`
existente (`backend/app/worker/celery_app.py`), NUNCA ao `live_rebalance_hourly`.

**Oráculo de aceitação:** 90 dias de `paper_snapshots` para a nova estratégia, com Profit Factor
> 1 tanto a preço-médio como a preço-de-execução-realista (mesmo gate usado para matar o 0006),
antes de sequer perguntar ao José sobre capital real.

**Rollback:** remover a entrada do `beat_schedule` e reiniciar `ib_bot-beat-1`.

**Gotchas:** qualquer proposta de avançar para capital real depois disto **exige aprovação
explícita do José e fica sujeita ao teto de EUR5 (ou o que ele definir) numa primeira execução
de teste** — nunca assumir autorização a partir de um backtest, por mais limpo que pareça.
