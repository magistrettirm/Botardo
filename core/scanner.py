# ============================================================
# core/scanner.py — Detecta oportunidades de arbitraje
# ============================================================

from datetime import datetime
from typing import List

import config
from core.models import ExchangePrice, Opportunity

# Mapa de fees por exchange (nombre -> fee como decimal)
EXCHANGE_FEES = {
    "Binance P2P":  config.FEE_BINANCE_P2P,
    "Buenbit":      config.FEE_BUENBIT,
    "Ripio":        config.FEE_RIPIO,
    "Satoshi Tango": config.FEE_SATOSHI,
}


def scan(prices: List[ExchangePrice]) -> List[Opportunity]:
    """
    Recibe una lista de ExchangePrice y retorna oportunidades de arbitraje
    ordenadas por spread neto descendente.

    Solo considera exchanges con precios válidos (sin error).
    """
    # Filtrar exchanges con errores
    valid_prices = [p for p in prices if p.is_valid]

    oportunidades: List[Opportunity] = []

    # Evaluar cada par (a, b): comprar en a, vender en b
    for price_a in valid_prices:
        for price_b in valid_prices:
            if price_a.exchange == price_b.exchange:
                continue

            buy_price = price_a.buy_price   # lo que pago en exchange_a
            sell_price = price_b.sell_price  # lo que recibo en exchange_b

            if buy_price <= 0:
                continue

            # Spread bruto: diferencia porcentual entre venta y compra
            gross_spread_pct = (sell_price - buy_price) / buy_price * 100

            # Fees: se suman ambos lados (en %)
            fee_a = EXCHANGE_FEES.get(price_a.exchange, 0.0) * 100
            fee_b = EXCHANGE_FEES.get(price_b.exchange, 0.0) * 100
            net_spread_pct = gross_spread_pct - fee_a - fee_b

            # Solo alertar si el spread neto supera el mínimo configurado
            if net_spread_pct >= config.MIN_SPREAD_PCT:
                # Ganancia estimada en ARS con capital de referencia
                estimated_profit_ars = (net_spread_pct / 100) * config.CAPITAL_USDT * buy_price

                oportunidades.append(Opportunity(
                    buy_exchange=price_a.exchange,
                    sell_exchange=price_b.exchange,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    gross_spread_pct=round(gross_spread_pct, 4),
                    net_spread_pct=round(net_spread_pct, 4),
                    estimated_profit_ars=round(estimated_profit_ars, 2),
                    timestamp=datetime.now(),
                ))

    # Ordenar por spread neto descendente (mejor oportunidad primero)
    oportunidades.sort(key=lambda o: o.net_spread_pct, reverse=True)
    return oportunidades


def mejor_spread_info(prices: List[ExchangePrice]) -> str:
    """
    Retorna un string con la mejor oportunidad detectada (aunque no supere el umbral),
    para mostrar en el footer de la tabla de precios.
    """
    valid_prices = [p for p in prices if p.is_valid]
    if len(valid_prices) < 2:
        return "Sin suficientes precios válidos para calcular spread."

    mejor = None
    mejor_spread = -999.0

    for price_a in valid_prices:
        for price_b in valid_prices:
            if price_a.exchange == price_b.exchange:
                continue
            if price_a.buy_price <= 0:
                continue
            gross = (price_b.sell_price - price_a.buy_price) / price_a.buy_price * 100
            fee_a = EXCHANGE_FEES.get(price_a.exchange, 0.0) * 100
            fee_b = EXCHANGE_FEES.get(price_b.exchange, 0.0) * 100
            neto = gross - fee_a - fee_b
            if neto > mejor_spread:
                mejor_spread = neto
                mejor = (price_a, price_b, neto)

    if mejor:
        a, b, neto = mejor
        return (
            f"Mejor oportunidad: Comprar {a.exchange} (${a.buy_price:,.2f}) "
            f"-> Vender {b.exchange} (${b.sell_price:,.2f}) = {neto:.2f}% neto"
        )
    return "Sin oportunidades calculables."
