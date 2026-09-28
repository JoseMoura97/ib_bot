# Plano de fixes — IB Bot (2026-09-28)

## Contexto para o executor (lê isto antes de tocares em qualquer coisa)

Este ficheiro tem de dar a um modelo/agente FRACO, sem esta conversa, tudo o que precisa para
executar do zero.

**O que é o projeto:** o IB Bot é um robô de trading que testou 56 estratégias de investimento
(copiar políticos dos EUA, fundos como Warren Buffett, etc.) contra a corretora Interactive
Brokers (IB). Está **PAUSADO desde julho de 2026** ao nível de decisão de negócio: o motor de
execução real (que enviaria ordens verdadeiras) está desligado e deve continuar desligado. Só
duas coisas continuam a correr sozinhas todos os dias: (1) um arquivo de dados públicos
("point-in-time" / PIT) e (2) um simulador de "paper trading" (dinheiro falso) — que está
QUEBRADO, ver Passo 1.

**Paths importantes:**
- Repositório principal (onde os jobs agendados publicam): `/home/servidor/Desktop/cursor-projects/ib_bot`
  — **branch `main` só para jobs agendados**, nunca faças trabalho de teste/lab aqui diretamente
  (regra em `AGENTS.md` do próprio repo, imposta desde 2026-09-24 pelo commit `486b6e3`).
  Para qualquer investigação/edição, cria um worktree novo:
  `git -C /home/servidor/Desktop/cursor-projects/ib_bot worktree add -b <branch> <caminho-novo> main`
- Segundo worktree (frontend v2, Next.js, porta 3001): `/home/servidor/Desktop/cursor-projects/ib_bot-v2`
- Stack Docker Compose: dentro do repo principal, containers `ib_bot-api-1`, `ib_bot-worker-1`,
  `ib_bot-beat-1`, `ib_bot-db-1` (Postgres), `ib_bot-redis-1`, `ib_bot-web-1`, `ib_bot-nginx-1`.
- Base de dados: Postgres dentro do container `ib_bot-db-1`. Acesso:
  `docker exec -it ib_bot-db-1 psql -U ibbot -d ibbot`. **NÃO exposta ao host** (sem porta
  publicada) — só acessível via `docker exec`.
- Credenciais: `.env` na raiz do repo principal (não o leias/imprimas nesta tarefa a menos que
  seja estritamente necessário para o fix; nunca commites segredos). `QUIVER_API_KEY` controla se
  o rebalanceamento usa dados reais Quiver ou o fallback SPY-only.
- Conta pessoal do José na IB é lida via o conector MCP `Interactive Brokers (IBKR)` (ferramentas
  `get_account_summary`, `get_account_positions`, etc.) — **não tem nada a ver com o bot**, é a
  conta pessoal dele, gerida manualmente. Não mexer.

**Regras duras para quem executar este plano:**
- **Money-path (qualquer coisa que possa levar a uma ordem real):** exige aprovação síncrona do
  José via `request_user_approval` ANTES de qualquer alteração a `system/execution/`,
  `backend/app/api/routes/live.py`, ao gateway (`ibgateway.service`/`xvfb-ibgw.service`), ou a
  qualquer variável `LIVE_*`/`ENABLE_LIVE_TRADING`. Nenhum passo deste plano deveria precisar
  disto — se achares que precisas, PARA e pergunta primeiro.
  - Depois de qualquer teste manual do gateway, corre sempre
    `/home/servidor/Desktop/cursor-projects/ib_bot/scripts/verify_f1_dormencia_seletiva.sh` e
    confirma `RESULT PASS failures=0` antes de terminar a tarefa.
- **Commit no mesmo turn:** depois de qualquer alteração de código verificada, faz commit no
  mesmo turno (branch de trabalho, nunca direto em `main` do checkout principal — ver regra
  `AGENTS.md` acima). Integração em `main` é uma decisão deliberada, não automática.
- **`runjob` para trabalho pesado:** se algum passo abaixo precisar de correr o backtest completo
  das 56 estratégias (pesado, pode demorar >1h), usa
  `runjob --mem 8G --cpu 8 --name ib-bot-fix-verify -- <comando>`, nunca um processo solto.
