# Iron Wing + cobertura de dados — relatório final (2026-07-13)

## /tldr

A recolha está operacional e não depende de market data da Interactive Brokers: 9/9 fontes foram gravadas, duas execuções consecutivas foram idempotentes, há uma única agenda externa (Celery, 05:00 UTC) e foram feitas **0 chamadas IB, 0 ordens e 0 subscrições**.

O headline antigo do Iron Wing misturava duas populações. Os eventos BMO foram classificados duas vezes; a string já normalizada `BMO` caiu no default AMC e deslocou entrada/saída um dia. Isso torna inválido o resultado combinado. O bug **piora** o headline, não cria o alpha: a amostra AMC válida continua positiva. Com held-out 2023+ e comissão round-trip de $5,20, AMC dá PF 1,801 / retorno médio +15,40% a slip 0,10 e PF 1,475 / +10,01% a slip 0,25. Os BMO deslocados dão PF 0,837 / -1,02% e PF 0,520 / -3,69%. Não há dados Theta locais para reparar os BMO: 0/1296 entradas corretas do dia anterior.

Decisão: **não pagar os $80/mês da ThetaData agora e não colocar a estratégia live**. O forward corrigido já registou três eventos reais dos snapshots locais, mas N=3 é apenas diagnóstico. Continuar a recolha grátis e reavaliar quando houver amostra forward material.

## Evidência histórica reconciliada

Dados usados, sem pedidos à Theta/IB:

- Theta intraday local: 15.172 ficheiros, 3.264 eventos, 174 símbolos, 2020-01-22 a 2026-05-21.
- EOD multi-regime local: 3.692 eventos, 157 símbolos, 2019-02-12 a 2026-05-21.
- Intersecção: 2.579 eventos / 157 símbolos.

### Auditoria do bug BMO

O script recalculou a divisão a partir do `when` original e das chains em disco; não são números copiados sem prova.

| Amostra held-out 2023+ | N | Retorno médio | PF | Win rate |
|---|---:|---:|---:|---:|
| AMC válida, slip 0,10 | 530 | +18,53% | 1,986 | 63,21% |
| AMC válida, slip 0,25 | 531 | +13,27% | 1,643 | 61,21% |
| AMC + $5,20 comissão, slip 0,10 | 531 | +15,40% | 1,801 | 62,71% |
| AMC + $5,20 comissão, slip 0,25 | 531 | +10,01% | 1,475 | 59,51% |
| BMO inválida/deslocada, slip 0,10 | 347 | -1,02% | 0,837 | 60,52% |
| BMO inválida/deslocada, slip 0,25 | 347 | -3,69% | 0,520 | 51,59% |

A origem é concreta: o builder transformava o texto bruto em `BMO`, depois chamava novamente `_classify_when("BMO")`; como o classificador reconhecia `before` mas não o token literal `BMO`, caía em AMC. Há 1.750 BMO e 1.514 AMC no dataset; 1.296 BMO estão no held-out. A busca aos nomes de ficheiro corretos do dia útil anterior encontrou 0/1296, logo o lado BMO não pode ser reconstituído honestamente com o histórico atual.

### Porque o EOD parecia contradizer o intraday

Não era a mesma trade:

- só 5,35% usam a mesma expiração;
- DTE mediano: intraday 3 dias versus EOD 16;
- mesma entrada 25,55%; mesma saída 52,85%; diferença ATM mediana $2,50;
- correlação de retorno no overlap a slip 0,25: 0,425;
- spread EOD/credit mediano 17,89%, p75 36,15%, p90 74,64%.

O EOD repriced a mid fica PF 1,187 e +2,17% médio (N=2.207), mas a execução a slip 0,25 cai para PF 0,170 e -21,34% (N=2.278). Portanto o EOD serve como aviso de execução/liquidez; não invalida automaticamente a amostra AMC intraday, mas impede tratá-la como pronta para live.

## Forward corrigido

O código de forward foi fechado no repo `trading`, commit `b98e15041`:

- classificação robusta BMO/AMC;
- snapshot mais próximo de 15:45 ET para entrada e saída;
- entrada por crédito e saída por débito com touch correto (shorts ao ask, longs ao bid);
- comissão 0,052 quote = $5,20 round trip;
- alerta de snapshots stale independente do funnel;
- calendário Dolt faz `fetch` + `ff-only`, recusa working tree suja e tem timeout; prova real `up_to_date` em 4,396 s;
- 18/18 testes passaram.

Prova offline pós-fix, 0 IB / 0 ordens:

| Evento | Timing | Ret mid | Ret touch |
|---|---|---:|---:|
| GIS BMO | ~15:45 ET | -41,54% | -70,66% |
| PEP BMO | ~15:45 ET | -14,91% | -28,64% |
| DAL BMO | ~15:45 ET | +42,70% | +19,88% |

Agregado N=3 (apenas diagnóstico): mid -4,58% médio, PF 0,757, win 33,3%; touch -26,47% médio, PF 0,200, win 33,3%. `touch <= mid` nos três eventos. Isto reforça esperar por mais forward e não comprar dados já.

## Cobertura diária sem pacing da IB

As duas execuções reais de 2026-07-13 deram 9/9 fontes, 9 linhas de vintage na base e rerun `exists` para todas:

| Fonte | Linhas | Uso / limitação principal |
|---|---:|---|
| Nasdaq Symbol Directory | 12.991 | universo, exchange, ETF/status |
| Yahoo OHLCV/actions (Iron Wing) | 3.332 | preço/corporate actions; feed best-effort |
| FINRA short volume | 6.352 | contexto off-exchange; não é short interest |
| House disclosure index | 1.340 | descoberta de documentos; **só metadata**, não holdings/transações completas |
| SEC daily material filings | 1.066 | eventos corporativos; fonte opcional com budget de 3 pedidos |
| FRED regimes | 240 | SPX, VIX, rates, crédito e dólar |
| USAspending awards | 100 | contratos públicos recentes |
| SEC 13F Scion | 3 | holdings; transação independente |
| SEC 13F Berkshire | 90 | holdings; transação independente |

O SEC agora para no primeiro 403 como `optional_external_403`, com timeouts 3/8 s e no máximo três business days. A falha fica no audit, mas não torna vermelho um run em que todas as fontes obrigatórias passaram. Scion e Berkshire são isoladas: uma falha não reverte a outra.

Quiver Congress foi excluído explicitamente: o bulk endpoint licenciado/pago fez timeout. O House index não é apresentado como substituto equivalente. A agenda única é `altdata_snapshot_daily_task` às 05:00 UTC; os units redundantes `equity-coverage.*` foram removidos e não estão instalados.

## Validação e decisão operacional

- Collector: 10/10 testes; inclui NaN estrito, idempotência, SEC 403 imediato, budget, criticalidade/exit code, isolamento 13F e agenda única.
- Trading forward: 18/18 testes no commit `b98e15041`.
- Reconciliação: 3m43s, exit 0, todos os valores históricos esperados recomputados e verificados.
- Runtime: worker e beat recriados com as imagens corrigidas; task registada; única agenda confirmada.
- Safety: 0 IB requests, 0 ordens, 0 compras/subscrições.

Próximo gate: acumular pelo menos uma primeira amostra forward material (30+ eventos como checkpoint, separada AMC/BMO), reportar mid e touch depois de comissão, e só então decidir se uma subscrição Theta acrescenta valor. Até lá: **collector ligado, paper ligado, live desligado**.
