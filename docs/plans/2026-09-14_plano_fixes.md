# Plano de Fixes — IB Bot (2026-09-14)

## Contexto para o executor (lê isto ANTES de qualquer passo — assume zero memória da conversa)

**O que é este projeto:** o IB Bot é um robô de trading (comprar/vender ações) para a Interactive
Brokers (IB), atualmente **PAUSED** — o José decidiu em julho de 2026 não ligar o motor de
execução real ("dormência seletiva"). Continua a correr: um arquivo diário de dados públicos
("PIT" — point-in-time), um backtest semanal, e um motor de "paper trading" (dinheiro falso)
diário que está **quebrado há mais de 1 mês** (ver Finding CRÍTICO #0 do audit
`2026-09-14_audit_profundo.md` no mesmo diretório — **lê esse ficheiro primeiro**, tem todo o
contexto de evidência e é a 7ª auditoria de uma série contínua; este é o 6º plano de fixes da
mesma série, os 5 anteriores não foram executados).

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
  `servidor`, sem password — autenticação peer local). Há um plano NOVO `4c48535c` (draft, criado
  2026-09-13, dono `ib_bot`) de hardening adicional de money-path que este plano de fixes **não
  duplica** — não mexer nele, é trabalho separado que o José/Conductor decide quando aprovar.
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
  pede aprovação explícita ao José antes de continuar. (Esse trabalho já tem plano próprio,
  `4c48535c` no Conductor.)
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

**Objetivo:** parar o padrão de 5 auditorias seguidas com o mesmo plano de limpeza ignorado.
Obter uma resposta explícita do José, registada em memória, sobre: (a) o que fazer ao arquivo PIT
(`altdata_snapshots` — vender B2B? continuar a acumular sem plano? arquivar e parar o timer?), (b)
se este ciclo de auditoria quinzenal/semanal deve continuar com esta cadência, e (c) se autoriza
já os passos 2-5 abaixo (baixo risco, reversíveis).

**Comandos:**
```bash
# Este passo não tem comando de "fix" — é uma pergunta ativa ao José, não um documento.
# O executor deste plano deve usar a ferramenta de mensagem/aprovação disponível na sessão
# (ex.: request_user_approval ou equivalente) para apresentar, num único bloco:
#   1. O facto: "5 auditorias seguidas (08-17, 08-24, 08-31, 09-07, 09-14) recomendaram o mesmo
#      plano de limpeza de 5 passos; nenhum foi executado."
#   2. A pergunta concreta: "Queres que eu:
#      (a) execute agora os passos 2-5 deste plano (consolidar frontends, limpar Docker,
#          arrumar resíduos) — baixo risco, reversível; e
#      (b) o que decides sobre o arquivo PIT: continuar a acumular sem destino, vender B2B,
#          ou arquivar e desligar `ib-altdata-backup.timer`/`ib-altdata-qa.timer`?"
# Regista a resposta em memória com a skill "memory" (ou escrevendo diretamente um ficheiro
# reference_ib_bot_yyyymmdd_decisao.md em /home/servidor/.claude/projects/-home-servidor/memory/
# se a skill não estiver disponível nesta sessão).
```

**Oráculo de aceitação:** existe um ficheiro de memória (`reference_ib_bot_*decisao*.md` ou
entrada em `MEMORY-trading.md`) com a resposta textual do José, datado de hoje ou mais recente.
Comando: `ls -la /home/servidor/.claude/projects/-home-servidor/memory/ | grep -i "ib_bot.*decisao"`.

**Rollback:** nenhum (é uma pergunta, não uma alteração de sistema).

**Gotchas:** não presumas uma resposta e não avances os passos 2-5 sem ela ser dada explicitamente
— mesmo que "pareça óbvio" que o José quer a limpeza feita, o padrão dos últimos 2 meses mostra
que perguntar sem agir também não funciona; a diferença desta vez é USAR `request_user_approval`
de forma síncrona (não escrever só num relatório que ninguém lê).

---

## Passo 1 — Corrigir o bug do `paper_rebalance_daily_task` (Finding CRÍTICO #0)

**Objetivo:** identificar e corrigir a causa de `tuple index out of range` em
`RebalancingBacktestEngine._generate_rebalance_events()`, que falha para as 9 estratégias das 2
contas de paper trading, todos os dias, desde pelo menos 2026-08-14.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot

# 1a. Reproduzir o erro manualmente com traceback completo (dentro do container, sem tocar em
# dinheiro real — paper trading só mexe em tabelas paper_*):
docker exec ib_bot-worker-1 python3 -c "
import traceback
from app.worker.tasks import paper_rebalance_daily_task
try:
    paper_rebalance_daily_task()
except Exception:
    traceback.print_exc()
