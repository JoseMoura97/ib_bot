# Plano de Fixes — IB Bot (2026-10-19)

## Contexto para o executor (lê isto primeiro, sem precisar da conversa original)

**O que é este projeto:** o `ib_bot` é um robô de trading automático (compra/venda de ações) que
usava a conta do José na Interactive Brokers (IB, a corretora). Testou 56 estratégias e todas
reprovaram num teste estatístico rigoroso (Deflated Sharpe Ratio) em maio de 2026 — nenhuma tem
edge real. O projeto está **PAUSED** (pausado) desde então: não se decide o próximo passo de
negócio, mas processos automáticos (backtests semanais, arquivo de dados diário, paper trading)
continuam a correr sozinhos. **NUNCA houve uma ordem real executada** (`ib_orders=0` desde
sempre) e o gateway que ligaria à IB está desligado desde 2026-08-27. Lê
`docs/audits/2026-10-19_audit_profundo.md` (o audit que gerou este plano) para o estado completo.

**Paths importantes:**
- Repositório: `/home/servidor/Desktop/cursor-projects/ib_bot` (branch `main`, único checkout que
  os timers automáticos usam — NUNCA mudar a sua branch, ver `AGENTS.md` no root do repo).
- Para trabalho de edição/teste, criar um worktree separado: `git worktree add -b <branch>
  <path-separado> main` (corrido DENTRO do repo principal) e trabalhar lá. Só integrar em `main`
  depois de validado.
- Base de dados do bot: Postgres dentro do container `ib_bot-db-1` (user `ibbot_app`, db
  `ibbot`). Acede-se com `docker exec ib_bot-db-1 psql -U ibbot_app -d ibbot -c "<query>"`.
- Credenciais: ficheiro `/home/servidor/Desktop/cursor-projects/ib_bot/.env` (permissões 600, só
  o utilizador `servidor`). **Nunca imprimir os valores** — só confirmar que as chaves/flags
  existem com `grep -E "^NOME_DA_CHAVE=" .env` (sem mostrar segredos; flags não-secretas como
  `ENABLE_LIVE_TRADING`/`LIVE_DRY_RUN` podem ser lidas e citadas diretamente).
- Script de limpeza Docker: `infra/scripts/docker_prune_weekly.sh` (criado em 2026-10-14),
  disparado pelo systemd timer `ib-docker-prune.timer`/`.service`.
- Stack Docker do bot: `docker compose -f docker-compose.yml` no root do repo. Serviços:
  `api`, `worker`, `beat`, `db`, `redis`, `web`, `nginx`. Container `ibeam-primary` (fora do
  compose do bot, definido noutro lado no host) mantém a sessão IB autenticada só para preços.

**Regras obrigatórias para quem executar este plano:**
1. **READ-ONLY em produção real** — este projeto nunca deve enviar ordens reais. Qualquer
   alteração de código que toque em `ENABLE_LIVE_TRADING`, `ib_orders`, ou no caminho de execução
   real exige aprovação explícita do José antes de aplicar (`request_user_approval` ou pedido
   direto) — isto é "money-path", mesmo que `ENABLE_LIVE_TRADING` esteja hoje em `false`. Nenhum
   passo deste plano toca nesse caminho — só limpeza de infraestrutura e governança de processo.
2. **Commit no mesmo turn.** Depois de cada passo verificado (oracle de aceitação a passar), fazer
   `git commit` imediatamente nesse mesmo turno — não deixar trabalho stageado.
3. **`runjob` para trabalho pesado.** Se algum passo precisar de reconstruir imagens Docker
   (`docker compose build`, pode demorar minutos e usar CPU/RAM significativos), usar
   `runjob --mem 8G --cpu 4 -- docker compose build ...` em vez de correr diretamente.
4. **Nunca editar um payload de `*-release-<sha>`** — não aplicável a este projeto (não usa o
   sistema de release do cluster polymarket), mas a disciplina de nunca sobrescrever artefactos
   publicados aplica-se da mesma forma: commitar, nunca editar histórico.
