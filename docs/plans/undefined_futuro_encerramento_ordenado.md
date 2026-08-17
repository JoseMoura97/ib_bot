# Plano Futuro 3 — Encerramento ordenado (só se o José decidir parar de vez)

## Gate de arranque (obrigatório)

**Só começar quando o Passo 2 do `docs/plans/undefined_plano_fixes.md` estiver concluído E o
José tiver escolhido explicitamente a opção 3 (desligar tudo) na conversa desse passo.**
Verificar com:
```bash
psql conductor -c "SELECT metadata->>'decisao_continuidade' FROM project_plans WHERE id='04bf8af8-6614-4f12-9d57-772f7af2b67d'"
```
Tem de conter "encerramento"/"kill"/equivalente registado pelo José. **Este plano nunca deve
correr por iniciativa própria de um agente — é o mais irreversível dos três futuros e precisa
da decisão mais explícita.**

## Contexto para o executor

Se o José decidir que nem o licenciamento de dados (Plano Futuro 1) nem a busca de edge
dormente (Plano Futuro 2) valem o esforço contínuo, a alternativa correta não é "deixar tudo a
correr sozinho para sempre" (isso é o que já está a acontecer e é o problema descrito no
finding ALTO #2 do audit) — é desligar de forma ordenada, preservando tudo o que tem valor
arquivístico (o dataset PIT, os relatórios de backtest, as memórias/decisões) e só então parar
os timers.

**Isto NÃO apaga a conta real da Interactive Brokers nem mexe na posição BRK B (€27.247,71,
70 ações) — essa é uma posição pessoal do José, fora do escopo deste projeto, e este plano
nunca a toca.**

## Passo 1 — Exportar o arquivo PIT completo para um destino frio (fora do Docker)

**Objetivo:** garantir que os dados acumulados (394+ dias-fonte a 2026-08-17) sobrevivem ao
encerramento dos containers.

**Comandos exatos:**
```bash
mkdir -p /home/servidor/archives/ib_bot_final_$(date +%Y%m%d)
docker exec ib_bot-db-1 pg_dump -U ibbot -d ibbot --format=custom \
  --file=/tmp/ib_bot_final_dump.pgdump
docker cp ib_bot-db-1:/tmp/ib_bot_final_dump.pgdump \
  /home/servidor/archives/ib_bot_final_$(date +%Y%m%d)/ib_bot_final_dump.pgdump
sha256sum /home/servidor/archives/ib_bot_final_$(date +%Y%m%d)/ib_bot_final_dump.pgdump
```

**Oráculo de aceitação:** o ficheiro `.pgdump` existe, tem tamanho > 0, e um restore de teste
para uma base scratch confirma `count(*)` de `altdata_snapshots` igual ao count vivo no momento
do dump (mesmo procedimento já provado no gate H1 do plano `04bf8af8` — reutilizar
`docs/altdata_restore_drill.md` como referência de comando exato).

**Rollback:** nenhum necessário (só cria uma cópia, não apaga nada).

**Gotchas:** confirmar que o backup offsite diário (`ib-altdata-backup.timer`) já tem uma cópia
recente antes de assumir que este dump é a ÚNICA cópia — não é, é uma cópia extra para um
destino "frio" fora de qualquer serviço automático.

## Passo 2 — Desligar os timers e serviços, por esta ordem exata

**Objetivo:** parar tudo sem perder o estado a meio de uma escrita.

**Comandos exatos:**
```bash
# 1. Parar primeiro os timers (não deixam nova escrita começar)
sudo systemctl disable --now ib-altdata-qa.timer ib-altdata-backup.timer ib-backtests.timer \
  theta-learned.timer lifeos-ib-refresh.timer

# 2. Confirmar que nenhuma tarefa está a meio (dar 5 min de folga)
systemctl list-jobs

# 3. Só depois, parar a stack Docker
cd /home/servidor/Desktop/cursor-projects/ib_bot
docker compose -f docker-compose.prod.yml down

# 4. Parar o frontend systemd
sudo systemctl disable --now ib-bot-v2-frontend.service
```

**Oráculo de aceitação:** `systemctl list-timers` já não mostra nenhum dos timers acima;
`docker ps` já não mostra nenhum container `ib_bot-*`; `curl localhost:3001` e
`curl localhost:8090` devolvem erro de ligação.

**Rollback:** `docker compose -f docker-compose.prod.yml up -d` + `sudo systemctl enable --now
<cada unit>` — reativa tudo; os dados na base Docker (volume persistente) não são apagados por
`down` sem `-v`, portanto o rollback é seguro e não perde histórico.

**Gotchas:**
- **NUNCA usar `docker compose down -v`** (o `-v` apaga os volumes, incluindo a base de dados
  Postgres com os 394+ dias de arquivo) — usar sempre `down` sem `-v`.
- Confirmar que `ibgateway.service` e `xvfb-ibgw.service` já estão `inactive` (deviam estar,
  desde 2026-07-12/13) — se por algum motivo estiverem ativos, isso é um finding a reportar
  antes de continuar, não algo a corrigir silenciosamente dentro deste plano.

## Passo 3 — Registar o encerramento em memória e fechar o plano no Conductor

**Objetivo:** deixar rasto claro para qualquer auditoria futura de que o encerramento foi
deliberado, com data, motivo e localização do dump final.

**Comandos exatos:** usar a skill `/memory` para gravar um novo bloco em
`project_ib_bot.md` com: data do encerramento, motivo (decisão do José, link para a conversa),
caminho do dump final (`/home/servidor/archives/ib_bot_final_<data>/...`), e o hash SHA256.

Depois:
```bash
psql conductor -c "UPDATE project_plans SET status='done' WHERE id='04bf8af8-6614-4f12-9d57-772f7af2b67d' AND status='executing'"
```
(Só correr este UPDATE depois de confirmar com o José — é a única escrita na base do Conductor
em todo este documento, e só serve para fechar o plano formalmente, não para mexer em dinheiro
ou trading.)

**Oráculo de aceitação:** memória atualizada e visível por
`grep -A5 "encerramento" /home/servidor/.claude/projects/-home-servidor/memory/project_ib_bot.md`;
`psql conductor -c "SELECT status FROM project_plans WHERE id='04bf8af8-...'"` devolve `done`.

**Rollback:** reverter o `UPDATE` com `status='executing'` se o encerramento for revertido no
Passo 2 (rollback).

**Gotchas:** nunca apagar o repositório git nem o remoto do GitHub — mesmo depois de
encerrado, o código e o histórico ficam como está, só os serviços vivos param.
