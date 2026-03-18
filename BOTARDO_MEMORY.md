# BOTARDO_MEMORY.md — Base de Conocimiento Polymarket Trading Bot

## Resumen General

**Botardo** es un bot de trading automatizado para **Polymarket**, especializado en mercados binarios de BTC 5 minutos (Up/Down). Usa una estrategia de 7 indicadores ponderados ("Composite Snipe Strategy v3") para detectar señales de entrada en los últimos 10 segundos antes del cierre de cada ventana de 5 minutos.

**Bankroll inicial:** $500 USD (USDC en Polygon)
**Blockchain:** Polygon (Chain ID 137)

---

## Arquitectura

```
live_trader.py (main loop cada 2s)
  ├── strategy.py      — 7 indicadores + Kelly + capital protection
  ├── trader.py         — CLOB client, place orders, find markets
  ├── allowance.py      — ERC20 approvals para USDC en Polygon
  ├── market_fetcher.py — Gamma API (markets) + CLOB API (orderbooks)
  ├── scanner.py        — Detección de arbitraje (Yes+No < $1)
  ├── models.py         — Dataclasses: PolyMarket, ArbOpportunity
  └── config.py         — Constantes, env vars, API URLs
```

---

## APIs Externas

| API | URL | Uso |
|-----|-----|-----|
| Polymarket Gamma | `https://gamma-api.polymarket.com` | Datos de mercados (público) |
| Polymarket CLOB | `https://clob.polymarket.com` | Orderbook y trading (puede estar bloqueado desde ARG) |
| Binance | `https://api.binance.com` | Precio BTC en tiempo real (primario) |
| Coinbase | `https://api.coinbase.com` | Precio BTC (fallback) |
| Polygon RPC | `https://polygon-bor-rpc.publicnode.com` | Balance USDC, firmar transacciones |

---

## Contratos Polygon (Polymarket)

| Contrato | Dirección |
|----------|-----------|
| USDC (native) | `0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359` |
| CTF Exchange | `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` |
| Neg Risk CTF Exchange | `0xC5d563A36AE78145C45a50134d48A1215220f80a` |
| Neg Risk Adapter | `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` |

---

## Los 7 Indicadores (strategy.py)

| # | Indicador | Peso | Descripción |
|---|-----------|------|-------------|
| 1 | **Window Delta** | 6.0 (DOMINANTE) | % cambio BTC desde apertura de ventana |
| 2 | **Micro Momentum** | 2.0 | Dirección últimas 2 velas (bullish/bearish/reversal) |
| 3 | **Acceleration** | 1.5 | Si el momentum se fortalece o debilita |
| 4 | **Volume Surge** | 1.5 | Ratio volumen compra/venta reciente |
| 5 | **Tick Trend** | 2.0 | Muestras de precio durante ventana (ticks up vs down) |
| 6 | **Multi-Exchange** | 1.0 | Acuerdo Binance vs Coinbase en dirección |
| 7 | **RSI Extreme** | 1.0 | RSI en extremos (<25 o >75) solamente |

**Score compuesto = Σ(score × peso)** → Máximo posible: ±15.0

---

## Mapeo Delta → Probabilidad (backtesting empírico)

| Delta BTC | Win Rate | Precio Token |
|-----------|----------|-------------|
| 0.005% | 51% | $0.50 |
| 0.010% | 53% | $0.55 |
| 0.020% | 57% | $0.60 |
| 0.050% | 67% | $0.72 |
| 0.100% | 78% | $0.82 |
| 0.200% | 88% | $0.92 |
| 0.500% | 97% | $0.98 |

---

## Modelo de Fees

```python
fee = token_price × (1 - token_price) × 0.0222
# Max fee ~1.56% cuando precio = $0.50, menor en extremos
# Maker orders: 0% fee
# FOK (taker): paga fee completo
```

---

## Modos de Operación

| Parámetro | SAFE ($500) | AGGRESSIVE | DEGEN |
|-----------|-------------|------------|-------|
| max_bet_fraction | 2% ($10) | 5% ($25) | 10% ($50) |
| kelly_fraction | 0.20 | 0.30 | 0.45 |
| min_confidence | 0.45 | 0.35 | 0.25 |
| min_net_edge | 2.5% | 1.5% | 0.8% |
| min_delta | 0.020% | 0.012% | 0.008% |

---

## Capital Protection

