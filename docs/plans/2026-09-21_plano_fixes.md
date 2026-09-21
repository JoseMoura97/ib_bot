# Plano de Fixes — IB Bot (2026-09-21)

## Contexto para o executor (lê isto ANTES de qualquer passo — assume zero memória da conversa)

**O que é este projeto:** o IB Bot é um robô de trading (comprar/vender ações) para a Interactive
Brokers (IB), atualmente **PAUSED** — o José decidiu em julho de 2026 não ligar o motor de
execução real ("dormência seletiva"). Continua a correr, sozinho, todos os dias: um arquivo diário
de dados públicos ("PIT" — point-in-time), um backtest semanal, e um motor de "paper trading"
(dinheiro falso) diário que está **quebrado há mais de 5 semanas (38 dias corridos)**. Ver Finding
CRÍTICO #0 do audit `2026-09-21_audit_profundo.md` no mesmo diretório — **lê esse ficheiro
primeiro**, tem todo o contexto de evidência. Este é o 7º plano de fixes de uma série contínua
(9ª auditoria); os 6 anteriores não foram executados na parte de limpeza (o Passo 0/decisão nunca
foi respondido de forma síncrona).

**Paths absolutos importantes:**
- Repositório principal: `/home/servidor/Desktop/cursor-projects/ib_bot` (branch `main`).
- Segundo worktree (frontend v2): `/home/servidor/Desktop/cursor-projects/ib_bot-v2` (branch
  `frontend-v2`) — **não mexer sem necessidade**, serve `ib-bot-v2-frontend.service`.
- Docker compose do stack principal: dentro do repo (`docker-compose.yml` e variantes
  `.prod`/`.epyc`/`.b`). Containers: `ib_bot-api-1`, `ib_bot-beat-1`, `ib_bot-worker-1`,
  `ib_bot-db-1` (Postgres, user `ibbot`, db `ibbot`), `ib_bot-redis-1`, `ib_bot-web-1`,
  `ib_bot-nginx-1` (porta 8090).
- Base de dados: `docker exec ib_bot-db-1 psql -U ibbot -d ibbot`. **Nunca escrever** nas tabelas
  de negócio (`ib_orders`, `ib_trades`, `paper_snapshots`, `paper_trades`, `altdata_snapshots`)
  fora do próprio código da aplicação — só leitura direta por `psql` é permitida para
  diagnóstico.
- Base de dados do Conductor (gestão de planos): `psql -U servidor -d conductor` (utilizador
  `servidor`, sem password — autenticação peer local). Não há nenhum plano ativo em `ib_bot` além
  dos já fechados (`04bf8af8`, `4c48535c` ambos `done`) — este plano de fixes não duplica
  trabalho de nenhum plano do Conductor.
- Credenciais: **nunca em texto neste ficheiro.** `QUIVER_API_KEY` vive no `.env` dentro dos
  containers Docker (`docker exec ib_bot-worker-1 env | grep -i key` para CONFIRMAR que existe,
  nunca para imprimir o valor num relatório). Ficheiro `.env` do repo principal:
  `/home/servidor/Desktop/cursor-projects/ib_bot/.env` (permissões `600`). Credenciais da IB (2FA,
  password) vivem fora deste repo, geridas pelo José — não são necessárias para nenhum passo deste
  plano.
- MCP `claude.ai Interactive Brokers (IBKR)` — dá acesso de LEITURA à conta real do José
  (`get_account_summary`, `get_account_positions`). **`create_order_instruction` só gera um link
  para o José clicar — nunca submete uma ordem sozinho.** Não é necessário para este plano.

**Regras duras (não negociáveis):**
- **READ-ONLY em sistemas**: proibido `systemctl restart/stop` fora do explicitamente autorizado
  no Passo 2 abaixo, escrever em DBs de produção fora do próprio código da app, alterar config,
  colocar ordens, mover dinheiro. As únicas escritas permitidas neste plano: ficheiros de
  código/teste/docs dentro do repo `ib_bot`, `git add`/`git commit` desse mesmo repo, e o
  `systemctl disable --now` explicitamente autorizado no Passo 2.
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
  backtest completo (>1h CPU), usa `runjob --mem 4G --cpu 4 -- <comando>` — este padrão já está em
  produção desde 2026-09-20 no próprio timer `ib-backtests.service`, não inventar um novo.
- Antes de reportares qualquer estado ("está corrigido", "o erro desapareceu"), **corre o oráculo
  de aceitação do passo** — nunca assumas a partir de código lido.

---

## Passo 0 — Decisão explícita do José sobre o ciclo de auditoria (Finding CRÍTICO #1)

**Objetivo:** parar o padrão de 6 auditorias seguidas com o mesmo plano de limpeza ignorado.
Obter uma resposta explícita do José, registada em memória, sobre: (a) o que fazer ao arquivo PIT
(`altdata_snapshots` — vender B2B? continuar a acumular sem plano? arquivar e parar o timer?), (b)
se este ciclo de auditoria semanal deve continuar com esta cadência ou passar a "só quando algo
mudar" (ver Finding #9 do audit sobre fadiga de auditoria), e (c) se autoriza já os passos 2-5
abaixo (baixo risco, reversíveis).