5. **Timers não podem ficar sem o seu checkout.** O checkout principal (`main` em
   `/home/servidor/Desktop/cursor-projects/ib_bot`) é usado por `ib-altdata-backup.service` e
   `ib-altdata-qa.service` todas as noites — nunca o deixar com `git status` sujo depois de um
   passo (cada passo abaixo termina com commit limpo).
6. **Nunca restart `ibgateway.service`/`xvfb-ibgw.service`** — estão parados por decisão
   deliberada do José (dormência seletiva, 2026-08-27). Nenhum passo deste plano os toca.

---

## Passo 1 — Corrigir a limpeza Docker (reporta sempre "0B reclaimed")

**Objetivo:** corrigir `infra/scripts/docker_prune_weekly.sh` para que realmente liberte espaço
em disco, em vez de reportar sempre "Total reclaimed space: 0B" (confirmado em 2026-10-14 e
2026-10-18, as duas únicas corridas até hoje).

**Causa raiz (confirmada no audit 2026-10-19):** o script só remove imagens `dangling` (sem
container a usá-las) com `docker image prune -f --filter "until=720h"`. Mas os containers
`ib_bot-worker-1`/`ib_bot-beat-1`/`ib_bot-api-1` nunca são reiniciados depois de uma imagem nova
ser construída (cada fix de código gera uma imagem nova com a mesma tag `latest`, mas o container
antigo continua a correr a imagem antiga) — por isso a imagem antiga nunca fica verdadeiramente
`dangling` de forma removível (o Docker recusa-se a apagar uma imagem referenciada por um
container, parado ou a correr).

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git worktree add -b fix/docker-prune-effectiveness-20261019 \
  /home/servidor/ib-docker-prune-fix-20261019 \
  main
cd /home/servidor/ib-docker-prune-fix-20261019

# 1a. Confirmar a causa raiz antes de editar: ver quantos containers referenciam imagens
# "velhas" (não a mais recente com a mesma tag)
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.CreatedAt}}' | grep ib_bot

# 1b. Editar infra/scripts/docker_prune_weekly.sh: adicionar, ANTES do `docker image prune`,
# um passo que reinicia os containers do compose do ib_bot para que passem a usar a imagem
# mais recente com a mesma tag (isto LIBERTA a referência à imagem antiga, que passa a estar
# verdadeiramente "dangling" e removível).
```
Editar o script para incluir, logo depois do `echo "docker-prune: start ..."` e ANTES do
`docker image prune`:
```bash
echo "docker-prune: recreating ib_bot containers from current tagged images (releases old image refs)"
docker compose -f /home/servidor/Desktop/cursor-projects/ib_bot/docker-compose.yml \
  up -d --no-build --force-recreate api worker beat web
```
(usa `--no-build` para NÃO reconstruir — só trocar o container para a imagem já etiquetada mais
recente; `--force-recreate` garante que mesmo sem mudança de imagem o container é substituído,
libertando a referência à imagem antiga se já tiver sido substituída por um build anterior).

```bash
# 1c. Testar em modo dry-run primeiro (o script já suporta --dry-run)
bash infra/scripts/docker_prune_weekly.sh --dry-run

# 1d. Correr a versão real e confirmar espaço libertado
bash infra/scripts/docker_prune_weekly.sh
docker system df
```

**Correção (verificador, 2026-10-19):** o número de 65,13GB/56,37GB de `docker system df` é do
**HOST INTEIRO** (22 imagens, 17 de outros projetos — Jellyfin, Nextcloud/family-drive, Immich,
OnlyOffice, Mongo, etc.), não só do `ib_bot`. `docker images -f dangling=true` devolve **zero**
hoje — não há camadas dangling acumuladas. Das 5 imagens do `ib_bot`, só `ib_bot-worker:latest`
tem 0 containers a usá-la (~8,76GB de "unique size", via `docker system df -v`). Este passo só
pode libertar, no máximo, **~8-9GB** — não vai mover visivelmente o número de 65GB/56GB do host.
O oracle abaixo foi reescrito para ser verificável NO MESMO TURNO (antes/depois), em vez de
empurrar o teste real para o próximo domingo sem monitorização.

**Oracle de aceitação (medir ANTES e DEPOIS, no mesmo turno, nunca aceitar por omissão):**
```bash
# ANTES (correr logo no início do passo, antes de qualquer `--force-recreate`/prune):
docker system df --format '{{.Type}}: {{.Reclaimable}}' | grep -i images > /tmp/docker_images_before.txt
cat /tmp/docker_images_before.txt

