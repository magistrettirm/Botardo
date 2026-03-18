# ============================================================
# fetchers/binance_p2p.py — Precios USDT/ARS en Binance P2P
# ============================================================
#
# API pública de Binance P2P (no requiere API key).
# Endpoint: POST https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search
#
# Lógica de precios:
#   - BUY (tradeType="BUY"):  los merchants VENDEN USDT. El primer resultado
#     es el más barato → precio al que YO compro.
#   - SELL (tradeType="SELL"): los merchants COMPRAN USDT. El primer resultado
#     es el que más paga → precio al que YO vendo.

import requests
from datetime import datetime

import config
from core.models import ExchangePrice

EXCHANGE_NAME = "Binance P2P"
API_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
}


def _fetch_side(trade_type: str) -> float:
    """
    Obtiene el precio del primer anuncio para el side indicado.
    trade_type: "BUY" (merchants venden USDT) o "SELL" (merchants compran USDT).
    Retorna el precio como float, o 0.0 si falla.
    """
    payload = {
        "asset": "USDT",
        "fiat": "ARS",
        "merchantCheck": False,
        "page": 1,
        "rows": 5,
        "side": trade_type,
        "tradeType": trade_type,
        "payTypes": [],
    }
    resp = requests.post(API_URL, json=payload, headers=HEADERS, timeout=config.REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    data = resp.json()
    ads = data.get("data", [])
    if not ads:
        raise ValueError(f"Binance P2P: sin anuncios para tradeType={trade_type}")
    return float(ads[0]["adv"]["price"])


def get_price() -> ExchangePrice:
    """
    Retorna un ExchangePrice con los precios actuales de Binance P2P.
    Si ocurre algún error, retorna con el campo error poblado.
    """
    try:
        buy_price = _fetch_side("BUY")    # precio más bajo al que puedo comprar
        sell_price = _fetch_side("SELL")  # precio más alto al que puedo vender
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
