# Botardo - Memoria del Proyecto

## Resumen
Bot de arbitraje financiero con dos módulos:
1. **USDT/ARS Scanner** - Monitorea precios en 4 exchanges argentinos
2. **Polymarket Trader** - Opera mercados de predicción de BTC 5-min

## Estado Actual (2026-03-18)

### Balance
- Wallet: `0x11E592a97F264335849970f25d9cf910DE798071`
- POL: 19.90 (~$8)
- USDC.e: $60.55
- USDC native: $4.84
- Capital inicial: ~$100 USD
- **Resultado neto: -$26.61 (~-27%)**

### Estrategia Polymarket (v2 - Adaptive)
- Mercado: BTC 5-minute candles (Up/Down)
- Señales: RSI(14) + EMA(9/21) crossover + Bollinger Bands + volumen
- Min confianza para operar: 65%
- Bet sizing: Kelly Criterion (max 15% del bankroll)
- Stop loss global: $40 (para todo el bankroll)
- Auto-ajuste: Si win rate < 45% en últimos 20 trades, sube min_confidence a 75%

### Resultados de Trading
- La estrategia perdió ~$8 durante la primera noche completa
- Los primeros 2 trades fueron winners (+$9.61)
- Trades posteriores fueron mayormente losses
- **Conclusión: La estrategia de predicción de BTC 5-min no es rentable con indicadores técnicos simples. El mercado de 5 minutos es básicamente random walk.**

### Infraestructura
- Telegram bot: @botardo_arb_bot (token en .env)
- Chat ID: 913393738
- Cloudflare WARP instalado (VPN para acceder a Polymarket desde Argentina)
- Binance API: Solo lectura habilitada, Spot Trading habilitado por el usuario
- MetaMask wallet configurada con private key en .env

## Arquitectura de Archivos

```
C:\Botardo\
├── main.py                    # Entry point scanner USDT/ARS
├── polymarket_main.py         # Entry point scanner Polymarket
├── config.py                  # Configuración general
├── requirements.txt
├── .env                       # Credenciales (NO commitear)
├── .gitignore                 # Excluir .env, __pycache__, etc
├── MEMORY.md                  # Este archivo
├── fetchers/                  # Price fetchers USDT/ARS
│   ├── binance_p2p.py
│   ├── buenbit.py
│   ├── ripio.py
│   └── satoshi_tango.py
├── core/                      # Scanner y modelos
│   ├── models.py
│   └── scanner.py
├── alerts/                    # Sistema de alertas
│   └── notifier.py
├── execution/                 # Ejecución de órdenes
│   ├── binance_executor.py
│   └── manager.py
├── polymarket/                # Módulo Polymarket
│   ├── config.py
│   ├── models.py
│   ├── market_fetcher.py
│   └── scanner.py
└── logs/
```

## Exchanges Monitoreados (USDT/ARS)
| Exchange | API Pública | Ejecución |
|---|---|---|
| Binance P2P | ✅ Funciona | ✅ API habilitada |
| Buenbit | ✅ via be.buenbit.com | ❌ Sin API |
| Ripio | ✅ via app.ripio.com | ❌ Sin API |
| Satoshi Tango | ✅ Funciona | ❌ Sin API |

## Credenciales (referencia, valores reales en .env)
- Binance API Key/Secret: en .env
- Telegram Bot Token: en .env
- Polymarket Private Key: en .env
- Wallet Address: 0x11E592a97F264335849970f25d9cf910DE798071

## Próximos Pasos
1. Investigar estrategias más rentables para Polymarket (arbitraje puro, no predicción)
2. Mejorar scanner USDT/ARS agregando más exchanges y pares (BTC, ETH)
3. Considerar dólar MEP/CCL como fuente de arbitraje
4. Evaluar si webscraping de Buenbit/Ripio permite ejecución
