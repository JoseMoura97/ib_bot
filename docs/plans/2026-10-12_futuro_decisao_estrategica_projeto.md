# Plano Futuro — Decisão estratégica: retomar, encerrar formalmente, ou manter dormente o IB Bot

**Gate de arranque:** só começar quando o `2026-10-12_plano_fixes.md` estiver 100% verde E o
`2026-10-12_futuro_decisao_arquivo_pit.md` tiver uma decisão registada (qualquer uma das 3
opções) — verificar com:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot && git log --oneline -10
grep -n "outreach B2B\|arquivar.*PIT\|continuar sem decidir" \
  /home/servidor/.claude/projects/-home-servidor/memory/MEMORY-trading.md
```
→ ambos devem mostrar evidência de conclusão antes de levantar este plano com o José.

## Contexto para o executor

Depois de 12 auditorias semanais seguidas (07-12 a 10-12), o `ib_bot` está num estado estável mas
estagnado: nenhuma das 56 estratégias testadas tem edge estatístico real (Deflated Sharpe Ratio,
maio 2026), o único candidato promissor fora do catálogo (estudo 0006, iron-fly earnings-vol) foi
morto em julho com forward-test real, e não há nenhum plano Conductor ativo para o slug `ib_bot`
desde 2026-09-15 (quase um mês). O projeto continua a gastar: armazenamento (PIT archive),
disco (imagens Docker), e atenção (12 auditorias semanais a documentar o mesmo estado). Isto não
é sustentável indefinidamente sem uma decisão explícita.

Este plano NÃO propõe uma resposta — propõe forçar a decisão e executar a consequência.

## Passo 1 — Montar o dossier de decisão (3 opções reais, com custo e evidência)

**Objetivo:** apresentar ao José um resumo de uma página com as 3 opções, cada uma com o que
custa manter e o que ganharia ao escolher.

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot

# Quanto está a ser gasto hoje em manutenção (tempo de auditoria, disco, etc.)
ls docs/audits/*.md | wc -l   # número de auditorias semanais já feitas
du -sh .git backups/altdata_snapshots
docker system df

# Resultado completo das 56 estratégias (o veredito mais recente)
cat docs/*investibilidade*.md 2>/dev/null | tail -100   # ajustar nome exato se diferente
grep -rl "Deflated Sharpe" docs/ 2>/dev/null

# Estado do estudo 0006 (repo irmão)
cat /home/servidor/Desktop/cursor-projects/trading/studies/0006-earnings-vol/forward_30events.md | tail -30
```

**As 3 opções a apresentar:**
1. **Encerramento formal** — parar TODOS os timers (`ib-altdata-backup`, `ib-altdata-qa`,
   `ib-backtests`), arquivar o repositório (tag final + export de dados), documentar o projeto
   como "fechado, sem edge encontrado" em memória permanente. Ganho: zero manutenção futura,
   atenção liberada. Perda: se um dia aparecer uma ideia nova de estratégia, tem de se recomeçar
   do arquivo (mas o arquivo PIT, se mantido fora do git — ver plano da decisão PIT — continua
   disponível).
2. **Dormência continuada (status quo)** — manter exatamente como está: backtests semanais
   (de graça, sem risco), PIT archive diário, paper trading, sem decisão de negócio. Ganho:
   opção aberta sem custo de decisão imediato. Perda: continua a consumir auditoria semanal e
   armazenamento sem destino declarado.
3. **Nova rodada de busca de edge, com critério pré-registado mais estrito** — só se houver uma
   ideia nova e específica (não revisitar as 56 já reprovadas nem o 0006 já morto); exigiria um
   plano Conductor novo, com critério de kill pré-registado ANTES de ver os dados (como foi feito
   bem no estudo 0006), para não repetir o erro de "testar 56 e escolher a que parece melhor"
   que já reprovou pelo Deflated Sharpe Ratio.

**Oracle de aceitação:** uma frase do José escolhendo 1, 2, ou 3. Sem isto, não avançar para o
passo 2.

**Rollback:** nenhum (passo de comunicação).

**Gotchas:** não enquadrar isto como urgente — não há risco de dinheiro real em nenhuma das 3
opções. O valor deste passo é forçar uma decisão consciente em vez de deixar o "status quo por
omissão" (opção 2) acontecer só porque nunca foi formalmente escolhida.

## Passo 2 — Executar a consequência técnica da decisão

**Se escolher opção 1 (encerramento formal):**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
sudo systemctl disable --now ib-altdata-backup.timer ib-altdata-qa.timer ib-backtests.timer
git tag -a ib_bot-encerramento-$(date +%Y%m%d) -m "Encerramento formal: nenhuma das 56 estratégias \
tem edge real (Deflated Sharpe Ratio, maio 2026); estudo 0006 morto (forward-test, julho 2026). \
Decisão do José em $(date +%Y-%m-%d)."
git push origin --tags
```
**Oracle de aceitação:**
```bash
systemctl is-enabled ib-altdata-backup.timer ib-altdata-qa.timer ib-backtests.timer
git tag -l "ib_bot-encerramento-*"
```
→ todos os timers `disabled`; tag existe.

**Se escolher opção 2 (dormência continuada):** nenhuma ação técnica — registar em memória a data
desta decisão e uma data de revisão sugerida (ex.: +90 dias) para a próxima auditoria não tratar
isto como "ainda sem decisão" indefinidamente.

**Se escolher opção 3 (nova busca de edge):** não é um passo técnico deste plano — abrir um plano
Conductor novo e dedicado (`conductor jobs add` ou equivalente, com dono explícito), citando o
critério de kill pré-registado como requisito de aceitação da fase 1. Este plano futuro TERMINA
aqui; o novo plano Conductor é que assume a partir daqui.

**Rollback (opção 1):**
```bash
sudo systemctl enable --now ib-altdata-backup.timer ib-altdata-qa.timer ib-backtests.timer
```

**Gotchas:**
- Encerrar os timers NÃO apaga dados — `ib_bot-db-1` continua a existir com tudo lá dentro, a
  menos que se decida explicitamente apagar o container/volume (não recomendado sem backup
  confirmado primeiro).
- Se a opção 1 for escolhida, considerar também parar os containers Docker
  (`docker compose down`) depois de confirmar que não há nada a perder — isto libera ~27 GB de
  imagens "vivas" imediatamente. Fazer isto só depois do tag + push estarem confirmados.
