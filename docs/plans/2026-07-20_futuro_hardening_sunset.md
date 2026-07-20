# Plano futuro — Hardening & sunset automatizado (contingência "matar o projeto")

## Gate de arranque (obrigatório — verificar antes de começar)

**Só começa quando o José tiver respondido explicitamente "matar"/"não
continuar" ao one-pager do plano
`docs/plans/2026-07-20_futuro_decisao_estrategica.md` (passo 3 desse
plano).** Verificar com:

```bash
psql conductor -c "
SELECT id, title, body, created_at FROM plan_knowledge
WHERE plan_id = (SELECT id FROM project_plans WHERE slug='ib_bot' ORDER BY created_at DESC LIMIT 1)
AND kind = 'decision'
ORDER BY created_at DESC LIMIT 5"
```

Ler manualmente a decisão mais recente — só avançar se disser
explicitamente para parar/arquivar o projeto. **Se a resposta for
"licenciar B2B" ou "retomar pessoal", este plano NÃO se aplica** — este é
um plano de contingência, não o caminho default.

## Contexto para o executor

Mesmo contexto de paths/DBs/regras do plano de fixes
(`docs/plans/2026-07-20_plano_fixes.md`) — não repetido aqui. Este plano
só existe para deixar pronto **como decomissionar em segurança** se e
quando José decidir matar o projeto de vez, para que essa decisão não
fique bloqueada à espera de descobrir "o que é seguro desligar" — o audit
de 2026-07-20 já mapeou tudo, este plano só executa.

**IMPORTANTE — distinguir o que É e o que NÃO É deste projeto antes de
desligar qualquer coisa** (confirmado no audit de 2026-07-20):
- **É do ib_bot:** `ibgateway.service`, `xvfb-ibgw.service`,
  `ib-bot-v2-frontend.service`, `ib-backtests.timer`/`.service`,
  `ib-backtests-alert.service`, stack Docker `ib_bot` (7 containers),
  `lifeos-ib-refresh.timer` (mantém-se mesmo se o resto morrer — o José
  pediu explicitamente para manter o saldo na página do lifeos).
- **NÃO é do ib_bot** (não tocar mesmo dentro deste plano):
  `historical-backfill`, `execution-metrics`, `cost-recalibration`,
  `theta-learned` (são do Polymarket); `theta-terminal.service`,
  `paper-ironfly.timer` (são do repo `trading`, estudo 0006 já morto mas
  gerido à parte).

## Passo 1 — Exportar dump final da base de dados antes de qualquer desligamento

**Objetivo:** garantir que nada se perde antes de decomissionar — mesmo
um projeto morto merece um backup final legível.

**Comandos exatos:**

```bash
mkdir -p /home/servidor/Desktop/cursor-projects/ib_bot/archive
docker exec ib_bot-db-1 pg_dump -U ibbot -d ibbot --format=custom \
  --file=/tmp/ibbot_final_$(date +%Y%m%d).dump
docker cp ib_bot-db-1:/tmp/ibbot_final_$(date +%Y%m%d).dump \
  /home/servidor/Desktop/cursor-projects/ib_bot/archive/
```

**Oráculo de aceitação:**

```bash
ls -la /home/servidor/Desktop/cursor-projects/ib_bot/archive/ibbot_final_*.dump
pg_restore --list /home/servidor/Desktop/cursor-projects/ib_bot/archive/ibbot_final_*.dump | wc -l
```

Esperado: ficheiro existe, `pg_restore --list` lista >= 21 tabelas (as 21
confirmadas no audit de 2026-07-20).

**Rollback:** apagar o ficheiro de dump não afeta a DB viva (é só uma
cópia).

**Gotchas:** o dump fica dentro do repo git — **NÃO fazer commit dele**
(é potencialmente grande e não é código); adicionar `archive/*.dump` ao
`.gitignore` antes de qualquer `git add`.

## Passo 2 — Desligar os serviços do ib_bot, por ordem de menor para maior impacto

