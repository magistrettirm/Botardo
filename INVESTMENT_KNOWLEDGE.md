# Botardo - Base de Conocimiento de Inversiones

> Documento consolidado con toda la investigacion realizada el 2026-03-18.
> Fuentes: 8 libros de trading, papers academicos, estrategias de top traders,
> y analisis especifico del contexto argentino.

---

## PARTE 1: PRINCIPIOS FUNDAMENTALES (de 8 libros clave)

### 1.1 Las 10 Reglas de Oro (sintesis cross-libro)

| Regla | Fuente |
|-------|--------|
| Risk management > estrategia | Market Wizards, Chan, Taleb, Graham |
| Proceso > resultado | Annie Duke, Taleb, Mark Douglas |
| Pensar en probabilidades, no certezas | Duke, Douglas, Taleb, Chan |
| Survivorship bias: estudiar fracasos, no solo exitos | Taleb, Malkiel |
| Disciplina emocional mata al talento | Douglas, Schwager |
| Humildad sobre modelos/predicciones | Simons (Renaissance), Taleb |
| Evitar la ruina a toda costa | Taleb, Graham (margin of safety), Chan (Kelly) |
| Sistematico > discrecional | Simons, Chan, Douglas |
| Diversificar | Graham, Malkiel, Taleb (Barbell) |
| El mercado no es racional | Graham (Mr. Market), Duke, Taleb |

### 1.2 Kelly Criterion — La Formula Clave

**Formula**: `f* = (b*p - q) / b`
- f* = fraccion del capital a arriesgar
- b = ratio ganancia/perdida
- p = probabilidad de ganar
- q = 1 - p

**Formula alternativa para trading**: `Kelly% = W - [(1 - W) / R]`
- W = win rate, R = avg_win / avg_loss

**REGLA: Siempre usar Kelly fraccionado**:
- Half-Kelly (0.5): captura ~75% del crecimiento con ~25% de la volatilidad
- Quarter-Kelly (0.25): conservador, para capital chico
- 0.10-0.15x Kelly: lo que usan fondos institucionales

**Dato clave**: Apostar 30% del Kelly optimo reduce la chance de drawdown 80% de 1-en-5 a 1-en-213, reteniendo 51% del crecimiento.

### 1.3 Risk of Ruin — El Numero Mas Importante

**Formula clasica**: `RoR = ((1-p)/p) ^ (B/S)`
- p = win prob, B = bankroll, S = bet size

**Tabla critica de position sizing**:

| Risk por trade | 10 losses seguidos | Drawdown |
|---|---|---|
| 1% | Si | 9.6% (recuperable) |
| 2% | Si | 18.3% (manejable) |
| 5% | Si | 40.1% (peligroso) |
| 10% | Si | 65.1% (casi fatal) |

**Targets profesionales**: RoR < 5% (traders), < 1% (institucional).

**Con $60 de bankroll y 5% risk por trade = $3 por trade. Con $60 y 2% = $1.20 por trade.**

### 1.4 Drawdown y Recovery — La Asimetria Fatal

| Drawdown | Recovery necesario |
|----------|-------------------|
| 10% | 11% |
| 20% | 25% |
| 30% | 43% |
| 50% | 100% |
| 75% | 300% |

**Triple Penance Rule**: Recovery time = 2-3x la duracion del drawdown.

### 1.5 Sharpe Ratio — El Benchmark

| Sharpe | Interpretacion |
|--------|----------------|
| < 0 | Estas perdiendo |
| 0-1.0 | Sub-optimo |
| 1.0-2.0 | Bueno |
| 2.0-3.0 | Excelente |
| > 3.0 | Excepcional (sospechoso si se sostiene) |

**Referencia**: Medallion Fund de Renaissance = Sharpe > 2.0 con 66% retorno anual.
**Clave de Chan**: Si Sharpe >= 2, ni siquiera una desviacion estandar te deja en negativo en el anio.

### 1.6 La Estrategia Barbell de Taleb

