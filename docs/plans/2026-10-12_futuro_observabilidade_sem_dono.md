# Plano Futuro — Dar dono formal (Conductor) aos achados críticos deste projeto pausado

**Gate de arranque:** só começar quando o Passo 1-3 do `2026-10-12_plano_fixes.md` estiver verde
(a correção do `insufficient cash` publicada e confirmada) — verificar com:
```bash
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc \
  "SELECT status FROM paper_rebalance_logs WHERE account_id = 2 ORDER BY timestamp DESC LIMIT 1;"
```
→ diferente de `ERROR`.

## Contexto para o executor

Padrão observado em 12 auditorias semanais seguidas: um achado crítico é identificado numa
auditoria, repetido na seguinte sem correção, e só é corrigido quando um operador humano (não um
plano Conductor formal) decide priorizá-lo manualmente — o bug de 45 dias (`tuple index out of
range`) só foi corrigido horas depois de uma auditoria o sinalizar; o `insufficient cash` já leva
14+ dias sem essa sorte. **Não há nenhum plano Conductor ativo para `ib_bot` desde 2026-09-15.**
Isto significa que não há nenhum mecanismo automático (fora da auditoria semanal manual) que
force a atenção de alguém para problemas abertos neste projeto pausado.

Este plano propõe fechar esse gap: um mecanismo leve e barato de "watchdog" que avisa quando um
achado crítico do audit continua aberto por mais de N dias, sem depender da próxima auditoria
semanal manual aparecer.

## Passo 1 — Criar um script de verificação do estado crítico conhecido

**Objetivo:** um script simples, read-only, que verifica os 2 sinais mais informativos de saúde
do projeto (erro de `insufficient cash` na conta 2; decisão PIT pendente) e falha com exit != 0 se
algo estiver crítico há mais de N dias.

**Comandos exatos:**
```bash
mkdir -p /home/servidor/Desktop/cursor-projects/ib_bot/scripts
cat > /home/servidor/Desktop/cursor-projects/ib_bot/scripts/check_critical_findings.sh << 'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

DAYS_THRESHOLD="${1:-3}"

# Sinal 1: paper_rebalance_logs da conta 2 com ERROR nos últimos N dias consecutivos
ERROR_DAYS=$(docker exec ib_bot-db-1 psql -U ibbot -d ibbot -tAc "
  SELECT count(*) FROM paper_rebalance_logs
  WHERE account_id = 2 AND status = 'ERROR'
    AND timestamp >= now() - interval '${DAYS_THRESHOLD} days';
")

if [ "${ERROR_DAYS}" -ge "${DAYS_THRESHOLD}" ]; then
  echo "CRITICAL: paper_rebalance conta 2 em ERROR há >= ${DAYS_THRESHOLD} dias (${ERROR_DAYS} ocorrências)"
  exit 1
fi

echo "OK: nenhum achado crítico conhecido há mais de ${DAYS_THRESHOLD} dias"
exit 0
SCRIPT
chmod +x /home/servidor/Desktop/cursor-projects/ib_bot/scripts/check_critical_findings.sh
```

**Oracle de aceitação:**
```bash
/home/servidor/Desktop/cursor-projects/ib_bot/scripts/check_critical_findings.sh 3
echo "exit code: $?"
```
→ hoje (antes do fix do passo 1-3 do plano de fixes), esperado `exit code: 1` com a mensagem
CRITICAL — confirma que o script deteta corretamente o problema real e conhecido. Depois do fix
publicado, correr de novo e confirmar `exit code: 0`.

**Rollback:**
```bash
rm /home/servidor/Desktop/cursor-projects/ib_bot/scripts/check_critical_findings.sh
```

**Gotchas:** o script é deliberadamente read-only (só `SELECT`) — nunca deve escrever na BD nem
tocar em código de execução.

## Passo 2 — Ligar o script a um timer semanal com alerta para o Conductor

**Objetivo:** correr o script automaticamente e, se falhar, avisar o Domain Manager `ib_bot` no
Conductor (o mesmo padrão já usado por `ib-backtests-alert.service` e `ib-altdata-qa-alert.service`
neste mesmo repositório — reutilizar o padrão, não inventar um novo).

**Comandos exatos:**
```bash
sudo tee /etc/systemd/system/ib-critical-findings-check.service > /dev/null << 'EOF'
[Unit]
Description=IB Bot weekly check for known critical findings still open
OnFailure=ib-critical-findings-alert.service
[Service]
Type=oneshot
WorkingDirectory=/home/servidor/Desktop/cursor-projects/ib_bot
ExecStart=/home/servidor/Desktop/cursor-projects/ib_bot/scripts/check_critical_findings.sh 3
EOF

sudo tee /etc/systemd/system/ib-critical-findings-alert.service > /dev/null << 'EOF'
[Unit]
Description=Alert ib_bot DM when a known critical finding stays open too long
[Service]
Type=oneshot
ExecStart=/usr/local/bin/conductor api-failure --project ib_bot --service critical-findings \
  --detail "Achado critico conhecido (ver docs/audits) continua aberto ha >= 3 dias" \
  --hint "Correr scripts/check_critical_findings.sh e ler o audit mais recente em docs/audits/" \
  --cooldown-min 1440 --notify-only
EOF

sudo tee /etc/systemd/system/ib-critical-findings-check.timer > /dev/null << 'EOF'
[Unit]
Description=Twice-weekly check for open critical findings in ib_bot
[Timer]
OnCalendar=Mon,Thu 09:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ib-critical-findings-check.timer
```

**Oracle de aceitação:**
```bash
systemctl is-enabled ib-critical-findings-check.timer
sudo systemctl start ib-critical-findings-check.service
journalctl -u ib-critical-findings-check.service -n 5
```
→ timer `enabled`; a corrida manual mostra o resultado do script (CRITICAL ou OK consistente com
o passo 1).

**Rollback:**
```bash
sudo systemctl disable --now ib-critical-findings-check.timer
sudo rm /etc/systemd/system/ib-critical-findings-check.service \
        /etc/systemd/system/ib-critical-findings-alert.service \
        /etc/systemd/system/ib-critical-findings-check.timer
sudo systemctl daemon-reload
```

**Gotchas:**
- Este timer é **adicional** à auditoria semanal manual — não a substitui. O objetivo é reduzir o
  tempo entre "um achado crítico aparece" e "alguém é avisado", de até 7 dias (ciclo de auditoria)
  para até 3-4 dias.
- `--cooldown-min 1440` (24h) evita espetar o Conductor com o mesmo alerta duas vezes no mesmo dia
  se o timer disparar mais de uma vez por engano.
- Se o José decidir pela opção 1 (encerramento formal) no plano
  `2026-10-12_futuro_decisao_estrategica_projeto.md`, desativar este timer também nesse momento
  (não tem sentido vigiar um projeto formalmente encerrado).
