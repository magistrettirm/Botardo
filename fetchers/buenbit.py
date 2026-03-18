# ============================================================
# fetchers/buenbit.py — Precios USDT/ARS en Buenbit
# ============================================================
#
# API pública de Buenbit.
# Endpoint: GET https://be.buenbit.com/api/market/tickers/
#
# NOTA: El dominio api.buenbit.com no resuelve DNS (inaccesible desde esta red).
#       Se usa be.buenbit.com que devuelve la misma estructura.
#
# Estructura relevante en la respuesta:
#   data["object"]["usdtars"] = {
#       "purchase_price": "1452.29",  ← precio al que Buenbit COMPRA USDT (bid = lo que yo recibo)
#       "selling_price":  "1485.70",  ← precio al que Buenbit VENDE USDT (ask = lo que yo pago)
#   }

import requests
from datetime import datetime

import config
from core.models import ExchangePrice

EXCHANGE_NAME = "Buenbit"
API_URL = "https://be.buenbit.com/api/market/tickers/"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_price() -> ExchangePrice:
    """
    Retorna un ExchangePrice con los precios actuales de Buenbit.
    """
    try:
        resp = requests.get(API_URL, headers=HEADERS, timeout=config.REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()

        tickers = data.get("object", {})
        usdt_ars = tickers.get("usdtars")
        if not usdt_ars:
            raise ValueError("Par 'usdtars' no encontrado en la respuesta de Buenbit")

        # purchase_price: Buenbit COMPRA USDT → yo VENDO (bid)
        # selling_price:  Buenbit VENDE USDT → yo COMPRO (ask)
        sell_price = float(usdt_ars["purchase_price"])  # bid: lo que recibo
        buy_price = float(usdt_ars["selling_price"])    # ask: lo que pago

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