**Objetivo:** parar tudo sem perder o histórico nem quebrar o
`lifeos-ib-refresh` (que se mantém).

**Comandos exatos (correr um de cada vez, confirmar cada oráculo antes do próximo):**

```bash
# 2a. Timer semanal de backtests (já não há razão para recalcular nada)
sudo systemctl disable --now ib-backtests.timer

# 2b. Frontend (painel deixa de ser útil sem ninguém a decidir trades)
sudo systemctl disable --now ib-bot-v2-frontend.service

# 2c. Stack Docker (api/worker/beat/web/nginx; manter db+redis até ao passo 3)
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker compose stop api worker beat web nginx

# 2d. IB Gateway (já estava dormente, confirmar que continua)
systemctl is-active ibgateway.service xvfb-ibgw.service
# esperado: 'inactive' em ambos — se algum estiver 'active', investigar
# porque reativou antes de desligar (não assumir, verificar)
```

**NÃO desligar `lifeos-ib-refresh.timer`** — confirmar decisão do José
sobre isto especificamente antes de tocar (o audit de 2026-07-12/13 já
registou que este timer é independente do resto e o José pediu para
manter o saldo visível no lifeos).

**Oráculo de aceitação:**

```bash
systemctl is-active ib-backtests.timer ib-bot-v2-frontend.service
# esperado: 'inactive' em ambos
docker ps --format '{{.Names}}' | grep -c ib_bot
# esperado: 2 (só db + redis, se decidido manter os dados consultáveis)
```

**Rollback:**

```bash
sudo systemctl enable --now ib-backtests.timer
sudo systemctl enable --now ib-bot-v2-frontend.service
cd /home/servidor/Desktop/cursor-projects/ib_bot && docker compose start api worker beat web nginx
```

**Gotchas:** parar `db`/`redis` antes de confirmar que o dump do passo 1
está completo e legível seria irreversível para dados não capturados no
dump — sempre passo 1 antes do passo 2.

## Passo 3 — Congelar (não apagar) o repositório e a base de dados

**Objetivo:** deixar o histórico acessível para consulta futura sem custo
de manutenção contínua.

**Comandos exatos:**

```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
git tag -a "sunset-2026-07-XX" -m "Projeto arquivado por decisão do José — ver docs/audits/2026-07-20_audit_profundo.md"
git push origin "sunset-2026-07-XX"

# Parar db/redis SÓ DEPOIS de confirmar o passo 1 (dump) e o passo 3a (tag)
docker compose stop db redis
```

**Oráculo de aceitação:**

```bash
git tag -l "sunset-*"
docker ps --format '{{.Names}}' | grep -c ib_bot
```

Esperado: tag existe; `0` containers `ib_bot` a correr.

**Rollback:** `docker compose start db redis` (os volumes Docker não são
apagados por `stop`, só por `down -v` — nunca correr `down -v` neste
plano).

**Gotchas:** nunca correr `docker compose down -v` nem apagar volumes —
isso destruiria os dados mesmo tendo o dump (o dump é o backup, mas não
há razão para arriscar precisar de o restaurar).

## Passo 4 — Atualizar o Conductor e a memória para refletir o encerramento

**Objetivo:** o próximo agente que olhar para `ib_bot` vê imediatamente
que está arquivado, não pausado "à espera".

**Comandos exatos:**

```bash
psql conductor -c "UPDATE projects SET status='archived' WHERE slug='ib_bot'"
```

Usar a skill de memória para registar em `project_ib_bot.md`: data,
decisão do José, tag git de sunset, localização do dump final.

**Oráculo de aceitação:**

```bash
psql conductor -c "SELECT status FROM projects WHERE slug='ib_bot'"
```

Esperado: `archived`.

**Rollback:** `psql conductor -c "UPDATE projects SET status='paused' WHERE slug='ib_bot'"`
— reversível a qualquer momento (arquivar não é apagar).

**Gotchas:** nenhum — este é o único passo puramente informativo e
totalmente reversível do plano.