- **MAX_CONSECUTIVE_LOSSES = 4** → cooldown de 2 ventanas (600s)
- **MAX_DRAWDOWN_PCT = 20%** → stop absoluto
- Después de pérdidas: min_delta y min_edge suben ×1.5
- Después de 3 wins consecutivos: parámetros se relajan

---

## Estrategia de Ejecución de Órdenes

```
SI seconds_left > 8:
  1. MAKER order (GTC) a market_price - $0.01 → 0% fee
  2. Esperar 2s
  3. Si filled: listo
  4. Si no: cancelar → fallback FOK

SI seconds_left < 8:
  FOK directo a market_price + $0.02 → fill garantizado
```

**Timing de entrada:**
- `ENTRY_SECONDS_BEFORE_CLOSE = 10` (T-10s, sweet spot)
- `HARD_DEADLINE_BEFORE_CLOSE = 5` (T-5s, último recurso)

---

## Ventanas de 5 Minutos

- Cada ventana = 300 segundos alineados a timestamps Unix múltiplos de 300
- Slug del mercado: `btc-updown-5m-{unix_timestamp}`
- Solo busca 3 ventanas (actual + próximas 2) para evitar rate limiting

---

## Dry Run Mode

- NO ejecuta órdenes reales
- Simula P/L: `if won: profit = bet/price - bet; else: profit = -bet`
- Guarda señales en `logs/dry_run_signals.json` con detalle completo de indicadores
- Si win rate > 52% en >50 trades → "EDGE DETECTED"

```bash
python run.py --dry-run --mode SAFE        # Testear sin plata
python run.py --dry-run --mode AGGRESSIVE  # Test agresivo
python run.py --dry-run --bankroll 1000    # Test con bankroll custom
python run.py --mode SAFE                  # LIVE trading real
```

---

## Alertas Telegram

Envía notificaciones de:
- Inicio/cierre del bot
- Cada trade ejecutado (dirección, confianza, score, delta, edge)
- Resultado (WIN/LOSS, P/L, bankroll nuevo)

Variables de entorno: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`

---

## Dependencias (requirements.txt)

```
rich            — Console con colores, tablas, paneles
python-dotenv   — Cargar .env
web3            — Polygon blockchain (wallet, USDC, tx signing)
requests        — HTTP APIs (Binance, Coinbase, Telegram)
py-clob-client  — Polymarket CLOB (órdenes, signing)
```

---

## Variables de Entorno (.env)

```
POLYMARKET_PRIVATE_KEY=0x...     # Private key hex
POLYMARKET_WALLET_ADDRESS=0x...  # Wallet address 42 chars

TELEGRAM_TOKEN=                  # Opcional
TELEGRAM_CHAT_ID=                # Opcional

POLY_SCAN_INTERVAL=5             # Segundos entre scans
MIN_ARB_EDGE=1.5                 # % mínimo para alertar arb
MAX_SPREAD_COST=3.0              # % fee estimado taker
MIN_VOLUME=10000                 # USD mínimo volumen
MIN_LIQUIDITY=5000               # USD mínimo liquidez
```

---

## Setup Inicial (antes del primer trade)

1. `pip install -r polymarket/requirements.txt`
2. Crear `.env` con private key y wallet address
3. `allowance.py` → `setup_all_allowances()` aprueba USDC en contratos CTF
4. `python run.py --dry-run --mode SAFE` para testear
5. Si edge confirmado → `python run.py --mode SAFE` para live

---

## Notas Importantes

- CLOB API puede estar bloqueada desde Argentina → necesita VPN
- Antes de operar en LIVE, correr dry-run por varias horas para validar edge
- El bot lee balance real de wallet cada 10 rondas para stop-loss preciso
- Spike Detection: si composite_score salta ≥1.5 entre polls → confianza +15%
- Indicadores no-delta pueden ajustar probabilidad estimada ±5%
- Kelly Criterion fraccional (0.2-0.45) para controlar volatilidad

---

## Lecciones Aprendidas en Desarrollo

1. Los mercados de 5 min son los más predecibles porque el delta de BTC a T-10s ya tiene alta correlación con el resultado
2. Maker orders son clave: 0% fee vs ~1.5% taker fee cambia completamente la rentabilidad
3. El indicador dominante es Window Delta (peso 6/15) — los demás confirman
4. Capital protection es esencial: 4 losses seguidos pueden destruir bankroll sin cooldown
5. Dry run con logging JSON permite analizar patrones sin arriesgar plata
6. Binance como precio primario es más confiable y rápido que Coinbase
