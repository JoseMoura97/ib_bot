# Reconciliação do paper ledger — conta 2

Data da verificação: 2026-07-13. As timestamps da base de dados estão em UTC. A
investigação foi exclusivamente de leitura (`SELECT` na base `ibbot`, leitura do
código e dos logs retidos); não foi alterado qualquer saldo, ordem, trade ou
posição.

## Veredito

O saldo fecha aritmeticamente apenas se a conta tiver recebido **$70.000,00 de
crédito extra** além dos $100.000,00 iniciais. Os 138 fills ainda presentes são
internamente consistentes, mas a aplicação permite financiar a conta através de
um endpoint que altera `paper_cash.balance` sem criar um lançamento de funding.
Não existe uma tabela de depósitos/créditos nem um audit log histórico que
permita provar o instante, o autor ou o pedido que originou os $70.000.

**Curva paper marcada como não-evidência (motivo: crédito de $70.000 exigido
pela reconciliação, mas sem lançamento auditável de funding que prove origem,
data e autor).** Em particular, a curva anterior ao primeiro snapshot de
2026-05-26 não pode ser usada como evidência de performance.

## Equação do saldo

Valores obtidos diretamente de `paper_cash` e `paper_trades` para
`account_id = 2`:

| Componente | Linhas | Valor (USD) | Efeito em cash |
|---|---:|---:|---:|
| Saldo inicial declarado | — | 100.000,00000000 | +100.000,00000000 |
| Crédito sem ledger | — | 70.000,00000000 | +70.000,00000000 |
| BUY | 115 | 164.704,86288422 | −164.704,86288422 |
| SELL | 23 | 31.596,92996094 | +31.596,92996094 |
| Saldo armazenado | — | 36.892,06707671 | =36.892,06707671 |

Equação reproduzível:

```text
100000.00000000 + 70000.00000000 + 31596.92996094 - 164704.86288422
= 36892.06707672  (diferença sub-centavo de floating point face ao valor armazenado)
```

Sem o crédito, os trades implicam `-33107.93292329`. Invertendo a equação a
partir do saldo armazenado e do fluxo líquido dos trades resulta exatamente em
`170000.00000000` de cash disponível, isto é, $100.000 iniciais mais $70.000.

## Teste das quatro hipóteses

### 1. SELLs com sinal ou base errada — refutada

- As 138 linhas têm `value >= 0`.
- Em todas as 138, `value = quantity * price` dentro de `0.000001`.
- Os 23 SELLs totalizam $31.596,92996094 e o serviço soma esse valor ao cash;
  os 115 BUYs totalizam $164.704,86288422 e o serviço subtrai-o.
- Não há sinal invertido nem discrepância entre quantidade, preço e valor.

### 2. Rebalances a creditar cash sem trade correspondente — não detetada

- Existem 138 `paper_orders` FILLED e 138 `paper_trades`.
- O join por `paper_trades.order_id = paper_orders.id` dá 138 pares, zero
  orders sem trade, zero trades sem order e zero diferenças de ação,
  quantidade, preço ou valor.
- As quantidades atuais das 88 posições coincidem exatamente com
  `sum(BUY quantity) - sum(SELL quantity)` por ticker: zero mismatches e
  diferença absoluta total `0.00000000`.
- O caminho atual `place_market_order` altera cash, posição, order e trade na
  mesma transação. Não foi encontrada uma escrita de rebalance que credite
  cash isoladamente.

`paper_rebalance_logs` só contém 47 erros posteriores a 2026-05-27, todos com
zero orders, portanto não fornece um audit trail dos rebalances de fevereiro a
maio. Isso limita a prova histórica, mas não há no estado retido qualquer
cash-only rebalance que explique os $70.000.

### 3. Top-up manual de $70.000 — consistente, mas não demonstrável

O backend tem `POST /api/paper/accounts/{account_id}/fund`, que executa
diretamente:

```python
acct.balance = float(acct.balance) + float(body.amount)
```

O pedido exige um montante positivo, mas não insere uma linha num ledger de
funding. A base contém apenas as seis tabelas `paper_cash`, `paper_orders`,
`paper_positions`, `paper_trades`, `paper_rebalance_logs` e
`paper_snapshots`; nenhuma regista depósitos. O campo
`paper_cash.updated_at = 2026-05-09 03:45:13.754474` coincide com o último
batch de trades e, por isso, já não preserva a eventual timestamp do funding.

Um top-up de exatamente $70.000 é a explicação mais simples e compatível com a
equação, mas os dados retidos não permitem atribuí-lo a um pedido concreto. Os
logs atuais do API começam depois desse período; o nginx retido desde 9 de maio
não contém um `POST .../fund` antes do batch das 03:45, que também pode ter
entrado diretamente pelo API/worker. Logo, chamar-lhe top-up confirmado seria
mais forte do que a evidência.

### 4. Trades apagadas — sem evidência positiva; não excluível historicamente

Os IDs retidos vão de 1 a 495 com 357 gaps. Isto, isoladamente, não prova
deleção: sequências PostgreSQL não revertem valores quando uma transação falha,
e o serviço faz `flush()` de orders/trades antes de um eventual rollback. Os
IDs são contíguos dentro dos batches bem-sucedidos de 19 e 26 de fevereiro e 9
de maio; os gaps ficam entre batches.

Além disso, orders, trades e posições sobreviventes fecham 1:1 e em quantidade.
Não há uma marca de deleção nem um audit log imutável, portanto não é possível
excluir que dados tenham sido apagados antes da retenção atual, mas não existe
evidência observável de que trades apagadas expliquem os $70.000.

## Consultas de reprodução

Executar apenas contra a stack v1 canónica:

```sql
SELECT account_id, action, count(*), sum(value)
FROM paper_trades
WHERE account_id = 2
GROUP BY account_id, action;

SELECT
  round(balance::numeric, 8) AS stored_cash,
  round(sum(CASE WHEN action='SELL' THEN value ELSE -value END)::numeric, 8)
    AS recorded_net_flow,
  round((balance - sum(CASE WHEN action='SELL' THEN value ELSE -value END))::numeric, 8)
    AS required_opening_cash,
  round((balance - sum(CASE WHEN action='SELL' THEN value ELSE -value END) - 100000)::numeric, 8)
    AS unexplained_credit
FROM paper_cash c
JOIN paper_trades t ON t.account_id = c.id
WHERE c.id = 2
GROUP BY c.balance;
```

Resultado esperado da segunda consulta:

```text
stored_cash   = 36892.06707671
net_cash_flow = -133107.93292329
opening_cash  = 170000.00000000
extra_credit  = 70000.00000000
```
