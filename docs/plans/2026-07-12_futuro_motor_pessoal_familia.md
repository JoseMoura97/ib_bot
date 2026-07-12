# Plano futuro — Motor pessoal/família ("path A") em modo mínimo — 2026-07-12

**GATE DE ARRANQUE**: só começa quando TODO o plano de fixes estiver verde (em especial os
Passos 1, 2 e 6) E o José disser explicitamente que quer usar o painel outra vez. Verificar
com: `ss -tlnp | grep 5900 | grep -v 127.0.0.1 | wc -l` → 0 (VNC fechado) e
`git -C /home/servidor/Desktop/cursor-projects/ib_bot status --porcelain | wc -l` → <10.

## Contexto para o executor

- **O que é o "path A"**: dos 4 caminhos que o audit v4 ranqueou, o A é usar o motor já
  construído como ferramenta PESSOAL de gestão (do José/família), sem clientes, sem RIA
  (Registered Investment Adviser — o registo de consultor financeiro exigido nos EUA quando
  se gere dinheiro de terceiros; gerir o próprio dinheiro não precisa). Custo: semanas, não
  meses. O produto já tem: catálogo de 56 estratégias com backtests, paper trading, página
  Deploy com verificação pré-trade, circuit breakers, e suporte a fractional shares.
- **Aviso honesto embutido** (tem de aparecer no painel): os backtests do catálogo NÃO batem
  o mercado depois de ajustar à sorte — o valor aqui é DISCIPLINA e execução barata de uma
  carteira que o José escolha (ex.: rebalancear uma carteira de ETFs), não "alpha".
- **Money-path**: QUALQUER ordem real continua gated: `ReadonlyLogin=yes` no gateway só sai
  com decisão explícita do José via `request_user_approval` (Telegram one-tap), e mesmo assim
  `ENABLE_LIVE_TRADING/LIVE_DRY_RUN/LIVE_ALLOWED_ACCOUNTS` têm de ser armados no compose —
  ver memória `project_ib_bot.md` (gotchas de go-live).

### Passo 1 — Religar o mínimo: 1 stack + 1 frontend + gateway em modo paper primeiro

**Objetivo**: ambiente utilizável em 1 tarde, sem tocar em dinheiro real.

**Comandos**:
```bash
cd /home/servidor/Desktop/cursor-projects/ib_bot && docker compose up -d
sudo systemctl enable --now ib-bot-v2-frontend.service   # :3001
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3001/
```
(Gateway live só é preciso para cotações IB e ordens; para paper com preços yfinance não é.)

**Oracle de aceitação**: `curl http://127.0.0.1:8001/strategies/catalog | head -c 200` devolve
JSON; o painel :3001 abre no browser do José.

**Rollback**: `docker compose down` + `sudo systemctl disable --now ib-bot-v2-frontend.service`.

**Gotchas**: depois do merge do Passo 6 dos fixes, rebuild obrigatório (`docker compose build
api worker beat`) — o código é copiado na build, não montado.

### Passo 2 — Definir COM o José a carteira-alvo e correr 4 semanas em paper

**Objetivo**: uma carteira escolhida por ele (ex.: 3-5 ETFs, rebalance mensal) carregada como
portfolio no painel, com paper allocation e snapshots diários a provar o comportamento.

**Oracle de aceitação**: 20+ snapshots diários da nova alocação em `paper_snapshots`
(query: `SELECT count(*) FROM paper_snapshots WHERE portfolio_id='<novo>'`) e desvio máximo
vs alvo <2% nos dias de rebalance.

**Rollback**: apagar a alocação paper (é fictícia).

**Gotchas**: usar carteiras com poucos nomes líquidos (o audit de maio provou que carteiras
de 400 tickers não funcionam com contas pequenas); a conta live do bot tem €1.000 — qualquer
teste live futuro precisa de fractional shares ativado na conta IB (permissão nunca
verificada).

### Passo 3 — (Opcional, gated) primeiro trade real de teste

**Objetivo**: SÓ se José pedir: armar o caminho live (tirar read-only, flags de compose,
allowlist da conta) e executar UM rebalance pequeno com aprovação one-tap.

**Oracle de aceitação**: `SELECT count(*) FROM ib_trades` passa de 0 para >0; relatório de
execução (slippage por leg) entregue a José.

**Rollback**: repor `ReadonlyLogin=yes` + flags off + `docker compose up -d` (desarma tudo).

**Gotchas**: seguir o checklist do verify engine (`POST /live/rebalance/verify?mode=live`) —
ele deteta o erro 321 (read-only), mercado fechado, spreads. Mercado US abre 10:30 ART.
Reconciliação pós-trade é o ponto fraco conhecido (gap D do audit v2) — conferir posições
manualmente no fim.