# ... aplicar o fix (1b/1c/1d acima) ...

# DEPOIS:
docker system df --format '{{.Type}}: {{.Reclaimable}}' | grep -i images > /tmp/docker_images_after.txt
cat /tmp/docker_images_after.txt
diff /tmp/docker_images_before.txt /tmp/docker_images_after.txt
```
→ **esperado: o valor de `Reclaimable` para `Images` desce em ~8-9GB** (o tamanho único de
`ib_bot-worker:latest`, a única imagem do `ib_bot` hoje com 0 containers a usá-la — confirmar
antes com `docker system df -v | grep ib_bot`). **Se o valor não baixar por essa ordem de
grandeza, o passo NÃO está feito** — reportar explicitamente "não resolvido: 0B reclaimed
mesmo depois do force-recreate" em vez de aceitar por omissão ou empurrar a verificação para o
disparo semanal de domingo (25-out). O disparo de domingo serve só como confirmação adicional de
regressão a longo prazo (`journalctl -u ib-docker-prune.service -n 20` depois de 25-out), nunca
como o único teste de aceitação deste passo.

**Rollback:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git worktree remove /home/servidor/ib-docker-prune-fix-20261019 --force
```
(worktree descartável; `main` só é tocado no passo de integração abaixo).

**Integração em `main`:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git fetch /home/servidor/ib-docker-prune-fix-20261019 \
  fix/docker-prune-effectiveness-20261019:fix/docker-prune-effectiveness-20261019
git merge --no-ff fix/docker-prune-effectiveness-20261019 \
  -m "fix(docker): force-recreate ib_bot containers before pruning so stale tagged-latest images actually become reclaimable"
git push origin main
```

**Gotchas:**
- `--force-recreate` reinicia os containers `api`/`worker`/`beat`/`web` — isto causa uma
  interrupção de alguns segundos nessas 4 peças (não no `db`/`redis`/`nginx`). Correr o prune
  fora de qualquer janela crítica (não há janelas críticas neste projeto pausado, mas evitar
  correr a menos de 5 minutos do disparo diário do `paper_rebalance_daily_task`, às 15:00 UTC,
  para não interromper uma tarefa a meio).
- Confirmar que `ib_bot-beat-1` (o scheduler Celery) volta a agendar corretamente depois do
  restart — `docker logs ib_bot-beat-1 --tail 10` deve mostrar o scheduler a arrancar sem erro.
- Isto não resolve a imagem etiquetada `ib_bot-worker:altdata-qa-pin-<sha>` (pin de conteúdo
  deliberado para a QA de alt-data) — essa imagem é propositadamente mantida fora do `-a` do
  prune; não a remover.

---

## Passo 2 — Dar dono formal no Conductor a este projeto pausado

**Objetivo:** fechar o achado MÉDIO #4 (34 dias sem nenhum plano Conductor ativo para `ib_bot`),
criando um plano leve de "vigilância" que dê dono formal aos findings recorrentes, mesmo com o
projeto pausado a nível de negócio.

**Comandos exatos:**
```bash
# Usar a skill /dispatch ou a ferramenta de Conductor direta para criar um plano leve.
# Não é dispatch de trabalho pesado — é só dar dono formal a um projeto pausado que continua a
# gerar findings semanais (auditoria recorrente). Consultar o José sobre quem deve ser o dono
# (DM existente do domínio trading, ou um novo DM leve "ib_bot-watch").
psql -U servidor -d conductor -c \
  "SELECT id, status, title FROM project_plans WHERE slug='ib_bot' ORDER BY updated_at DESC;"
