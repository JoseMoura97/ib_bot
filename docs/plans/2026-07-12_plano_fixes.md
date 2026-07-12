# Plano de fixes — IB Bot — 2026-07-12

## Contexto para o executor (lê isto primeiro; assume que não viste mais nada)

- **Projeto**: IB Bot — robô de investimento ligado à Interactive Brokers ("IB", uma
  corretora de ações). Está PAUSADO: não negoceia dinheiro real (nunca negociou — a tabela
  `ib_orders` tem 0 linhas), mas deixou muita infraestrutura ligada.
- **Paths**: repo principal `/home/servidor/Desktop/cursor-projects/ib_bot` (branch atual
  `snapshots-exec-fixes`); worktrees `/home/servidor/Desktop/cursor-projects/ib_bot-v2`
  (branch frontend-v2) e `.../ib_bot-altdata-wt` (branch alt-data-consolidation). Estudo de
  opções 0006 vive noutro repo: `/home/servidor/Desktop/cursor-projects/trading`.
- **DBs**: Postgres dentro de containers Docker — `ib_bot-db-1` (user `ibbot`, db `ibbot`;
  aceder com `docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "..."`) e `ib_bot-v2-db-1`
  (idêntico, quase vazio). Conductor: `psql conductor` no host.
- **Credenciais** (ONDE estão, nunca copiar valores): login IB no `/opt/ibc/config.ini` e
  no `.env` do ibeam em `/home/servidor/Desktop/cursor-projects/ib_bot/infra/ibeam/`;
  ThetaData em `/home/servidor/thetadata/creds.txt`. NUNCA imprimir estes ficheiros inteiros
  em logs/chats.
- **Regras duras**: (1) qualquer ação de dinheiro real (ordens, transferências) é PROIBIDA
  sem aprovação one-tap via Telegram (`request_user_approval`) — este plano não tem nenhuma;
  (2) todo o edit é commitado NO MESMO turno; (3) compute pesado vai por
  `runjob [--mem 24G] [--cpu N] -- CMD`; (4) parar/alterar serviços systemd exige `sudo` —
  são mudanças de infra JÁ AUTORIZADAS por este plano aprovado, mas se algo parecer diferente
  do descrito (drift), pára e escala.
- **Displays em ART (UTC-3); timestamps de DB em UTC.**
- Os findings citados (C1, A1…) são do audit
  `/home/servidor/Desktop/cursor-projects/ib_bot/docs/audits/2026-07-12_audit_profundo.md`.

---

### Passo 1 — Fechar o VNC sem password (finding C1) — FAZER PRIMEIRO

**Objetivo**: o x11vnc do IB Gateway deixa de aceitar ligações de fora da própria máquina.

**Comandos** (o x11vnc é lançado pelos scripts do IBC; primeiro localizar onde):
```bash
grep -rn "x11vnc" /opt/ibc/scripts/ /etc/systemd/system/ibgateway.service 2>/dev/null
```
No ficheiro onde aparecer `x11vnc -display :1 -bg -nopw -listen 0.0.0.0 ...` (esperado:
um script chamado por `/opt/ibc/scripts/displaybannerandlaunch.sh` ou o unit), editar a linha
para escutar só em localhost:
```bash
sudo sed -i 's/-listen 0\.0\.0\.0/-listen 127.0.0.1/' <FICHEIRO_ENCONTRADO>
```
(Se quiser manter acesso remoto ao ecrã, a alternativa correta é `-rfbauth` com ficheiro de
password criado com `x11vnc -storepasswd` — mas localhost-only chega: acede-se por túnel SSH.)
Depois reiniciar SÓ o gateway (isto vai disparar um login live com 2FA — normal):
```bash
sudo systemctl restart ibgateway.service
```

**Oracle de aceitação**:
```bash
ss -tlnp | grep 5900
```
Output esperado: linha com `127.0.0.1:5900` (e NENHUMA com `0.0.0.0:5900` ou `[::]:5900`).
E o gateway volta a autenticar: `ss -tlnp | grep 4001` mostra a porta 4001 em escuta
(pode demorar ~2-3 min após restart).

**Rollback**: reverter o sed (trocar `127.0.0.1` por `0.0.0.0` no mesmo ficheiro) e
`sudo systemctl restart ibgateway.service`.