- **Read-only na conta pessoal da IB e no gateway partilhado:** nenhum passo abaixo deve ligar
  `ibgateway`/`xvfb-ibgw`. Se precisares de investigar o motor de execução, usa mocks (como os
  testes existentes já fazem em `backend/tests/test_futures_contracts.py`).
- **Não dupliques planos:** antes de começares, confirma que não há já um plano `executing` para
  `ib_bot` no Conductor: `psql -U servidor -d conductor -c "SELECT id,status,title FROM
  project_plans WHERE slug='ib_bot' AND status IN ('draft','approved','executing','paused','gated');"`
  — se devolver alguma linha, PARA e avisa o José antes de continuar (pode já estar a ser feito).

---

## Passo 0 — Obter decisão explícita do José sobre a limpeza (7ª vez a pedir isto)

**Objetivo:** parar o ciclo de "auditoria escreve, ninguém decide" que já dura 7 auditorias
seguidas (17-08 a 28-09).

**Comandos:** nenhum comando técnico. Usa `request_user_approval` (ou o mecanismo síncrono
equivalente da sessão) com esta pergunta literal:

> "IB Bot: há 7 auditorias seguidas a recomendar (a) desligar um dos dois frontends duplicados
> (porta 3001 ou porta 8090), (b) limpar 31,5 GB de imagens Docker não usadas, (c) decidir o
> destino do arquivo de dados PIT (vender/arquivar/continuar sem plano). Queres que eu avance com
> (a) e (b) agora (baixo risco, reversível/grátis), e qual é a tua decisão sobre (c)?"

**Oracle de aceitação:** resposta do José registada em memória (ex.:
`/home/servidor/.claude/projects/-home-servidor/memory/project_ib_bot_cleanup_decision_<data>.md`)
com a data e o conteúdo exato da resposta. Se a resposta for "sim, avança com a/b", passa ao
Passo 2. Se for "não, deixa como está", regista isso como decisão explícita e a próxima auditoria
deixa de repetir o mesmo achado como CRÍTICO/ALTO (passa a informativo, "decisão tomada").

**Rollback:** nenhum (é só uma pergunta).

**Gotchas:** não avances para os Passos 2-3 sem esta resposta, exceto se o José já tiver
respondido a esta pergunta noutra conversa — confirma primeiro com
`grep -rl "frontend duplicado\|docker image prune\|arquivo PIT" /home/servidor/.claude/projects/-home-servidor/memory/*.md | grep -v bak`.

---

## Passo 1 — Diagnosticar e corrigir o bug `tuple index out of range` no paper rebalance

**Objetivo:** o `paper_rebalance_daily_task` falha silenciosamente todos os dias desde
2026-08-14 (45+ dias confirmados em 2026-09-28) para as duas contas de paper trading. Corrigir a
causa raiz e fazer o erro aparecer de forma visível se voltar a acontecer.

**Diagnóstico já feito nesta auditoria (2026-09-28), para poupar tempo:** chamar diretamente
`RebalancingBacktestEngine._generate_rebalance_events(strategy_name="Congress Buys", ...)` dentro
do container `ib_bot-worker-1` **não reproduz o erro** (54 eventos gerados com sucesso). Isto
significa que o bug provavelmente está: (a) numa estratégia específica das 9 configuradas nos
portefólios reais das duas contas (não "Congress Buys"), ou (b) na combinação de pesos de
múltiplas estratégias em `backend/app/api/routes/paper.py` linhas 264-312, ou (c) em
`fetch_prices`/`place_market_order` chamados depois (linhas 314-346, 374-390).

**Comandos exatos:**

1. Identificar as estratégias reais configuradas nos dois portefólios que falham (read-only):
   ```
   docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
     "select ps.portfolio_id, ps.strategy_name, ps.weight, ps.enabled \
      from portfolio_strategies ps \
      where ps.portfolio_id in ('7095ae3e-2633-49f4-b92c-094e2b4156aa','d2e87bea-0cd8-4175-82b0-3282ec8828dc') \
      order by ps.portfolio_id, ps.strategy_name;"
   ```
   (ajusta o nome da tabela se `\dt` mostrar um nome diferente — confirma com
   `docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "\dt" | grep -i strateg"`.)

