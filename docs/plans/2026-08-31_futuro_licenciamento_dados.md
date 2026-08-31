# Plano Futuro — Explorar Licenciamento/Venda B2B do Arquivo PIT (2026-08-31)

## Gate de arranque (OBRIGATÓRIO — não começar sem isto)

**Só começa quando o José escolher explicitamente a opção 1 ("continuar a acumular + explorar
venda/licenciamento") no Passo 0/1 do `docs/plans/2026-08-31_plano_fixes.md`, E revogar
explicitamente o HOLD atual da fase `a1_altdata_b2b`.**

Verificar com:
```bash
psql conductor -c "SELECT id,status,metadata FROM project_plans WHERE slug='ib_bot' AND id='e36e04ec-de9c-438f-b0e5-434dfa391154'"
grep -rl "ib_bot" /home/servidor/.claude/projects/-home-servidor/memory/ | xargs grep -l "B2B.*reabrir\|revogar.*HOLD\|licenciamento.*aprovado" 2>/dev/null
```
O plano `e36e04ec`, fase `a1_altdata_b2b`, tem uma nota explícita e ainda válida a 2026-08-31:
**"B2B em HOLD. NÃO reabrir, NÃO voltar a cardar, NÃO fazer qualquer contacto comercial."** —
este plano futuro NÃO pode arrancar sem uma revogação explícita e datada dessa nota pelo José,
registada em memória. Isto não é opcional — é a regra mais forte encontrada nesta linha do
projeto em 3 auditorias seguidas.

## Contexto para o executor

O ib_bot mantém, desde 2026-07-13, um arquivo diário "ponto-no-tempo" (PIT) de 11 fontes de dados
públicas (compras do Congresso, filings 13F, dados de curto (short) da FINRA, posicionamento de
futuros da CFTC, contratos governamentais do USAspending, etc.). A 2026-08-31 tem 548 linhas,
50 dias distintos. Os entregáveis técnicos de uma eventual venda/licenciamento já existem
(exports com 51.967 linhas, one-pager em `docs/altdata_b2b_one_pager_draft.md`), mas a decisão
comercial ficou em HOLD explícito desde julho — este plano só serve para retomar isso SE e
QUANDO o José decidir.

**Paths absolutos:**
- Repo: `/home/servidor/Desktop/cursor-projects/ib_bot`
- One-pager já preparado: `docs/altdata_b2b_one_pager_draft.md`
- Arquivo PIT: tabela `altdata_snapshots` em `ib_bot-db-1` (Postgres).

**Credenciais:** nenhuma nova. Contacto comercial (se aprovado) usaria canais pessoais do José,
fora deste repo.

**Regras:**
- **Qualquer contacto comercial externo (email, chamada, proposta) exige aprovação explícita do
  José antes de cada contacto individual** — não é um "routine next step" automatizável, é
  decisão de negócio com exposição reputacional/legal (ver nota RIA no glossário do audit).
  Não simplificar para "já tenho autorização geral" — a nota de HOLD é explícita sobre "NÃO fazer
  qualquer contacto comercial" até revogação.
- Este plano é sobre **preparação e validação**, não sobre fechar vendas sozinho.

---

## Passo 1 — Validar frescura e integridade dos entregáveis técnicos já preparados

**Objetivo:** confirmar que o one-pager e os exports de 51.967 linhas ainda refletem o estado
atual do arquivo (que cresceu de 471→548 linhas desde a última vez que isto foi revisto).

**Comandos exatos:**
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot
cat docs/altdata_b2b_one_pager_draft.md
docker exec ib_bot-db-1 psql -U ibbot -d ibbot -c "SELECT count(*), min(as_of_date), max(as_of_date), count(distinct source) FROM altdata_snapshots"
git log -1 --format="%ad" -- docs/altdata_b2b_one_pager_draft.md
```

**Oráculo de aceitação:** confirmação escrita (comentário no próprio ficheiro ou nota em
`docs/audits/`) de que os números no one-pager (contagem de linhas, período coberto, número de
fontes) batem com o estado atual da tabela, ou uma lista do que precisa de atualização.

**Rollback:** não aplicável, é validação read-only.

**Gotchas:** não atualizar o one-pager com dados novos sem também atualizar a data de "última
verificação" no topo do documento — um one-pager desatualizado é pior que nenhum.

---

## Passo 2 — Mapear potenciais compradores/licenciadores SEM contactar ninguém

**Objetivo:** preparar uma lista curta (5-10 nomes) de potenciais interessados (fundos
quantitativos pequenos, newsletters de investimento, agregadores de dados alternativos tipo
Quiver/Unusual Whales que o audit v4 já identificou como concorrência de referência) — pesquisa,
sem contacto.

**Comandos exatos:** usar o skill `search` ou `research` para levantar potenciais
compradores/licenciadores de dados "alt-data" de baixo volume (11 fontes, ~50 dias de histórico
por agora) — não é um comando de shell, é trabalho de pesquisa.

**Oráculo de aceitação:** documento `docs/altdata_b2b_potential_buyers_<data>.md` com 5-10 nomes,
para cada um: por que poderia interessar, que fonte(s) do arquivo seria mais relevante, e
estimativa de dimensão (pequeno/médio/grande) — SEM qualquer contacto feito.

**Rollback:** não aplicável.

**Gotchas:** **NÃO contactar ninguém nesta fase.** O objetivo é ter a lista pronta para quando o
José aprovar o próximo passo (contacto), não acelerar sozinho.

---

## Passo 3 — Apresentar ao José a lista + pedir aprovação explícita para o primeiro contacto

**Objetivo:** entregar o trabalho de preparação e obter uma decisão pontual e explícita (por
contacto, não um "sim" geral) antes de qualquer avanço comercial.

**Comandos exatos:** nenhum — é uma conversa/mensagem direta ao José, citando o Passo 1 e 2.

**Oráculo de aceitação:** resposta explícita do José por contacto proposto, registada em memória
(`/memory`) com data e nome do interessado.

**Rollback:** não aplicável.

**Gotchas:** se o José não responder num prazo razoável, NÃO avançar sozinho — isto tem exposição
reputacional/legal (dados derivados de fontes públicas, mas empacotados e vendidos, pode ter
implicações regulatórias tipo RIA dependendo do modelo comercial escolhido — sinalizar isso
explicitamente na apresentação ao José, não decidir por ele).
