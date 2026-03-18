from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class PolyMarket:
    """Un mercado de Polymarket"""
    condition_id: str
    question: str
    slug: str
    outcomes: List[str]  # ej: ["Yes", "No"]
    outcome_prices: List[float]  # ej: [0.48, 0.52]
    token_ids: List[str]  # IDs de los tokens para trading
    volume: float
    liquidity: float
    end_date: Optional[str] = None
    category: str = ""
    active: bool = True


@dataclass
class ArbOpportunity:
    """Una oportunidad de arbitraje en Polymarket"""
    market: PolyMarket
    total_cost: float      # costo total de comprar todos los outcomes
    guaranteed_payout: float  # siempre $1 en binario
    gross_edge_pct: float  # (payout - cost) / cost * 100
    net_edge_pct: float    # gross_edge - fees estimados
    estimated_profit_usd: float  # con capital de referencia
    timestamp: datetime = field(default_factory=datetime.now)
    arb_type: str = "binary"  # binary, multi_outcome
