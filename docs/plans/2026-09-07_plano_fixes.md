# Plano de Fixes — IB Bot (2026-09-07)

## Contexto para o executor (lê isto ANTES de qualquer passo — assume zero memória da conversa)

**O que é este projeto:** o IB Bot é um robô de trading (comprar/vender ações) para a Interactive
Brokers (IB), atualmente **PAUSED** — o José decidiu em julho de 2026 não ligar o motor de
execução real ("dormência seletiva"). Continua a correr: um arquivo diário de dados públicos
("PIT"), um backtest semanal, e um motor de "paper trading" (dinheiro falso) diário que está
**quebrado** (ver Finding CRÍTICO #0 do audit `2026-09-07_audit_profundo.md` no mesmo diretório —
lê esse ficheiro primeiro, tem todo o contexto de evidência).

**Paths absolutos importantes:**
- Repositório principal: `/home/servidor/Desktop/cursor-projects/ib_bot` (branch `main`).
- Segundo worktree (frontend v2): `/home/servidor/Desktop/cursor-projects/ib_bot-v2` (branch
  `frontend-v2`) — **não mexer sem necessidade**, serve `ib-bot-v2-frontend.service`.
- Docker compose do stack principal: dentro do repo (`docker-compose.yml` e variantes
  `.prod`/`.epyc`/`.b`). Containers: `ib_bot-api-1`, `ib_bot-beat-1`, `ib_bot-worker-1`,
  `ib_bot-db-1` (Postgres, user `ibbot`, db `ibbot`), `ib_bot-redis-1`, `ib_bot-web-1`,
  `ib_bot-nginx-1` (porta 8090), `ib_bot-web-lint-1` (parado, lixo).
- Base de dados: `docker exec ib_bot-db-1 psql -U ibbot -d ibbot`. **Nunca escrever** nas tabelas
  de negócio (`ib_orders`, `ib_trades`, `paper_snapshots`, `paper_trades`, `altdata_snapshots`)
  fora do próprio código da aplicação — só leitura direta por `psql` é permitida para
  diagnóstico.
- Base de dados do Conductor (gestão de planos): `psql -U servidor -d conductor` (utilizador
  `servidor`, sem password — autenticação peer local).
- Credenciais: **nunca em texto neste ficheiro.** `QUIVER_API_KEY` e outras chaves vivem no `.env`
  dentro dos containers Docker (`docker exec ib_bot-worker-1 env | grep -i key` para CONFIRMAR
  que existem, nunca para imprimir o valor num relatório). Credenciais da IB (2FA, password)
  vivem fora deste repo, geridas pelo José — não são necessárias para nenhum passo deste plano.
- MCP `claude.ai Interactive Brokers (IBKR)` — dá acesso de LEITURA à conta real do José
  (`get_account_summary`, `get_account_positions`). **`create_order_instruction` só gera um link
  para o José clicar — nunca submete uma ordem sozinho.** Não é necessário para este plano.

**Regras duras (não negociáveis):**
- **READ-ONLY em sistemas**: proibido `systemctl restart/stop`, escrever em DBs de produção fora
  do próprio código da app, alterar config, colocar ordens, mover dinheiro. As únicas escritas
  permitidas neste plano: ficheiros de código/teste/docs dentro do repo `ib_bot`, e
  `git add`/`git commit` desse mesmo repo.
- **Qualquer alteração ao caminho de colocação de ordens reais** (`backend/app/services/ib_worker.py`,
  `backend/app/api/routes/live.py`, `system/execution/order_preflight.py`) passa OBRIGATORIAMENTE
  por `request_user_approval` antes de qualquer merge para `main`, e nunca dispensa um segundo
  revisor. Nenhum passo deste plano toca nesses ficheiros — se descobrires que precisas, PÁRA e
  pede aprovação explícita ao José antes de continuar.
- **Money-path**: qualquer ação que envolva dinheiro real (mesmo um teste de €5) tem de passar por
  `request_user_approval` com um teto de execução final verificado ≤ €5. Nenhum passo deste plano
  precisa disto — todo o trabalho é diagnóstico/limpeza/paper trading (dinheiro falso).
- **Commit no mesmo turn**: assim que um passo terminar com sucesso (oráculo verde), faz commit
  imediatamente. Não deixes trabalho terminado por commitar.
- **`runjob` para compute pesado**: nenhum passo deste plano precisa de compute pesado (tudo é
  leitura de logs, DB, e patches pequenos de Python). Se algum passo vier a precisar de correr o
  backtest completo (>1h CPU), usa `runjob --mem 8G --cpu 4 -- <comando>`, nunca correr solto.
- Antes de reportares qualquer estado ("está corrigido", "o erro desapareceu"), **corre o oráculo
  de aceitação do passo** — nunca assumas a partir de código lido.