2. Cria um worktree de trabalho isolado (nunca no checkout principal):
   ```
   git -C /home/servidor/Desktop/cursor-projects/ib_bot worktree add -b fix/paper-rebalance-tuple-bug \
     /home/servidor/ib-bot-fix-paper-rebalance-20260928 main
   ```

3. Dentro do worktree, escreve um script de reprodução isolado que chama
   `_generate_rebalance_events` para CADA UMA das estratégias reais identificadas no passo 1 (não
   só "Congress Buys"), com os mesmos parâmetros (`start`/`end`/`lookback_days_override=None`)
   que `backend/app/api/routes/paper.py:293-295` usa, e captura o traceback completo:
   ```
   docker exec ib_bot-worker-1 python3 -c "
   import traceback, sys, os
   sys.path.insert(0,'/app'); os.chdir('/app')
   from datetime import datetime, timedelta
   from rebalancing_backtest_engine import RebalancingBacktestEngine
   from app.core.config import settings
   bt = RebalancingBacktestEngine(quiver_api_key=settings.quiver_api_key, initial_capital=100000.0, transaction_cost_bps=0.0, price_source=settings.price_source)
   end = datetime.utcnow(); start = end - timedelta(days=365)
   for name in ['<lista das estratégias do passo 1>']:
       try:
           evs = bt._generate_rebalance_events(strategy_name=name, start=start, end=end, lookback_days_override=None)
           print('OK', name, len(evs))
       except Exception as e:
           print('FAIL', name); traceback.print_exc()
   "
   ```
   Isto é **read-only** (não escreve na base de dados) — seguro correr contra o container real.

4. Depois de identificar a estratégia/linha exata que falha, corrige a causa raiz no worktree
   (ex.: indexação defensiva, ou tratar lista vazia antes de indexar `[0]`/`[-1]`).

5. Adiciona um teste de regressão em `backend/tests/` que reproduz exatamente o cenário
   encontrado (dados vazios/malformados para essa estratégia) e falha ANTES do fix, passa DEPOIS.

6. Torna o erro visível se acontecer de novo: em `backend/app/worker/tasks.py:559-570`, troca
   `logger.warning(...)` por `logger.error(..., exc_info=True)` e garante que
   `PaperRebalanceLog.status="ERROR"` também dispara um alerta visível (ex.: mesma mecânica
   `conductor api-failure --notify-only` usada por `ib-altdata-qa-alert.service`).

**Oracle de aceitação:**
```
docker exec ib_bot-worker-1 python3 -m pytest /app/backend/tests/test_paper_rebalance_tuple_bug.py -v
```
→ `1 passed` (nome exato do ficheiro de teste fica ao critério de quem corrige; tem de reproduzir
o cenário real). Depois, no dia seguinte às 15:00 WEST, confirmar:
```
docker logs ib_bot-worker-1 --since 30h | grep paper_rebalance_daily
```
→ linha `orders=N` (N pode ser 0 se nada mudou, mas SEM `error=tuple index out of range`).

**Rollback:** `git worktree remove /home/servidor/ib-bot-fix-paper-rebalance-20260928 --force` e
não fazer merge do branch se o fix não passar nos testes.

**Gotchas:**
- Não mexer em `system/execution/` neste passo — é paper trading, não money-path, mas evita
  tocar em ficheiros partilhados desnecessariamente para não invalidar o hardening do plano
  `4c48535c`.
- As duas contas (1 e 2) podem ter causas raiz DIFERENTES — a conta 1 nunca teve nenhum trade
  (sempre $100k), a conta 2 tem histórico de maio. Testa as duas separadamente.
- `QUIVER_API_KEY` tem de estar definido no ambiente do container para reproduzir o caminho real
  (o fallback SPY-only não reproduz o bug, porque nem chama `_generate_rebalance_events`).

---

## Passo 2 — Consolidar os dois frontends duplicados (só depois de resposta do Passo 0)

**Objetivo:** parar de gastar recursos a servir a mesma informação em duas interfaces
(`localhost:3001` Next.js e `localhost:8090` nginx+React antigo).

**Comandos exatos** (assumindo que o José escolheu manter o `3001`, conforme recomendação das
auditorias anteriores — ajusta se a decisão do Passo 0 for diferente):
```
sudo systemctl status ib-bot-v2-frontend.service   # confirma que fica ativo, não tocar
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker compose stop web nginx
docker compose rm -f web nginx
```

