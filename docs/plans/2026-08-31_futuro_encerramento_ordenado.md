# Plano Futuro — Encerramento Ordenado do IB Bot (2026-08-31)

## Gate de arranque (OBRIGATÓRIO — não começar sem isto)

**Só começa quando o José escolher explicitamente a opção 3 ("desligar tudo e arquivar") no
Passo 0/1 do `docs/plans/2026-08-31_plano_fixes.md`, OU quando o plano
`2026-08-31_futuro_busca_edge_dormente.md` terminar com veredito negativo (nenhuma das ~30
estratégias 13F sobrevive ao Deflated Sharpe Ratio) e o José confirmar que quer encerrar depois
dessa 4ª tentativa falhada.**

Verificar com:
```bash
grep -rl "ib_bot" /home/servidor/.claude/projects/-home-servidor/memory/ | xargs grep -l "encerrar\|arquivar.*ib_bot\|opção 3" 2>/dev/null
cat /home/servidor/Desktop/cursor-projects/ib_bot/docs/audits/2026-08-31_13f_veredito.md 2>/dev/null   # se existir, ler a conclusão
```

## Contexto para o executor

O ib_bot é um sistema de trading que, depois de 4 tentativas independentes de encontrar edge
(56 estratégias originais, PEAD, earnings-vol/Iron Wing, e potencialmente as 13F dormentes),
nunca confirmou uma vantagem estatística robusta que sobreviva a testes rigorosos (Deflated
Sharpe Ratio + holdout). Trading ao vivo já está desligado desde julho de 2026. Este plano
existe para o dia em que o José decidir que não vale a pena manter a infraestrutura a correr
(backtest semanal, arquivo diário, dois frontends, stack Docker completa) sem uma via ativa de
uso.

**Importante: "encerramento ordenado" não significa apagar dados.** O arquivo PIT
(`altdata_snapshots`) tem valor histórico único e irreversível — uma vez perdido um dia sem
captura, não há forma de o reconstruir. Este plano preserva tudo, só desliga o que consome
compute/atenção sem retorno.

**Paths absolutos:**
- Repo: `/home/servidor/Desktop/cursor-projects/ib_bot`
- Worktree secundário: `/home/servidor/Desktop/cursor-projects/ib_bot-v2`
- Backups offsite do arquivo PIT: verificar destino exato com
  `systemctl cat ib-altdata-backup.service` (script `infra/scripts/backup_altdata_snapshots.sh`)
  antes de desligar o timer.

**Credenciais:** nenhuma nova.

**Regras:**
- **Qualquer passo que mexa em `ibgateway.service`/`xvfb-ibgw.service` já está inativo — não
  precisa de ação, mas confirmar que continua `disabled` no fim.**
- Parar timers/serviços é reversível (systemd guarda o estado `enabled`/`disabled` e os dados na
  DB não são apagados) — mas fazer 1 passo de cada vez com oráculo de aceitação entre eles, nunca
  um `systemctl disable --now` em massa sem verificar cada serviço individualmente.
- **NÃO apagar volumes Docker (`ib_bot-db-1` guarda a DB) nem a tabela `altdata_snapshots`** —
  o objetivo é parar de GERAR dados novos e libertar compute, não destruir o histórico já
  capturado.
- Fazer commit no mesmo turno de qualquer mudança de código/config.

---

## Passo 1 — Congelar o arquivo PIT no seu estado atual (parar de capturar, preservar tudo)

**Objetivo:** parar os 3 timers do ib_bot (`ib-altdata-qa`, `ib-altdata-backup`, `ib-backtests`)
sem apagar nada, deixando o arquivo com a sua última fotografia completa.

**Comandos exatos:**
```bash
# 1. Confirmar estado atual e última captura bem-sucedida ANTES de desligar
systemctl list-timers ib-altdata-qa.timer ib-altdata-backup.timer ib-backtests.timer
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT max(as_of_date), count(*) FROM altdata_snapshots"

# 2. Garantir que existe pelo menos 1 backup offsite recente ANTES de parar o backup
ls -la /home/servidor/Desktop/cursor-projects/ib_bot/backups/ | tail -5   # ou o destino real confirmado no unit file

# 3. Desligar os timers (não os serviços diretamente — os timers são o que dispara)
sudo systemctl disable --now ib-altdata-qa.timer
sudo systemctl disable --now ib-altdata-backup.timer
sudo systemctl disable --now ib-backtests.timer
```