---

## Passo 0 — Decisão explícita do José sobre o ciclo de auditoria (Finding CRÍTICO #1)

**Objetivo:** parar o padrão de 4 auditorias seguidas com o mesmo plano de limpeza ignorado.
Obter uma resposta explícita do José, registada em memória, sobre: (a) o que fazer ao arquivo
PIT (`altdata_snapshots` — vender B2B? continuar a acumular sem plano? arquivar e parar o
timer?), (b) se este ciclo de auditoria quinzenal/semanal deve continuar com esta cadência.

**Comandos:**
```bash
# Este passo não tem comando de "fix" — é uma pergunta ativa ao José, não um documento.
# O executor deste plano deve usar a ferramenta de mensagem/aprovação disponível na sessão
# (ex.: request_user_approval ou equivalente) para apresentar, num único bloco:
#   1. O facto: "4 auditorias seguidas (08-17, 08-24, 08-31, 09-07) recomendaram o mesmo plano
#      de limpeza de 5 passos; nenhum foi executado."
#   2. A pergunta concreta: "Queres que eu:
#      (a) execute agora os passos 2-5 deste plano (consolidar frontends, limpar Docker,
#          arrumar resíduos) — baixo risco, reversível; e
#      (b) o que decides sobre o arquivo PIT: continuar a acumular sem destino, vender B2B,
#          ou arquivar e desligar `ib-altdata-backup.timer`/`ib-altdata-qa.timer`?"
# Regista a resposta em memória com a skill "memory" (ou escrevendo diretamente um ficheiro
# reference_ib_bot_yyyymmdd_decisao.md em /home/servidor/.claude/projects/-home-servidor/memory/
# se a skill não estiver disponível nesta sessão).
```

**Oráculo de aceitação:** existe um ficheiro de memória novo (`ls -la
/home/servidor/.claude/projects/-home-servidor/memory/ | grep -i ib_bot` mostra uma data de hoje)
com a resposta do José registada textualmente (não parafraseada).

**Rollback:** nenhum — é só uma pergunta e um registo.

**Gotchas:** não escrevas "presumo que sim" e avances sozinho — isto é exatamente o padrão que já
falhou 4 vezes. Se o José não responder nesta sessão, documenta isso explicitamente no audit
seguinte ("perguntado em 09-07, sem resposta até <data>") em vez de repetir a pergunta do zero.

---

## Passo 1 — Diagnosticar e corrigir `paper_rebalance_daily_task` (Finding CRÍTICO #0)

**Objetivo:** descobrir a linha exata onde `tuple index out of range` acontece dentro de
`RebalancingBacktestEngine._generate_rebalance_events()` (ou função relacionada), corrigi-la, e
garantir que futuras falhas fiquem visíveis (não só um `WARNING` engolido).

**Comandos — passo 1a: reproduzir com traceback completo (dentro do container, sem tocar em produção):**
```bash
docker exec -it ib_bot-worker-1 python3 -c "
import traceback
from app.core.database import SessionLocal
from app.api.schemas import PaperRebalanceRequest as PRReq
from app.api.routes.paper import paper_rebalance_execute
from uuid import UUID

db = SessionLocal()
# conta 1, portfolio Ackman/Burry/Howard Marks — id confirmado no audit 2026-09-07
body = PRReq(portfolio_id=UUID('7095ae3e-2633-49f4-b92c-094e2b4156aa'), allocation_amount=100000.0, account_id=1)
try:
    paper_rebalance_execute(body, db)
except Exception:
    traceback.print_exc()
finally:
    db.rollback()
    db.close()
"
```
Isto corre a MESMA função que a tarefa diária chama, mas imprime o *traceback* completo (que os
logs de produção não têm) — vai apontar o ficheiro:linha exatos dentro de
`rebalancing_backtest_engine.py` ou `paper.py`. **`db.rollback()` no fim garante zero escrita
persistente** — é só leitura + cálculo, mesmo que o preview normalmente não escreva nada até ao
`execute`.