"
# Se a exceção for apanhada DENTRO da tarefa (não propaga), reproduz a chamada interna
# diretamente, por exemplo (ajustar ao nome real da função encontrado em
# backend/app/api/routes/paper.py):
docker exec ib_bot-worker-1 python3 -c "
import traceback
from app.api.routes.paper import paper_rebalance_preview
try:
    # usar os mesmos ids reais das contas: account 1 -> portfolio 7095ae3e-2633-49f4-b92c-094e2b4156aa
    # account 2 -> portfolio d2e87bea-0cd8-4175-82b0-3282ec8828dc (confirmados via psql)
    paper_rebalance_preview(account_id=1)
except Exception:
    traceback.print_exc()
"

# 1b. Ler o código da função raiz suspeita (linha exata pode ter mudado; localizar por grep):
grep -n "_generate_rebalance_events" /home/servidor/Desktop/cursor-projects/ib_bot/rebalancing_backtest_engine.py

# 1c. Depois de identificada a linha exata que indexa um tuple/lista vazia, corrigir com uma
# guarda explícita (ex.: `if not weights: return []` ou similar, conforme a lógica real) e
# adicionar um teste de regressão em backend/tests/ que reproduza o cenário exato (dados de uma
# das 9 estratégias reais) e confirme que a função já não levanta `IndexError`/`tuple index out
# of range`.

# 1d. Ao mesmo tempo, no ponto onde a exceção é apanhada (backend/app/worker/tasks.py — localizar
# com grep), trocar `logger.warning(f"... error={e}")` por
# `logger.error("...", exc_info=True)` para que a próxima falha semelhante apareça com traceback
# completo nos logs (fecha também o Finding MÉDIO #8 do audit).
grep -n "paper_rebalance_daily: account=" /home/servidor/Desktop/cursor-projects/ib_bot/backend/app/worker/tasks.py

# 1e. Rebuild e restart do worker (dentro das regras: é o próprio serviço do bot, não um serviço
# partilhado do José; paper trading é dinheiro falso, não money-path real):
docker compose -f docker-compose.yml build worker
docker compose -f docker-compose.yml up -d worker

# 1f. Correr manualmente uma vez para confirmar (ver oráculo abaixo).
```

**Oráculo de aceitação:**
```bash
docker exec ib_bot-worker-1 python3 -c "from app.worker.tasks import paper_rebalance_daily_task; paper_rebalance_daily_task()"
docker logs ib_bot-worker-1 --since 5m | grep "paper_rebalance_daily.*error"
# esperado: SEM nenhuma linha "error=" — se aparecer qualquer uma, o passo NÃO está concluído,
# volta a 1a com o traceback completo agora disponível.
```
Adicionalmente, correr a suite de testes relevante:
```bash
docker exec ib_bot-api-1 python3 -m pytest backend/tests/ -k "rebalance" -v
# esperado: todos os testes passam (0 failed).
```

**Rollback:** `git revert <commit-deste-passo>` seguido de `docker compose build worker && docker
compose up -d worker`. Como o bug é só de paper trading (dinheiro falso), reverter não tem
qualquer impacto em dinheiro real.

**Gotchas:**
- Não tocar em `backend/app/services/ib_worker.py`, `backend/app/api/routes/live.py`, ou
  `system/execution/order_preflight.py` — são o caminho de execução real, fora do escopo deste
  bug e sob a regra dura de `request_user_approval` acima.
- O erro é idêntico para as 9 estratégias — é quase certo um problema estrutural na função (ex.:
  acesso a `resultado[0]` quando `resultado` pode vir vazio), não um problema de dados de uma
  fonte só. Não gastar tempo a testar fonte a fonte antes de ler o código.
- Depois de corrigido, os números de paper trading vão começar a refletir rebalanceamentos reais
  outra vez — não confundir "subida/descida súbita" no dia seguinte com um novo bug; documentar
  no plano futuro de retestagem (`2026-09-14_futuro_retestar_paper_corrigido.md`).

---

## Passo 2 — Consolidar os dois frontends (Finding ALTO #2)

**Objetivo:** ter só um frontend web vivo, eliminando a duplicação confirmada 5 auditorias
seguidas.

**Comandos:**
```bash
# 2a. Confirmar qual frontend o José usa de facto (perguntar explicitamente se não houver sinal
# claro — não presumir). Sinal indireto: acessos recentes.
sudo journalctl -u ib-bot-v2-frontend.service --since "-30 days" | grep -c "GET /"
docker logs ib_bot-nginx-1 --since 720h 2>&1 | grep -c "GET /"

# 2b. Se a decisão for manter só o stack Docker principal (porta 8090), parar o serviço systemd
# extra (NÃO apagar o worktree sem confirmação extra do José, pode ter código útil):
sudo systemctl disable --now ib-bot-v2-frontend.service