**Comandos:**
```bash
# Este passo não tem comando de "fix" — é uma pergunta ativa ao José, não um documento.
# O executor deste plano deve usar request_user_approval (ou equivalente síncrono disponível na
# sessão) para apresentar, num único bloco:
#   1. O facto: "6 auditorias seguidas (08-17, 08-24, 08-31, 09-07, 09-14, 09-21) recomendaram o
#      mesmo plano de limpeza de 5 passos; nenhum foi executado. O bug do paper rebalance já leva
#      38 dias corridos de falha silenciosa."
#   2. A pergunta concreta: "Queres que eu:
#      (a) execute agora os passos 2-5 deste plano (consolidar frontends, limpar
#          .worktree-quarantine e imagens Docker, arrumar resíduos) — baixo risco, reversível; e
#      (b) o que decides sobre o arquivo PIT: continuar a acumular sem destino, vender B2B, ou
#          arquivar e desligar ib-altdata-backup.timer/ib-altdata-qa.timer; e
#      (c) queres manter a cadência semanal de auditoria, ou só quando houver mudança material?"
# Regista a resposta em memória com a skill "memory" (ou escrevendo diretamente um ficheiro
# reference_ib_bot_yyyymmdd_decisao.md em /home/servidor/.claude/projects/-home-servidor/memory/
# se a skill não estiver disponível nesta sessão).
```

**Oráculo de aceitação:** existe um ficheiro de memória (`reference_ib_bot_*decisao*.md` ou
entrada em `MEMORY-trading.md`) com a resposta textual do José, datado de hoje ou mais recente.
Comando: `ls -la /home/servidor/.claude/projects/-home-servidor/memory/ | grep -i "ib_bot.*decisao"`.

**Rollback:** nenhum (é uma pergunta, não uma alteração de sistema).

**Gotchas:** não presumas uma resposta e não avances os passos 2-5 sem ela ser dada explicitamente
— o padrão dos últimos 2 meses e meio mostra que perguntar sem sincronizar também não funciona; a
diferença desta vez é USAR `request_user_approval` de forma síncrona (não escrever só num
relatório que ninguém lê).

---

## Passo 1 — Corrigir o bug do `paper_rebalance_daily_task` (Finding CRÍTICO #0)

**Objetivo:** identificar e corrigir a causa de `tuple index out of range` em
`RebalancingBacktestEngine._generate_rebalance_events()`, que falha para as 9 estratégias das 2
contas de paper trading, todos os dias, desde pelo menos 2026-08-14 (38 dias confirmados a
21-09-2026).

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
# Se a exceção continuar a ser apanhada DENTRO da tarefa (não propaga), localizar a função
# interna real com grep (o nome exato pode ter mudado desde a última auditoria):
grep -rn "_generate_rebalance_events\|tuple index out of range" \
  /home/servidor/Desktop/cursor-projects/ib_bot/backend/ \
  /home/servidor/Desktop/cursor-projects/ib_bot/rebalancing_backtest_engine.py 2>/dev/null

# 1b. Ler o código da função raiz suspeita e reproduzir a chamada interna diretamente usando os
# ids reais das contas (confirmados via psql nesta sessão):
#   account 1 -> portfolio 7095ae3e-2633-49f4-b92c-094e2b4156aa
#   account 2 -> portfolio d2e87bea-0cd8-4175-82b0-3282ec8828dc
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c \
  "select distinct account_id, portfolio_id from paper_snapshots order by account_id;"

# 1c. Depois de identificada a linha exata que indexa um tuple/lista vazia, corrigir com uma
# guarda explícita (ex.: `if not weights: return []` ou similar, conforme a lógica real) e
# adicionar um teste de regressão em backend/tests/ que reproduza o cenário exato (dados de uma
# das 9 estratégias reais) e confirme que a função já não levanta `IndexError`/`tuple index out
# of range`.

# 1d. Ao mesmo tempo, no ponto onde a exceção é apanhada (backend/app/worker/tasks.py — localizar
# com grep), trocar `logger.warning(f"... error={e}")` por
# `logger.error("...", exc_info=True)` para que a próxima falha semelhante apareça com traceback
# completo nos logs (fecha também o Finding MÉDIO #8 do audit).
grep -n "paper_rebalance_daily: account=" \
  /home/servidor/Desktop/cursor-projects/ib_bot/backend/app/worker/tasks.py

# 1e. Rebuild e restart do worker (é o próprio serviço do bot, não um serviço partilhado do José;
# paper trading é dinheiro falso, não money-path real):
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
  bug e sob a regra dura de `request_user_approval` acima. **Nota:** estes ficheiros mudaram
  recentemente (plano `4c48535c`, fechado 2026-09-15) — confirmar com `git log -3 -- <ficheiro>`
  que não há trabalho em curso antes de sequer os leres, para não confundir contexto.