**Gotchas**: se o Passo 2 (dormência) for executado no mesmo dia, este passo continua a valer
a pena — o unit fica corrigido para quando alguém o voltar a ligar. O restart do gateway
dispara o 2FA-bot; verificar no journal (`journalctl -u ibgateway -n 50`) que o login passou.
Se a 2FA falhar repetidamente (>3 tentativas), PARAR e escalar a José — não insistir (risco
de lockout da conta IB).

---

### Passo 2 — Modo dormência: desligar as sessões live e o backtest semanal (A1, M2)

**Objetivo**: zero logins live automáticos na IB e zero compute semanal, mantendo os dados.
⚠️ Decisão embutida (já tomada no audit, confirmar com José só se ele reagir): o
`lifeos-ib-refresh.timer` (projeto lifeos) usa o ibeam para ler o saldo diário — ao desligar
o ibeam, esse refresh começa a falhar. É aceitável (saldo fica stale no lifeos); se José
quiser manter, ver o gotcha no fim.

**Comandos**:
```bash
# 1) parar e desativar o IB Gateway e os seus acessórios
sudo systemctl disable --now ibgateway.service xvfb-ibgw.service ib-socat.service ibgw-watchdog.service
# 2) parar a segunda sessão live (ibeam / Client Portal)
cd /home/servidor/Desktop/cursor-projects/ib_bot/infra/ibeam && docker compose down
# 3) matar o ibeam_starter avulso se ainda existir
pkill -f "python ibeam_starter.py" || true
# 4) desligar o backtest semanal
sudo systemctl disable --now ib-backtests.timer
```

**Oracle de aceitação**:
```bash
systemctl is-active ibgateway.service xvfb-ibgw.service ib-socat.service ibgw-watchdog.service ib-backtests.timer; docker ps --format '{{.Names}}' | grep -c ibeam; ss -tlnp | grep -E ':4001|:4003|:5900' | wc -l
```
Output esperado: cinco linhas `inactive` (ou `failed`→depois `inactive`), `0` containers
ibeam, `0` portas 4001/4003/5900 em escuta.

**Rollback**:
```bash
sudo systemctl enable --now xvfb-ibgw.service ibgateway.service ib-socat.service ibgw-watchdog.service ib-backtests.timer
cd /home/servidor/Desktop/cursor-projects/ib_bot/infra/ibeam && docker compose up -d
```

**Gotchas**: (a) NÃO tocar em `theta-learned/historical-backfill/execution-metrics/
cost-recalibration` — são do Polymarket, não deste projeto. (b) NÃO tocar em
`paper-ironfly.timer`/`options-cache.timer` neste passo — decisão no Passo 5. (c) Se José
quiser manter o saldo diário no lifeos: manter APENAS o ibeam ligado (saltar o sub-passo 2)
e desligar o resto na mesma — o ibeam não usa GUI nem o 2FA-bot de pixels. (d) O
`ibgw-watchdog` manda alertas quando a 4001 cai — desativá-lo JUNTO com o gateway, senão
spamma alertas.

---

### Passo 3 — Ligar o arquivo point-in-time `altdata_snapshots` (A3)

**Objetivo**: começar finalmente a gravar, uma vez por dia, o estado atual de cada fonte de
alt-data (vintages) na tabela `altdata_snapshots` — o único ativo que compõe valor com o
projeto parado.

**Comandos** (investigar primeiro o que já existe — a tabela foi criada por algum código):
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
grep -rn "altdata_snapshots" --include='*.py' . | head -20
```
Dois cenários:
- **(3a) Já existe um task/endpoint que grava e está desligado** → localizar (provável em
  `backend/app/` como task Celery) e agendar: adicionar entrada ao beat schedule OU criar
  timer systemd no host que chama o endpoint/script 1×/dia. Deploy: `docker compose build api
  worker beat && docker compose up -d api worker beat` (o código é copiado na build, ver
  memória do projeto).
- **(3b) Não existe writer** → escrever script standalone `scripts/snapshot_altdata.py` no
  repo que: para cada fonte gratuita já integrada (EDGAR 13F, FINRA short, CFTC COT,
  USASpending, congress trades), puxa o estado atual usando os módulos existentes
  (`quiver_signals.py` e afins) e insere linhas `(source, as_of_date, payload_json)` na
  tabela. Agendar com timer systemd diário 06:00 UTC. Não precisa do IB Gateway nem de
  ThetaData — fontes são web públicas.

Commit no mesmo turno (branch atual):
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot && git add -A scripts/ backend/ && git commit -m "feat(altdata): daily point-in-time snapshots (audit A3)"
```