**Oráculo de aceitação:**
```bash
systemctl list-timers ib-altdata-qa.timer ib-altdata-backup.timer ib-backtests.timer
# deve devolver "0 timers listed" ou mostrar os 3 como inactive/disabled
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT count(*) FROM altdata_snapshots"
# deve mostrar o MESMO número de linhas de antes de desligar (nenhuma perda)
```

**Rollback:** `sudo systemctl enable --now ib-altdata-qa.timer ib-altdata-backup.timer
ib-backtests.timer` — reativa tudo, próxima captura no horário normal.

**Gotchas:** desligar PRIMEIRO o backup só depois de confirmar que existe um backup offsite
recente (< 24h) — nunca deixar o arquivo sem pelo menos 1 cópia fora do host antes de parar de o
proteger ativamente.

---

## Passo 2 — Desligar a stack Docker duplicada e o worktree secundário

**Objetivo:** parar de gastar RAM/CPU numa segunda cópia completa do sistema (api/worker/beat/
db/redis/nginx/web) que já não vai receber trabalho novo depois do Passo 1.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# 1. Fazer um dump final da DB ANTES de parar (mesmo já tendo backups automáticos)
docker exec ib_bot-db-1 pg_dump -U ibbot ibbot | gzip > /home/servidor/Desktop/cursor-projects/ib_bot/backups/final_dump_$(date +%Y%m%d).sql.gz

# 2. Parar a stack Docker (não remover — `stop`, não `down -v`)
docker compose -f docker-compose.prod.yml stop

# 3. Parar o frontend systemd também, se a decisão for "arquivar completamente"
#    (só se o José confirmar que não quer sequer consultar dashboards antigos)
sudo systemctl disable --now ib-bot-v2-frontend.service
```

**Oráculo de aceitação:**
```bash
ls -la /home/servidor/Desktop/cursor-projects/ib_bot/backups/final_dump_*.sql.gz   # existe, tamanho > 0
docker ps --filter "name=ib_bot"   # nenhum "Up"
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001   # connection refused (se Passo 2.3 feito)
```

**Rollback:** `docker compose -f docker-compose.prod.yml start` restaura a stack; se os dados
tiverem sido perdidos por engano, `gunzip -c final_dump_<data>.sql.gz | docker exec -i
ib_bot-db-1 psql -U ibbot -d ibbot` restaura a partir do dump.

**Gotchas:** NUNCA usar `docker compose down -v` (o `-v` apaga os volumes, incluindo a base de
dados Postgres). Usar sempre `stop`.

---

## Passo 3 — Documentar o encerramento para auditorias futuras

**Objetivo:** deixar um registo claro de que o projeto foi encerrado deliberadamente (não
abandonado por negligência), para que uma auditoria futura não trate isto como um problema.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
cat > docs/ENCERRAMENTO_2026.md << 'EOF'
# IB Bot — Encerramento ordenado (data a preencher)

Decisão do José: <citar a decisão exata e a data>.

O que ficou:
- Base de dados Postgres (`ib_bot-db-1`, container parado mas volume preservado) com todo o
  histórico: 56+ estratégias testadas, arquivo PIT completo (`altdata_snapshots`), curva de
  paper trading de <preencher> dias.
- Dump final: `backups/final_dump_<data>.sql.gz`.
- Este repositório git, com todas as auditorias e planos em `docs/audits/` e `docs/plans/`.

O que foi desligado: timers de captura/backup/backtest, stack Docker, frontend systemd.

Se algum dia quiseres retomar: `docs/plans/2026-08-31_plano_fixes.md` e as auditorias em
`docs/audits/` têm o estado completo do sistema no momento do encerramento.
EOF
git add docs/ENCERRAMENTO_2026.md
git commit -m "docs: registar encerramento ordenado do ib_bot"
```

**Oráculo de aceitação:** `git log -1 --stat` mostra o commit com `docs/ENCERRAMENTO_2026.md`
adicionado; `psql conductor -c "UPDATE project_plans SET status='archived' WHERE slug='ib_bot'
AND id='e36e04ec-de9c-438f-b0e5-434dfa391154'"` NÃO é permitido correr sem confirmação do José
(escrita na DB do Conductor não é uma das escritas autorizadas por este plano — apenas sinalizar
ao José que o status do plano no Conductor devia ser atualizado manualmente por ele ou por um
agente com essa autorização explícita).

**Rollback:** `git revert <hash>` remove o documento; os serviços parados no Passo 1/2 continuam
reversíveis pelos rollbacks descritos aí.

**Gotchas:** este passo é só documentação — não reativar nem desativar mais nada aqui.