**Oracle de aceitação:**
```
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001   # espera 307 (inalterado)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8090 || echo "connection refused (esperado)"
docker ps --filter name=ib_bot   # não deve listar mais ib_bot-web-1 nem ib_bot-nginx-1
```

**Rollback:** `docker compose up -d web nginx` (os containers voltam com a mesma imagem, nada foi
apagado, só parado/removido — a imagem continua em `docker images` a menos que já tenhas corrido
o Passo 3).

**Gotchas:** confirma primeiro que ninguém depende do `8090` externamente (nenhum link
partilhado, nenhum bookmark do José) — pergunta se não tiveres a certeza.

---

## Passo 3 — Limpar disco Docker e resíduos do repositório (só depois de resposta do Passo 0)

**Objetivo:** recuperar >30 GB de imagens Docker não usadas e limpar ficheiros órfãos na raiz do
repositório.

**Comandos exatos:**
```
docker system df   # confirma números antes (esperado: ~31.51GB reclamável)
docker image prune -a -f
docker system df   # confirma depois (esperado: perto de 0GB reclamável)

cd /home/servidor/Desktop/cursor-projects/ib_bot
git rm '$LOG' alembic_validation.db backtest_results_2026_05_12.json \
  backtest_results_corrected.json backtest_results_final.json \
  'docker-compose.prod.yml.bak.1778273314'
git mv docs/plans/undefined_futuro_busca_edge_dormente.md docs/plans/2026-08-17_futuro_busca_edge_dormente.md
git mv docs/plans/undefined_futuro_encerramento_ordenado.md docs/plans/2026-08-17_futuro_encerramento_ordenado.md
git mv docs/plans/undefined_futuro_licenciamento_dados.md docs/plans/2026-08-17_futuro_licenciamento_dados.md
git mv docs/plans/undefined_plano_fixes.md docs/plans/2026-08-17_plano_fixes.md
git commit -m "chore: remove ficheiros órfãos da raiz (achado #8/#10, 7 auditorias) e libertar imagens Docker não usadas"
```

**Oracle de aceitação:**
```
docker system df | grep Images   # RECLAIMABLE deve estar perto de 0B
ls /home/servidor/Desktop/cursor-projects/ib_bot/'$LOG' 2>&1   # "No such file or directory"
git -C /home/servidor/Desktop/cursor-projects/ib_bot log --oneline -1   # mostra o novo commit
```

**Rollback:** os ficheiros continuam no histórico git (`git log --all --oneline --
'$LOG'`); para os reaver, `git checkout <commit-anterior> -- '$LOG' ...`. As imagens Docker
removidas por `docker image prune` só voltam fazendo `docker compose build`/`docker compose pull`
de novo (não há rollback direto de imagens apagadas, mas nenhuma está em uso pelos containers
ativos — `docker system df` já confirmou 100% reclamável antes de apagar).

**Gotchas:** corre `docker image prune -a` (não só `prune` sem `-a`) para apanhar também imagens
não referenciadas por nenhum container parado — confirma com `docker system df` antes/depois como
mostrado acima. Nunca uses `docker system prune -a --volumes` (isso apagaria também os volumes
com a base de dados).

---

## Passo 4 — Confirmar o backtest semanal de domingo (verificação rápida, baixo risco)

**Objetivo:** o recibo mais recente em disco (`.cache/latest_backtest_results.json`) continua
datado de 2026-09-20; confirmar se o backtest de 27-09 correu e publicou.

**Comandos exatos:**
```
find /home/servidor/Desktop/cursor-projects/ib_bot/.cache -name "*.json" -newer \
  /home/servidor/Desktop/cursor-projects/ib_bot/.cache/latest_backtest_results.json
journalctl -u ib-backtests.service --since "2026-09-26" --no-pager | tail -60
```

**Oracle de aceitação:** se `find` devolver um ficheiro mais recente, está tudo bem (falso alarme
desta auditoria). Se `journalctl` mostrar falha/timeout e nenhum alerta disparou, reabre o Finding
#9 da auditoria de 09-20 (contrato do `ib_backtests_alert.sh`) e verifica se voltou a quebrar.

**Rollback:** nenhum (é só leitura).

**Gotchas:** nenhum.
