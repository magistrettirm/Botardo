# ============================================================
# fetchers/ripio.py — Precios USDT/ARS en Ripio
# ============================================================
#
# API pública de Ripio.
# Endpoint: GET https://app.ripio.com/api/v3/public/rates/?country=AR
#
# NOTA: api.exchange.ripio.com no resuelve DNS desde esta red.
#       Se usa app.ripio.com que devuelve una lista de pares con rates.
#
# Estructura relevante (ítem con ticker "USDT_ARS"):
#   {
#     "ticker": "USDT_ARS",
#     "buy_rate":  "1467.80",   ← precio al que Ripio VENDE USDT (ask = lo que yo pago)
#     "sell_rate": "1450.81",   ← precio al que Ripio COMPRA USDT (bid = lo que yo recibo)
#   }

import requests
from datetime import datetime

import config
from core.models import ExchangePrice

EXCHANGE_NAME = "Ripio"
API_URL = "https://app.ripio.com/api/v3/public/rates/?country=AR"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_price() -> ExchangePrice:
    """
    Retorna un ExchangePrice con los precios actuales de Ripio.
    """
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=config.REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        rates = resp.json()

        # Buscar el par USDT_ARS en la lista
        usdt_ars = next((r for r in rates if r.get("ticker") == "USDT_ARS"), None)
        if not usdt_ars:
            raise ValueError("Par 'USDT_ARS' no encontrado en la respuesta de Ripio")

        # buy_rate:  Ripio VENDE → yo COMPRO (ask)
        # sell_rate: Ripio COMPRA → yo VENDO (bid)
        buy_price = float(usdt_ars["buy_rate"])
        sell_price = float(usdt_ars["sell_rate"])

        return ExchangePrice(
            exchange=EXCHANGE_NAME,
            buy_price=buy_price,
            sell_price=sell_price,
            timestamp=datetime.now(),
        )
    except Exception as e:
        return ExchangePrice(
            exchange=EXCHANGE_NAME,
            buy_price=0.0,
            sell_price=0.0,
            timestamp=datetime.now(),
            error=str(e),
        )