- **85-95%** en activos ultra-seguros (cash, bonos, stablecoins)
- **5-15%** en apuestas altamente especulativas (opciones, crypto, prediction markets)
- **0%** en riesgo "medio" (imposible de estimar correctamente)

**Para nuestro caso**: 85-90% en USDC en Aave/Compound (4-6% APY seguro) + 10-15% en Polymarket/trades especulativos.

### 1.7 Lecciones de los Top Traders

**Jim Simons (Renaissance)**:
- Solo acierta el 50.75% de los trades — pero hace 150,000/dia
- "Los modelos no reflejan la realidad, solo algunos aspectos de ella"
- Automatizacion total: cero intervencion humana

**Theo (Polymarket, +$85M)**:
- Comisiono una encuesta privada a YouGov usando el "efecto vecino"
- Information edge > prediction: encontro un sesgo en las encuestas que el mercado ignoraba
- Vendio todos sus activos liquidos para apostar $80M

**Edward Thorp (primer quant)**:
- Derivo Black-Scholes 6 anios antes que Black y Scholes
- "El edge viene de las matematicas, pero la supervivencia viene del position sizing (Kelly)"

**Mark Douglas (Trading in the Zone)**:
- 5 verdades: (1) Cualquier cosa puede pasar (2) No necesitas predecir para ganar (3) Wins/losses son random en cualquier set (4) Un edge es solo mayor probabilidad (5) Cada trade es unico

---

## PARTE 2: PREDICTION MARKETS (Polymarket/Kalshi)

### 2.1 El Estado del Mercado en 2026

- Polymarket proceso 95M+ transacciones en 2025, $21.5B en volumen
- Solo 0.51% de wallets lograron profits > $1,000
- $40M en profits de arbitraje entre abril 2024 y abril 2025
- Duracion promedio de oportunidad de arbitraje: **2.7 segundos** (era 12.3s en 2024)
- 73% de profits de arbitraje capturados por bots sub-100ms
- Spreads bid-ask comprimidos de 4.5% (2023) a 1.2% (2025)

### 2.2 Las 6 Estrategias Rentables Identificadas

1. **Information Arbitrage**: Tener data que el mercado no tiene (Theo con encuestas)
2. **Cross-Platform Arbitrage**: Polymarket vs Kalshi (divergencia >5% el 15-20% del tiempo)
3. **Market Rebalancing**: Si Yes+No < $1.00, comprar ambos = profit seguro
4. **Market Making**: Proveer liquidez a ambos lados, ganar el spread
5. **Speed Trading**: Reaccionar en <8 segundos a noticias/eventos
6. **AI Event Trading**: Ventana de 30s-5min cuando precio no ajusto a nueva info

### 2.3 Mercados BTC 5-min — Nuestro Campo de Batalla

**El edge real es la latencia, no la prediccion**:
- Chainlink actualiza BTC/USD cada ~10-30s o con desviacion de 0.5%
- Lag entre Binance real y oracle: 100-500ms
- A T-10s del cierre, ~80-85% de ventanas ya tienen resultado definido
- Pero los market makers ya ajustaron el precio del token

**Datos de los bots ganadores**:
- Bot basado en Claude: $1,000 → $14,216 en 48hs
- Bot Go (PolyCryptoBot): $313 → $414,000 en un mes (98% win rate)
- Win rate de bots exitosos: >85%
- Su edge: latencia ultra-baja, no prediccion tecnica

**Fee structure**:
- Maker (GTC limit order): **0% fee**
- Taker (FOK/market): `token_price * (1 - token_price) * 0.0222` (max 1.56% a 50%)
- **Implicancia**: Maker-first strategy es critica

### 2.4 Realidad para Nosotros (Argentina, capital chico)

- Latencia desde Argentina con WARP: ~150-300ms — demasiado para latency arb
- Capital $60: maximo ~$3/trade en modo SAFE
- Cross-platform arb requiere capital en Polymarket + Kalshi ($500+ recomendado)
- Market making requiere capital significativo para ambos lados del spread

**Conclusion**: Con $60 desde Argentina, solo podemos ejecutar la estrategia
de snipe a T-10s con edge basado en window delta fuerte. No competimos con
bots de latencia. Solo operamos cuando hay edge neto real despues de fees.