**Oracle de aceitação** (no dia seguinte ao deploy, ou após disparo manual do job):
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc "SELECT count(*), max(created_at) FROM altdata_snapshots"
```
Output esperado: count > 0 e `max(created_at)` = hoje. Correr 2 dias seguidos e ver o count a
crescer diariamente.

**Rollback**: desativar o timer/beat entry; os dados gravados ficam (são só INSERTs).

**Gotchas**: cuidado com rate limits das fontes (EDGAR pede User-Agent identificado); payloads
grandes → gravar JSON comprimido ou por fonte/dia; NUNCA usar a Quiver API paga sem confirmar
que a subscrição ainda existe (o audit não a verificou).

---

### Passo 4 — Explicar o delta +$70.000 do paper ledger (M1)

**Objetivo**: descobrir por que o cash da conta paper 2 é $36.892 quando as trades implicam
−$33.108, e deixar a explicação escrita (ou marcar a curva como não-fiável).

**Comandos** (só SELECTs):
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT action, count(*), sum(value::numeric) FROM paper_trades WHERE account_id=2 GROUP BY action"
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT * FROM paper_orders ORDER BY id LIMIT 20"
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT * FROM paper_rebalance_logs ORDER BY id DESC LIMIT 20"
grep -rn "paper_cash\|update.*cash\|deposit" /home/servidor/Desktop/cursor-projects/ib_bot/paper_trading.py /home/servidor/Desktop/cursor-projects/ib_bot/backend/app --include='*.py' -i | head -30
```
Hipóteses a testar por esta ordem: (1) `paper_trades.value` de SELLs gravado com sinal/base
errada; (2) rebalances que creditam cash sem trade correspondente; (3) top-up manual de $70k
em maio; (4) trades apagadas. Escrever o veredito em
`docs/audits/2026-07-12_paper_ledger_reconciliacao.md` e commitar.

**Oracle de aceitação**: o documento existe, com uma equação que fecha:
`100000 + Σcréditos − Σdébitos = 36892.07` linha a linha, OU a frase "curva paper marcada
como não-evidência (motivo: X)".

**Rollback**: n/a (só leitura + 1 doc).

**Gotchas**: `paper_trades.account_id` pode ser NULL nas linhas antigas — verificar a que
conta pertencem antes de somar.

---

### Passo 5 — Forward test do iron-fly: corrigir ou parar (parte de A2)

**Objetivo**: o `paper-ironfly.timer` (repo `trading`) regista 0 eventos desde 28-mai porque
o universo do snapshot cache não cobre os nomes com earnings. Ou se corrige o universo, ou
se pára o timer — não fica a correr para o vazio.

**Comandos** (diagnóstico):
```bash
journalctl -u paper-ironfly.service --since '2026-06-01' | grep funnel | tail -10
wc -l /home/servidor/Desktop/cursor-projects/trading/live/options_cache/universe.txt
grep -n "not_in_snap_universe\|universe" /home/servidor/Desktop/cursor-projects/trading/live/options_cache/paper_ironfly.py | head
```
**Fix preferido**: alargar o universo do `options-cache` aos nomes com earnings próximos —
o snapshot.py já tem "earnings-soon augmentation" (ver README em
`trading/live/options_cache/`); investigar porque é que os 16/19 eventos ficam de fora
(provável: a augmentation só entra no cache DEPOIS do evento, ou a liquidez filtra). Corrigir,
commitar no repo `trading` (branch atual), e validar no dia seguinte.
**Se não houver fix em <1 dia de trabalho**: `sudo systemctl disable --now paper-ironfly.timer
options-cache.timer` e escrever no phase-status do estudo que o forward test foi suspenso.

**Oracle de aceitação** (fix): dentro de 7 dias,
```bash
ls /home/servidor/Desktop/cursor-projects/trading/data/options_cache/paper_ironfly_ledger.parquet && journalctl -u paper-ironfly.service -n 5 | grep -E "logged [1-9]"
```
Output esperado: o ficheiro existe e pelo menos um run com `logged N` (N≥1).
(alternativa "parar": `systemctl is-active paper-ironfly.timer` → `inactive`.)