# Confirmar que não há já um plano `executing` (evitar duplicar)
```
Criar o plano via a interface normal do Conductor (não diretamente por INSERT SQL — usar a
ferramenta/skill apropriada do Conductor para que o plano tenha o formato e os campos esperados
pelo resto da frota). Título sugerido: "ib_bot — vigilância pós-pausa (achados recorrentes sem
dono)". Âmbito: monitorizar os timers/serviços listados na secção (c) do audit, escalar ao José
qualquer erro novo (ex.: um `ERROR` em `paper_rebalance_logs` que não seja o já corrigido), e
decidir se cada auditoria semanal futura precisa de continuar ou se pode passar a mensal agora
que o único bug crítico está fechado.

**Oracle de aceitação:**
```bash
psql -U servidor -d conductor -c \
  "SELECT id, status, title FROM project_plans WHERE slug='ib_bot' ORDER BY updated_at DESC LIMIT 1;"
```
→ esperado: 1 linha nova, `status` diferente de `superseded`/`done` (ex.: `executing` ou
`active`), título a mencionar vigilância/monitorização.

**Rollback:** marcar o plano novo como `superseded` via a interface do Conductor (não apagar a
linha da base de dados diretamente).

**Gotchas:**
- Não criar um plano pesado de "reativação" aqui — isso é uma decisão do José, tratada no plano
  futuro de decisão estratégica (`docs/plans/2026-10-19_futuro_decisao_estrategica.md`), gated
  por este passo.
- Confirmar com José quem deve ser o dono (DM) antes de criar — não assumir.

---

## Passo 3 — Registar em memória os caminhos de ficheiro consolidados

**Objetivo:** fechar o achado BAIXO #5 (pedido há 2 auditorias, nunca executado).

**Comandos exatos:** usar a skill `/memory` para adicionar, em `MEMORY-trading.md` (dentro de
`/home/servidor/.claude/projects/-home-servidor/memory/`), a linha:
```
- Os nomes `project_ib_bot.md`/`project_ib_bot_audit.md`/`project_pead.md`/`project_earnings_vol.md`
  (usados em briefs antigos) foram consolidados em `MEMORY-trading.md` + `reference_ib_bot_*.md`.
  Não procurar por esses nomes exatos — já não existem.
```

**Oracle de aceitação:**
```bash
grep -n "project_ib_bot.md\|project_pead.md\|project_earnings_vol.md" \
  /home/servidor/.claude/projects/-home-servidor/memory/MEMORY-trading.md
```
→ esperado: a linha nova aparece.

**Rollback:** editar o ficheiro e remover a linha (é só texto, sem efeito em sistemas).

**Gotchas:** este passo não tem `git commit` associado no repo `ib_bot` (memória não vive lá) —
não esquecer isto não conta para o commit final deste plano.

---

## Passo 4 — Investigar as 6 linhas `preview`/`ERROR` em `live_rebalance_audit`

**Objetivo:** fechar o achado BAIXO #6 — entender porque 6 das 25 tentativas `preview` deram
`ERROR`, antes de qualquer decisão futura de reativar execução real.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker exec ib_bot-db-1 psql -U ibbot_app -d ibbot -c \
  "SELECT created_at, action, status, error FROM live_rebalance_audit WHERE status='ERROR' ORDER BY created_at;"
```

**Oracle de aceitação:** produzir uma frase clara "a causa dos 6 erros preview é X" (ex.: conta
de teste sem posições, parâmetro inválido, etc.) e decidir se precisa de fix de código (se sim,
abrir um novo passo) ou se é comportamento esperado de um ambiente de preview sem dados reais
(nesse caso, só documentar, sem fix).

**Rollback:** nenhum (passo read-only).

**Gotchas:** não disparar `preview`/`dry_run` manualmente para reproduzir — usar só os registos
já existentes; qualquer nova chamada ao caminho de execução real/preview exige a mesma disciplina
de aprovação do passo 1 das regras gerais acima.

---

## Fecho do plano

Depois dos passos 1 e 2 (os passos 3-4 são memória/investigação, sem commit obrigatório no repo),
confirmar estado limpo e publicar:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git status --porcelain   # esperado: vazio
git log --oneline -3     # confirmar o commit do passo 1 está lá
```