---

## PARTE 3: DeFi / CRYPTO YIELD

### 3.1 Estrategias por Nivel de Riesgo

| Estrategia | APY | Riesgo | Capital Min |
|---|---|---|---|
| Aave lending USDC (Polygon) | 4-6% | Bajo (smart contract) | $50 |
| Compound USDC | 2-5% | Bajo | $50 |
| Curve stablecoin pools | 2-19% | Bajo-Medio | $100 |
| Yearn Finance vaults (auto-compound) | 5-10% | Medio | $100 |
| Pendle yield tokenization | 8-15% | Medio | $200 |
| LP en DEX (stablecoin pairs) | 5-15% | Medio (IL bajo) | $100 |
| LP en DEX (volatile pairs) | 15-50%+ | Alto (IL alto) | $200 |

### 3.2 Nuestra Mejor Opcion Inmediata

**Aave en Polygon** — ya tenemos wallet ahi:
- Depositar USDC.e que ya tenemos ($60.55)
- Ganar 4-6% APY = ~$3/anio
- Zero esfuerzo, riesgo minimo (Aave tiene $15B+ TVL, nunca fue hackeado)
- Se puede retirar en cualquier momento

**Limitacion**: $60 * 5% = $3/anio. No mueve la aguja.

### 3.3 CEX-DEX Arbitrage

- Viable con $200-500 por transaccion
- En BSC: ciclo completo en 10-20 min, ~$1-6/transaccion
- Requiere bot o ejecucion rapida
- Spreads se cerraron mucho en 2026 — necesitas automatizacion

---

## PARTE 4: INVERSIONES DESDE ARGENTINA (2026)

### 4.1 Contexto Macro

- Inflacion: ~2-2.8% mensual (bajando)
- Dolar: todas las cotizaciones convergieron a $1,390-1,460
- Riesgo pais: <500bp (era 1,500)
- Mejor inversion YTD 2026: Oro, luego PF UVA
- Estrategia dominante: Carry trade en pesos

### 4.2 Oportunidades Concretas

#### Carry Trade (la mas popular en 2026)
- Vender dolares → poner en LECAPs (35-36% TNA) → recomprar dolares
- Funciona mientras el dolar se mantiene estable/baja
- Riesgo: devaluacion subita elimina todas las ganancias
- Para empezar: necesitas cuenta comitente (IOL, Bull Market, Cocos)

#### CEDEARs (acciones de EEUU desde Argentina)
- Picks 2026: NVIDIA, MercadoLibre, Vista Energy, Microsoft, TSM
- Portfolio modelo: 40% tech, 25% energia, 20% consumo, 10% crypto-linked, 5% cash
- Se puede empezar con lo que sea (fraccionarios)
- Ventaja: cobertura contra devaluacion (cotizan en ARS pero subyacente en USD)

#### Bonos Argentinos
- **Conservador**: BPOC7 (Bopreal, ~6% anual USD), BONCER TX26 (CER)
- **Moderado**: AL30 (Bonar 2030), AN29 (9.7% TIR)
- **Agresivo**: GD35 (12.2% TIR, 30% upside potencial)
- Catalizador: posible re-inclusion en MSCI Emerging Markets

#### P2P Crypto Arbitrage
- Cross-platform: Lemon vs Buenbit vs Ripio vs Binance P2P
- Rulo cripto: comprar USDT, vender en otro exchange a premium
- BCRA restringio el rulo clasico (90 dias restriccion cruzada)
- Stablecoins = 61.8% de transacciones crypto en Argentina

### 4.3 Impuestos Crypto en Argentina

- **Ganancias**: 5% sobre ganancias en ARS, 15% en moneda extranjera
- **Swaps entre cryptos** son eventos gravables
- **Staking/DeFi yields**: gravados como renta de segunda categoria
- **Bienes Personales**: crypto en exchanges extranjeros = bienes del exterior
- Exchanges locales (Lemon, Buenbit, Ripio) reportan a ARCA mensualmente

---