# 2c. Se a decisão for o inverso, documentar e parar o container web/nginx do stack principal em
# vez disso (não fazer os dois ao mesmo tempo).
```

**Oráculo de aceitação:**
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001   # deve dar erro de ligação (frontend parado) OU
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8090   # um dos dois, não os dois com 200/307
```

**Rollback:** `sudo systemctl enable --now ib-bot-v2-frontend.service` (ou equivalente para o
outro lado).

**Gotchas:** parar um serviço systemd É uma escrita em sistema — está fora do "READ-ONLY" genérico
mas é explicitamente autorizado aqui porque (a) é reversível num comando, (b) não é um serviço
partilhado (regra do laptop/VM do scraper não se aplica), (c) só afeta um painel de visualização,
não money-path. Se tiveres dúvida, usa `request_user_approval` antes deste passo especificamente.

---

## Passo 3 — Limpar imagens Docker antigas (Finding MÉDIO #6)

**Objetivo:** recuperar >30 GB de disco, sem qualquer risco (imagens não usadas por nenhum
container ativo).

**Comandos:**
```bash
docker system df   # confirmar de novo os 32,37 GB reclamáveis antes de agir
docker image prune -a --filter "until=168h"   # remove imagens não usadas há mais de 7 dias
docker system df   # confirmar a redução
```

**Oráculo de aceitação:**
```bash
docker system df --format "{{.Type}}: {{.Reclaimable}}" | grep Images
# esperado: valor muito menor que 32GB (idealmente <5GB, dependendo de quantas imagens ativas ficam)
```

**Rollback:** não aplicável — imagens Docker removidas por `prune` seriam recriadas por
`docker compose build`/`pull` na próxima vez que forem necessárias; nenhum container ativo é
afetado (o comando só apaga imagens SEM container a usá-las).

**Gotchas:** correr `docker system df` ANTES para confirmar que as imagens de
`ib_bot-api-1`/`worker`/`beat`/`web`/`nginx`/`db`/`redis` (as 7 ativas) não vão ser apagadas — o
filtro `until=168h` já protege isto, mas confirma no output do prune que só imagens `<none>` ou
antigas foram removidas.

---

## Passo 4 — Arrumar resíduos na raiz do repositório (Finding BAIXO #9)

**Objetivo:** remover ficheiros obsoletos identificados 5 auditorias seguidas.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
mkdir -p .archive/pre-2026-09-14-cleanup
git mv '$LOG' .archive/pre-2026-09-14-cleanup/ 2>/dev/null || mv '$LOG' .archive/pre-2026-09-14-cleanup/
git mv alembic_validation.db .archive/pre-2026-09-14-cleanup/
git mv backtest_results_2026_05_12.json backtest_results_corrected.json backtest_results_final.json .archive/pre-2026-09-14-cleanup/
git mv docker-compose.prod.yml.bak.1778273314 .archive/pre-2026-09-14-cleanup/
echo ".archive/" >> .gitignore
git add .gitignore
git commit -m "chore: arquivar resíduos da raiz identificados em 5 auditorias (LOG, alembic_validation.db, backtest_results antigos, docker-compose bak)"
```

**Oráculo de aceitação:**
```bash
ls '$LOG' alembic_validation.db backtest_results_2026_05_12.json 2>&1
# esperado: "No such file or directory" para todos (foram movidos)
git log -1 --oneline
# esperado: mostra o commit deste passo
```

**Rollback:** `git mv .archive/pre-2026-09-14-cleanup/* .` seguido de `git commit`.

**Gotchas:** usar `.archive/` (não apagar de vez) para o caso de algum destes ficheiros ainda ser
referenciado por algum script esquecido — verificar antes com
`grep -rn "backtest_results_2026_05_12\|alembic_validation" --include="*.py" .` (excluindo
`.archive/`) para confirmar que nada os importa.

---

## Passo 5 — Verificação final e fecho do ciclo

**Objetivo:** confirmar que todos os passos anteriores estão realmente verdes antes de considerar
este plano concluído.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker exec ib_bot-worker-1 python3 -c "from app.worker.tasks import paper_rebalance_daily_task; paper_rebalance_daily_task()"
docker logs ib_bot-worker-1 --since 2m | grep -c "paper_rebalance_daily.*error"   # esperado: 0
docker system df --format "{{.Type}}: {{.Reclaimable}}" | grep Images             # esperado: bem abaixo de 32GB
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001 http://localhost:8090   # esperado: só um responde 200/307
git status --porcelain   # esperado: vazio (tudo commitado)
```

**Oráculo de aceitação:** todos os 4 comandos acima devolvem o resultado esperado indicado.

**Rollback:** não aplicável (é só verificação).

**Gotchas:** se qualquer verificação falhar, NÃO reportar o plano como concluído — voltar ao passo
correspondente. Esta é exatamente a disciplina que faltou nos 5 ciclos anteriores.
