# Plano Futuro 1/3 — Decisão de negócio sobre o arquivo PIT (2026-09-14)

**Gate de arranque:** só começa quando o Passo 0 do `2026-09-14_plano_fixes.md` estiver verde —
verificar com:
```bash
ls -la /home/servidor/.claude/projects/-home-servidor/memory/ | grep -i "ib_bot.*decisao"
```
Se não existir um ficheiro de memória com a resposta do José sobre o destino do arquivo PIT, **não
avances** — volta a apresentar a pergunta do passo 0, não presumas uma direção. Esta é a 6ª vez
que este plano é escrito (07-12, 07-20/08-10, 08-24, 08-31, 09-07, agora 09-14) — se o gate
continuar fechado na próxima auditoria, o achado a reportar deixa de ser "decisão pendente" e
passa a ser "processo de pedir decisão não está a funcionar, precisa de canal diferente".

## Contexto para o executor

O arquivo "ponto-no-tempo" (PIT — *point-in-time*, uma "fotografia" diária de dados públicos que
nunca muda depois de guardada) cresce ~11 linhas/dia desde 13 de julho de 2026, sem que exista uma
decisão de negócio sobre o que fazer com ele. Está em `altdata_snapshots` (Postgres, container
`ib_bot-db-1`) e é replicado para fora da máquina por `ib-altdata-backup.timer` (commits
`backup(altdata): PIT table ...` neste repo). Em 2026-09-14 tinha **701 linhas, 64 dias
distintos**, 11 fontes de dados (CFTC, FINRA, FRED, House disclosure ×2, SEC ×2, Nasdaq,
USAspending, 13F Berkshire, 13F Scion). Isto tem valor real (não se pode reconstruir um dia
passado depois de a fonte mudar), mas também custo real (armazenamento crescente, engenharia de
manutenção, atenção do José em cada audit).

Três caminhos possíveis, cada um com objetivo e critério de sucesso diferentes — **este plano só
executa o caminho que o José escolher no passo 0 do plano de fixes**, não decide por ele.

## Fase A — Se a decisão for "vender/licenciar dados" (produto B2B tipo Unusual Whales/Quiver)

**Objetivo:** validar se há procura real ANTES de construir mais nada — o plano Conductor
`3702771c` ("ib_bot → Alt-Data Product") já foi tentado e ficou `superseded`; não repetir sem
evidência nova de procura.

**Passos:**
1. Listar 5-10 potenciais compradores/parceiros (fundos pequenos, boletins de investimento,
   agregadores de dados alternativos) e mandar uma mensagem de validação de procura (não um
   produto construído) perguntando se pagariam por acesso PIT a estas 11 fontes.
2. Só avançar para construir uma API de venda se ≥2 respostas positivas concretas (interesse real,
   não cortesia) forem recebidas em 30 dias.
3. Se sim: nova fase de engenharia (fora deste plano) para expor `altdata_snapshots` via API paga,
   com rate limiting e autenticação — dimensionar noutro ciclo.
4. Se não: voltar ao passo 0 do plano de fixes com a resposta "procura validada como insuficiente,
   qual dos outros dois caminhos preferes?".

**Oráculo de aceitação da Fase A:** existe um registo (memória ou ficheiro) com as respostas
recebidas e a contagem de interesse real, datado, antes de qualquer código novo ser escrito.

## Fase B — Se a decisão for "arquivar e desligar"

**Objetivo:** parar de gastar engenharia/atenção num arquivo sem destino, preservando os dados já
capturados (não apagar histórico).

**Comandos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
# 1. Exportar snapshot final completo antes de qualquer desligamento:
docker exec ib_bot-db-1 pg_dump -U ibbot -d ibbot -t altdata_snapshots --data-only \
  > .archive/altdata_snapshots_final_$(date +%Y%m%d).sql
git add .archive/altdata_snapshots_final_*.sql
git commit -m "chore: snapshot final de altdata_snapshots antes de arquivar (decisão José 2026-09-XX)"

# 2. Desligar os timers (NÃO apagar a tabela nem o container db):
sudo systemctl disable --now ib-altdata-backup.timer
sudo systemctl disable --now ib-altdata-qa.timer
```

**Oráculo de aceitação da Fase B:**
```bash
systemctl is-active ib-altdata-backup.timer ib-altdata-qa.timer
# esperado: "inactive" para ambos
ls -la .archive/altdata_snapshots_final_*.sql
# esperado: ficheiro existe e não está vazio
```

**Rollback:** `sudo systemctl enable --now ib-altdata-backup.timer ib-altdata-qa.timer` — os dados
continuam na tabela, só o timer para de correr; nada é destruído.

## Fase C — Se a decisão for "continuar a acumular, sem produto, só por precaução"

**Objetivo:** documentar explicitamente esta decisão (que É uma decisão válida, não é ausência de
decisão) para que a próxima auditoria pare de reportar isto como "achado crítico".

**Comandos:**
```bash
cat > /home/servidor/.claude/projects/-home-servidor/memory/reference_ib_bot_pit_decisao_$(date +%Y%m%d).md << 'EOF'
# Decisão José — arquivo PIT ib_bot (data: preencher)
José decidiu CONTINUAR a acumular o arquivo PIT sem produto B2B definido, por precaução/opcionalidade
futura. Custo aceite: ~11 linhas/dia, replicação diária, sem decisão de venda. Revisitar em
[data futura, ex: 3-6 meses] ou se aparecer procura orgânica.
EOF
```

**Oráculo de aceitação da Fase C:** o ficheiro de memória existe com a data de hoje e é referenciado
em `MEMORY-trading.md`.

**Gotchas gerais (todas as fases):** nunca apagar linhas de `altdata_snapshots` sem exportação
prévia confirmada — é dado histórico não reconstruível (a promessa do PIT é exatamente essa: não
pode ser recriado depois).