## PARTE 5: MI RECOMENDACION — Plan de Accion

### Situacion Actual
- Capital total: ~$65 USD ($60.55 USDC.e + $4.84 USDC native)
- Infraestructura: wallet Polygon, Binance, Cloudflare WARP
- Resultado previo: -27% con estrategia v1/v2

### Principio Rector: Barbell de Taleb adaptado

```
90% SEGURO ($58.50) → Aave/Compound USDC lending (4-6% APY)
10% ESPECULATIVO ($6.50) → Polymarket BTC 5-min con estrategia v3
```

### Fase 1: Sobrevivir y Aprender (semanas 1-4)
1. Depositar $55 en Aave Polygon (USDC.e lending)
2. Correr estrategia v3 en **dry run** (sin plata real) — solo loggear seniales
3. Despues de 50+ seniales loggeadas, calcular win rate real y calibrar DELTA_PROB_MAP
4. Abrir cuenta comitente (IOL o Bull Market) para acceder a CEDEARs y carry trade

### Fase 2: Validar Edge (semanas 5-8)
1. Si el dry run muestra WR > 55% con edge neto positivo consistente:
   - Poner $5-10 reales en Polymarket modo SAFE
   - Risk por trade: $1-2 max (quarter Kelly)
2. Si NO muestra edge: **no poner plata**. Pivotar a otra estrategia
3. Considerar CEDEARs defensivos (SPY, MSFT) como ahorro en dolares

### Fase 3: Escalar (mes 3+)
1. Si Polymarket es rentable: aumentar bankroll gradualmente (reinvertir profits)
2. Diversificar: parte en carry trade pesos (LECAPs) si macro sigue estable
3. Explorar CEX-DEX arbitrage con bot si capital crece a >$200
4. Nunca poner mas del 15% del capital total en Polymarket

### Reglas Inquebrantables
1. **Nunca arriesgar mas del 5% del bankroll en un solo trade**
2. **Stop total si drawdown alcanza 20%**
3. **Juzgar decisiones por proceso, no por resultado** (Annie Duke)
4. **Recalcular Kelly cada 20-30 trades**
5. **Si no hay edge, no operar** (Kelly = 0 cuando edge = 0)
6. **La supervivencia es mas importante que las ganancias** (Thorp)

---

## FORMULAS RAPIDAS DE REFERENCIA

```
Kelly:          f* = (b*p - q) / b
Position Size:  (Equity * Risk%) / Risk_per_unit
Recovery:       1/(1-DD%) - 1
Expectancy:     (Win% * AvgWin_R) + (Loss% * AvgLoss_R)
Sharpe:         (Rp - Rf) / sigma
Sortino:        (Rp - Rf) / sigma_downside
Breakeven WR:   1 / (1 + R:R)
Fee Polymarket: token_price * (1 - token_price) * 0.0222
Adj Kelly:      Kelly / (1 + avg_correlation)
RoR:            ((1-p)/p) ^ (B/S)
```

---

## FUENTES PRINCIPALES

### Libros
- "Thinking in Bets" — Annie Duke
- "The Man Who Solved the Market" — Gregory Zuckerman (Jim Simons)
- "Quantitative Trading" — Ernest Chan
- "Market Wizards" — Jack Schwager
- "A Random Walk Down Wall Street" — Burton Malkiel
- "The Intelligent Investor" — Benjamin Graham
- "Fooled by Randomness" — Nassim Taleb
- "Trading in the Zone" — Mark Douglas

### Papers Academicos
- "Prediction Markets? The Accuracy and Efficiency of $2.4B in the 2024 Election" — Clinton & Huang
- "Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets" — IMDEA (arXiv:2508.03474)
- "Exploring Decentralized Prediction Markets: Accuracy, Skill, and Bias on Polymarket" — Reichenbach & Walther

### Mercados Argentina
- Bloomberg Linea, iProfesional, Infobae, El Cronista, Ambito — analisis de mercado 2026
- ARCA/AFIP — normativa impositiva crypto
- BCRA Com. A 8336 — restriccion cruzada septiembre 2025