**Comandos — passo 1b: ler a linha exata reportada pelo traceback e corrigir.**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# substitui <ficheiro>:<linha> pelo que o traceback do passo 1a apontar
sed -n '<linha-10>,<linha+10>p' <ficheiro>
```
A correção depende do que o traceback mostrar — padrões prováveis a verificar primeiro (todos
confirmáveis por leitura de código nesta sessão de audit):
- `evs[-1]` em `paper.py:298` assume que `_generate_rebalance_events` devolveu pelo menos 1 evento
  — se a lista vier vazia por outro caminho não coberto pelo `if not evs: continue` (ex.: um
  `evs` que é uma tupla vazia em vez de lista, ou um objeto diferente do esperado), confirmar o
  tipo real devolvido.
- Dentro de `RebalancingBacktestEngine._generate_rebalance_events` ou `_clean_weight_map`, procurar
  por indexação posicional tipo `algo[0]`, `algo[1]`, `row[2]` sobre resultados de
  `fetch_prices`/dataframes que podem vir vazios quando uma fonte de dados (ex.: preços em falta
  para um ticker delistado — os logs do worker mostram avisos `yfinance: possibly delisted` no
  mesmo período) devolve menos colunas/linhas do que o código espera.
```bash
grep -n "\[0\]\|\[1\]\|\[-1\]\|\[2\]" /home/servidor/Desktop/cursor-projects/ib_bot/rebalancing_backtest_engine.py | head -40
```
Aplica a correção mínima (tipicamente: verificar o comprimento antes de indexar, ou tratar
"sem dados suficientes para este ticker" como `continue` em vez de deixar rebentar).

**Comandos — passo 1c: tornar o erro visível no futuro (não silencioso).**
Em `backend/app/worker/tasks.py`, na linha ~570 (`logger.warning(f"paper_rebalance_daily:
account={account_id} portfolio={portfolio_id} error={e}")`), adicionar `exc_info=True` para que o
*traceback* completo fique nos logs a partir de agora, mesmo que o bug volte a aparecer de outra
forma:
```python
logger.warning(
    f"paper_rebalance_daily: account={account_id} portfolio={portfolio_id} error={e}",
    exc_info=True,
)
```

**Comandos — passo 1d: rebuild e reiniciar SÓ o worker (não o resto do stack) para aplicar o patch.**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker compose build worker
docker compose up -d worker
```

**Oráculo de aceitação:**
```bash
# Espera até à próxima janela das 15:00 WEST (ou dispara manualmente a tarefa):
docker exec ib_bot-worker-1 python3 -c "from app.worker.tasks import paper_rebalance_daily_task; paper_rebalance_daily_task()"
docker logs ib_bot-worker-1 --since 5m | grep paper_rebalance_daily
# Esperado: para account=1 e account=2, a linha diz "freq=... orders=<N>" (sucesso), NÃO
# "error=tuple index out of range". N pode ser 0 se nada estiver "due" (frequência ainda não
# venceu) — isso é normal, o importante é NÃO haver "error=".
```
Se a frequência não estiver "due" para nenhuma estratégia no momento do teste manual, confirma
pelo menos que a exceção não repete — corre o passo 1a de novo (reproduz sempre,
independentemente de "due") e confirma que já não levanta exceção.

**Rollback:** `git revert <commit deste passo>`, depois `docker compose build worker && docker
compose up -d worker`.

**Gotchas:**
- **Não mexer em `place_market_order` nem no caminho de execução real** — este bug é 100%
  dentro do cálculo de pesos-alvo em paper trading, não perto do dinheiro real.
- Se `evs` vier vazio para TODAS as estratégias (incluindo as que não dependem de
  `quiver_congress_trades`), o bug é genérico no motor, não uma fonte de dados específica —
  confirmado no audit que falha identicamente para as 9 estratégias das 2 contas.
- Depois de corrigido, a curva de equity da conta 2 vai passar a refletir rebalanceamentos REAIS
  outra vez — é esperado que os números de "performance" mudem em relação ao que está documentado
  no audit de hoje (que descreve uma carteira congelada). Isso é o comportamento CORRETO, não uma
  regressão.

---

## Passo 2 — Consolidar os dois frontends (Finding ALTO #2)

**Objetivo:** manter só um frontend vivo — decidir qual (recomendação: manter
`ib-bot-v2-frontend.service` na porta 3001, que já fala com a API real :8001; desligar o stack
Docker completo `ib_bot-web-1`+`ib_bot-nginx-1` na 8090, que duplica API/worker/beat/db/redis
inteiros só para servir uma segunda cópia do frontend).

**Comandos:**
```bash
# 1. Confirmar que 3001 está de facto a funcionar e a falar com a API real antes de desligar nada:
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001
curl -s http://localhost:3001/api/health 2>&1 | head -5   # ou endpoint equivalente do frontend v2

# 2. Este passo ENVOLVE parar um serviço (docker compose down do web+nginx) — regra READ-ONLY
#    deste audit NÃO cobre isto (é o plano de fixes, não o audit, mas ainda assim é uma mudança
#    operacional visível). Apresentar ao José antes de executar (mensagem curta, não card
#    formal): "Vou desligar o segundo frontend Docker (porta 8090), fica só o 3001 vivo — ok?"
#    Só depois de confirmação (inline, não é preciso card):
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker compose stop web nginx
# NÃO usar `docker compose down` (isso remove containers/redes; `stop` é reversível com `start`).
```

**Oráculo de aceitação:**
```bash
curl -s -o /dev/null -w "8090: %{http_code}\n" http://localhost:8090   # esperado: erro de conexão (nada a responder)
curl -s -o /dev/null -w "3001: %{http_code}\n" http://localhost:3001   # esperado: 200 ou 307 (continua vivo)
docker ps --filter name=ib_bot-web-1 --filter name=ib_bot-nginx-1 --format "{{.Names}}: {{.Status}}"
# esperado: vazio ou "Exited"
```

**Rollback:** `docker compose start web nginx` (containers continuam a existir, só pararam).

**Gotchas:** a API (`ib_bot-api-1`, porta 8001), o worker e o beat continuam a correr — não os
pares, servem a lógica de negócio real (paper trading, altdata), não só o frontend duplicado.

---

## Passo 3 — Limpar disco Docker (Finding MÉDIO #6)

**Objetivo:** libertar os 32,36 GB de imagens reclamáveis, sem risco (imagens paradas, não
containers vivos).

**Comandos:**
```bash
docker system df   # confirma o número antes (deve mostrar ~32.36GB reclamável)
docker image prune -a --filter "until=48h"
# --filter until=48h evita apagar imagens usadas por builds em curso nas últimas 48h;
# ajusta para 0h só se tiveres a certeza que nada está a construir agora.
docker system df   # confirma depois
```

**Oráculo de aceitação:** `docker system df` mostra "Images ... RECLAIMABLE" muito menor que
32,36 GB (idealmente <5 GB, só as imagens dos containers ainda vivos).

**Rollback:** nenhum necessário — imagens apagadas podem ser reconstruídas com `docker compose
build` se algo precisar delas de novo (não há perda de dados, só de imagens já compiladas).

**Gotchas:** correr isto DEPOIS do passo 2 (para não apagar por engano a imagem do
web/nginx se ainda precisares dela para o rollback do passo 2 dentro da mesma sessão).

---

## Passo 4 — Arrumar resíduos na raiz do repositório (Finding BAIXO #9)

**Objetivo:** remover ficheiros mortos confirmados como não referenciados por nenhum
código/serviço vivo há 4 auditorias seguidas.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# Confirmar antes de apagar que nada os importa/lê:
grep -rl "alembic_validation.db\|backtest_results_2026_05_12\|backtest_results_corrected\|backtest_results_final" --include="*.py" . 2>/dev/null
# Esperado: vazio (nenhum ficheiro Python os referencia). Se aparecer algo, PARA e investiga
# antes de apagar.

git rm -f '$LOG' alembic_validation.db backtest_results_2026_05_12.json \
  backtest_results_corrected.json backtest_results_final.json \
  docker-compose.prod.yml.bak.1778273314
git commit -m "chore: remove root residue confirmed unreferenced (audit 2026-09-07 finding #9)"
```

**Oráculo de aceitação:**
```bash
git log -1 --stat | grep -E "LOG|alembic_validation|backtest_results|docker-compose.prod.yml.bak"
# esperado: mostra os 6 ficheiros como removidos (deletions) no commit mais recente
ls -la '$LOG' alembic_validation.db 2>&1   # esperado: "No such file or directory" para ambos
```

**Rollback:** `git revert <hash-deste-commit>`.

**Gotchas:** `$LOG` tem um `$` literal no nome — usa aspas simples em todos os comandos shell.

---

## Passo 5 — Documentar (não corrigir) o propósito da conta paper 1 (Finding BAIXO #10)

**Objetivo:** só documentação — perguntar ao José ou encontrar em código/commits antigos porque
existe uma segunda conta paper (`account_id=1`) que fica sempre em $100.000.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git log --all --oneline -S "account_id=1" -- backend/ | head -20
grep -rn "account_id.*1\b" backend/app/models/paper.py backend/app/services/paper_trading.py 2>/dev/null | head -20
```
Se a origem não ficar clara por código/commits, perguntar ao José junto com o passo 0 (mesma
mensagem/aprovação, não duas mensagens separadas).

**Oráculo de aceitação:** o próximo audit tem uma linha explicando o propósito da conta 1 (mesmo
que a resposta seja "conta de controlo intencional, sem trades por desenho" — só precisa de estar
documentado, não de mudar comportamento).

**Rollback:** N/A (só documentação).

---

## Passo 6 — `git add` + commit final dos artefactos deste ciclo de audit

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git add docs/audits docs/plans
git commit -m "Audit profundo 2026-09-07 + planos"
git log -1 --format="%H"
```

**Oráculo de aceitação:** `git log -1 --stat` mostra os ficheiros
`docs/audits/2026-09-07_audit_profundo.md`, `docs/plans/2026-09-07_plano_fixes.md`, e os planos
futuros (`docs/plans/2026-09-07_futuro_*.md`) no commit.