**Rollback**: reativar os timers (`sudo systemctl enable --now ...`).

**Gotchas**: earnings season é por ondas — se a semana não tiver earnings de nomes líquidos,
o oracle pode demorar; validar com o funnel (o `not_in_snap_universe` deve cair para ~0).

---

### Passo 6 — Arrumar o repo (M3) + gitignore do lixo ibeam

**Objetivo**: árvore limpa, lixo fora do controlo de versão, fixes preservados.

**Comandos**:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
printf 'infra/ibeam/outputs/\n' >> .gitignore
git rm -r --cached infra/ibeam/outputs 2>/dev/null || true
git add .gitignore && git commit -m "chore: ignore ibeam outputs (712 ficheiros de screenshots/logs)"
git status --porcelain | wc -l   # ver o que sobra e commitá-lo ou descartá-lo conscientemente
```
Depois, decisão de branch (levar a José só se houver conflito): `snapshots-exec-fixes` tem os
fixes de 29-jun — fazer merge para `main` quando os testes passarem:
```bash
git checkout main && git merge snapshots-exec-fixes && git push origin main
```

**Oracle de aceitação**: `git -C /home/servidor/Desktop/cursor-projects/ib_bot status --porcelain | wc -l` → < 10; `git log main -1` inclui o commit de 29-jun (`25f7a6a` como ancestral).

**Rollback**: `git merge --abort` em caso de conflito; o gitignore é inócuo.

**Gotchas**: NÃO apagar `infra/ibeam/outputs/` do disco sem confirmar que ninguém precisa dos
logs para debug do ibeam; ignorar ≠ apagar. O container api foi construído do `main` antigo —
depois do merge, `docker compose build api worker beat && docker compose up -d` SE a stack
ainda estiver ligada (se o Passo 7 a desligar, saltar).

---

### Passo 7 — Reduzir para 1 stack Docker (M4)

**Objetivo**: desligar a stack `ib_bot-v2` (Plan B, porta 8092) e o frontend público :3002;
manter a stack v1 (API 8001 + web 8090) e o frontend :3001 — que é o que o José usa —
OU desligar tudo se o José não abrir o painel há semanas (perguntar-lhe 1 vez via canal
normal; default = manter v1).

**Comandos** (variante default):
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot-v2 && docker compose down
sudo systemctl disable --now ib-bot-v2-frontend-public.service
```

**Oracle de aceitação**:
```bash
docker ps --format '{{.Names}}' | grep -c 'ib_bot-v2'; ss -tlnp | grep -c ':8092\|:3002'; curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3001/
```
Output esperado: `0`, `0`, `200` (o frontend 3001 continua a servir).

**Rollback**: `cd /home/servidor/Desktop/cursor-projects/ib_bot-v2 && docker compose up -d;
sudo systemctl enable --now ib-bot-v2-frontend-public.service`.

**Gotchas**: o frontend :3001 fala com a API :8001 da stack V1 — confirmar que se desliga a
v2 e não a v1 (os nomes enganam: o frontend "v2" usa a API "v1"). A DB `ib_bot-v2-db-1` está
praticamente vazia (paper_trades=0) — não se perde nada.

---

### Passo 8 — Atualizar o estado no conductor e nas memórias

**Objetivo**: a frota deixa de ver informação errada (projeto "active"; estudo 0006
"survivor" sem a contradição multiregime).

**Comandos**: via MCP conductor (ou psql se autorizado): marcar projeto `ib_bot` como
`paused`; adicionar knowledge ao DM ib_bot com o link deste audit; editar
`/home/servidor/.claude/projects/-home-servidor/memory/project_earnings_vol.md`
acrescentando o resultado multiregime (PF<0,4 todos os anos, por reconciliar) e
`project_ib_bot.md` com o estado de dormência. Commit da memória não se aplica (fora de repo).

**Oracle de aceitação**: `psql conductor -tAc "SELECT status FROM projects WHERE slug='ib_bot'"`
→ `paused`; `grep -c "multiregime" .../project_earnings_vol.md` ≥ 2 (agora com o resultado).

**Rollback**: repor status `active`.

**Gotchas**: escritas na DB do conductor podem estar restringidas — usar as ferramentas MCP
do conductor em vez de UPDATE direto se possível.