- O erro é idêntico para as 9 estratégias — é quase certo um problema estrutural na função (ex.:
  acesso a `resultado[0]` quando `resultado` pode vir vazio), não um problema de dados de uma
  fonte só. Não gastar tempo a testar fonte a fonte antes de ler o código.
- Depois de corrigido, os números de paper trading vão começar a refletir rebalanceamentos reais
  outra vez — não confundir "subida/descida súbita" no dia seguinte com um novo bug; documentar
  no plano futuro de retestagem (`2026-09-21_futuro_retestar_paper_corrigido.md`, se aplicável —
  ver planos futuros deste ciclo).

---

## Passo 2 — Consolidar os dois frontends (Finding ALTO #2)

**Objetivo:** ter só um frontend web vivo, eliminando a duplicação confirmada 6 auditorias
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

## Passo 3 — Limpar `.worktree-quarantine/` e imagens Docker antigas (Findings MÉDIO #6, #7)

**Objetivo:** recuperar >32 GB de disco (865 MB de worktrees já fundidos + >31 GB de imagens
Docker não usadas), sem qualquer risco.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot

# 3a. Confirmar que os worktrees em quarentena já estão fundidos em main antes de apagar
# (verificação de segurança, não presumir a partir do audit):
git log --all --oneline | grep -i "phase-p2-43e6\|phase-p3-ee99" | head -5
git branch -a | grep -i "phase-p2-43e6\|phase-p3-ee99"
# esperado: os commits aparecem em main (já fundidos); os branches remotos, se existirem, são só
# histórico, não trabalho pendente.

# 3b. Se confirmado, remover os diretórios de quarentena (não são worktrees git ativos —
# `git worktree list` já não os lista):
du -sh .worktree-quarantine/
rm -rf .worktree-quarantine/

# 3c. Limpar imagens Docker:
docker system df   # confirmar de novo os ~31,5 GB reclamáveis antes de agir
docker image prune -a --filter "until=168h"   # remove imagens não usadas há mais de 7 dias
docker system df   # confirmar a redução
```

**Oráculo de aceitação:**
```bash
ls .worktree-quarantine 2>&1   # esperado: "No such file or directory"
docker system df --format "{{.Type}}: {{.Reclaimable}}" | grep Images
# esperado: valor muito menor que 31GB (idealmente <5GB, dependendo de quantas imagens ativas ficam)
```

**Rollback:** `.worktree-quarantine/` — não aplicável, o código já está em `main` (confirmado no
passo 3a); se precisares de reconstruir o histórico exato do worktree, usa `git log`/`git show`
nos commits já fundidos. Imagens Docker — recriadas por `docker compose build`/`pull` na próxima
vez que forem necessárias; nenhum container ativo é afetado.

**Gotchas:** correr `git log`/`git branch` do passo 3a ANTES de qualquer `rm -rf` — nunca apagar
sem confirmar que o trabalho já está fundido. Correr `docker system df` ANTES de confirmar que as
imagens de `ib_bot-api-1`/`worker`/`beat`/`web`/`nginx`/`db`/`redis` (as 7 ativas) não vão ser
apagadas — o filtro `until=168h` já protege isto.

---

## Passo 4 — Arrumar resíduos na raiz do repositório (Finding BAIXO #10)

**Objetivo:** remover ficheiros obsoletos identificados 6 auditorias seguidas.

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
mkdir -p .archive/pre-2026-09-21-cleanup
git mv '$LOG' .archive/pre-2026-09-21-cleanup/ 2>/dev/null || mv '$LOG' .archive/pre-2026-09-21-cleanup/
git mv alembic_validation.db .archive/pre-2026-09-21-cleanup/
git mv backtest_results_2026_05_12.json backtest_results_corrected.json backtest_results_final.json .archive/pre-2026-09-21-cleanup/
git mv docker-compose.prod.yml.bak.1778273314 .archive/pre-2026-09-21-cleanup/
echo ".archive/" >> .gitignore
git add .gitignore
git commit -m "chore: arquivar resíduos da raiz identificados em 6 auditorias (LOG, alembic_validation.db, backtest_results antigos, docker-compose bak)"
```

**Oráculo de aceitação:**
```bash
ls '$LOG' alembic_validation.db backtest_results_2026_05_12.json 2>&1
# esperado: "No such file or directory" para todos (foram movidos)
git log -1 --oneline
# esperado: mostra o commit deste passo
```

**Rollback:** `git mv .archive/pre-2026-09-21-cleanup/* .` seguido de `git commit`.

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
ls .worktree-quarantine 2>&1                                                     # esperado: no such file
docker system df --format "{{.Type}}: {{.Reclaimable}}" | grep Images            # esperado: bem abaixo de 31GB
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001 http://localhost:8090   # esperado: só um responde 200/307
git status --porcelain   # esperado: vazio (tudo commitado)
```

**Oráculo de aceitação:** todos os 5 comandos acima devolvem o resultado esperado indicado.

**Rollback:** não aplicável (é só verificação).

**Gotchas:** se qualquer verificação falhar, NÃO reportar o plano como concluído — voltar ao passo
correspondente. Esta é exatamente a disciplina que faltou nos 6 ciclos anteriores.
