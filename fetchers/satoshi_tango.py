# ============================================================
# fetchers/satoshi_tango.py — Precios USDT/ARS en Satoshi Tango
# ============================================================
#
# API pública de Satoshi Tango.
# Endpoint: GET https://api.satoshitango.com/v3/ticker/ARS/USDT
#
# Estructura de la respuesta:
#   {
#     "data": {
#       "ticker": {
#         "USDT": {
#           "bid": 1457.47,   ← precio de compra de Satoshi (lo que yo recibo si vendo)
#           "ask": 1483.99,   ← precio de venta de Satoshi (lo que pago si compro)
#         }
#       }
#     }
#   }

import requests
from datetime import datetime

import config
from core.models import ExchangePrice

EXCHANGE_NAME = "Satoshi Tango"
API_URL = "https://api.satoshitango.com/v3/ticker/ARS/USDT"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_price() -> ExchangePrice:
    """
    Retorna un ExchangePrice con los precios actuales de Satoshi Tango.
    """
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=config.REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()

        usdt = data.get("data", {}).get("ticker", {}).get("USDT")
        if not usdt:
            raise ValueError("Datos de USDT no encontrados en respuesta de Satoshi Tango")

        buy_price = float(usdt["ask"])   # ask: lo que pago para comprar
        sell_price = float(usdt["bid"])  # bid: lo que recibo al vender

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
