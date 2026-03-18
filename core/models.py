# ============================================================
# core/models.py — Dataclasses del dominio del bot
# ============================================================

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ExchangePrice:
    """
    Precio de USDT/ARS en un exchange específico.

    buy_price:  precio al que YO compro USDT (ask del exchange, lo que pago)
    sell_price: precio al que YO vendo USDT (bid del exchange, lo que recibo)
    """
    exchange: str
    buy_price: float        # ask — lo que pago para comprar 1 USDT
    sell_price: float       # bid — lo que recibo si vendo 1 USDT
    timestamp: datetime = field(default_factory=datetime.now)
    available_volume: float = 0.0
    error: str = ""

    @property
    def is_valid(self) -> bool:
        """Retorna True si el precio fue obtenido sin errores."""
        return self.error == "" and self.buy_price > 0 and self.sell_price > 0


@dataclass
class Opportunity:
    """
    Oportunidad de arbitraje detectada entre dos exchanges.

    Estrategia: comprar USDT barato en buy_exchange, vender caro en sell_exchange.
    """
    buy_exchange: str
    sell_exchange: str
    buy_price: float            # precio de compra (ask en buy_exchange)
    sell_price: float           # precio de venta (bid en sell_exchange)
    gross_spread_pct: float     # spread bruto antes de fees
    net_spread_pct: float       # spread neto después de fees
    estimated_profit_ars: float # ganancia estimada en ARS con CAPITAL_USDT
    timestamp: datetime = field(default_factory=datetime.now)
