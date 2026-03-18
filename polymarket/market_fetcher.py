import json
import requests
import logging
from typing import List, Optional
from polymarket.models import PolyMarket
from polymarket import config

logger = logging.getLogger("botardo")


class PolymarketFetcher:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Botardo/1.0"
        })

    def get_active_markets(self, limit: int = 100, category: str = None) -> List[PolyMarket]:
        """Obtiene mercados activos de Polymarket via Gamma API"""
        url = f"{config.GAMMA_API_URL}/markets"
        params = {
            "limit": limit,
            "active": True,
            "closed": False,
        }
        if category:
            params["tag"] = category

        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Error fetching Polymarket markets: {e}")
            return []

        markets = []
        for item in data:
            try:
                # Parsear outcomes y precios
                outcomes = item.get("outcomes", "[]")
                if isinstance(outcomes, str):
                    outcomes = json.loads(outcomes)

                outcome_prices_str = item.get("outcomePrices", "[]")
                if isinstance(outcome_prices_str, str):
                    outcome_prices = [float(p) for p in json.loads(outcome_prices_str)]
                else:
                    outcome_prices = [float(p) for p in outcome_prices_str]

                # Token IDs
                clobTokenIds = item.get("clobTokenIds", "[]")
                if isinstance(clobTokenIds, str):
                    token_ids = json.loads(clobTokenIds)
                else:
                    token_ids = clobTokenIds or []

                market = PolyMarket(
                    condition_id=item.get("conditionId", ""),
                    question=item.get("question", "Unknown"),
                    slug=item.get("slug", ""),
                    outcomes=outcomes,
                    outcome_prices=outcome_prices,
                    token_ids=token_ids,
                    volume=float(item.get("volume", 0) or 0),
                    liquidity=float(item.get("liquidity", 0) or 0),
                    end_date=item.get("endDate"),
                    category=item.get("groupSlug", ""),
                    active=item.get("active", True),
                )
                markets.append(market)
            except Exception as e:
                logger.debug(f"Error parsing market: {e}")
                continue

        return markets

    def get_crypto_markets(self) -> List[PolyMarket]:
        """Obtiene mercados crypto (BTC up/down, etc.)"""
        all_markets = self.get_active_markets(limit=200)
        crypto_keywords = ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol"]

        crypto = []
        for m in all_markets:
            q_lower = m.question.lower()
            if any(kw in q_lower for kw in crypto_keywords):
                crypto.append(m)

        return crypto

    def get_high_volume_markets(self, min_volume: float = None) -> List[PolyMarket]:
        """Obtiene mercados con alto volumen"""
        min_vol = min_volume or config.MIN_VOLUME
        all_markets = self.get_active_markets(limit=200)
        return [m for m in all_markets if m.volume >= min_vol]

    def get_market_orderbook(self, token_id: str) -> dict:
        """
        Obtiene el orderbook de un token via CLOB API (publico).
        NOTA: El CLOB API (clob.polymarket.com) puede estar bloqueado
        desde Argentina sin VPN. Si falla con timeout o 403, es por
        restriccion geografica.
        """
        url = f"{config.CLOB_API_URL}/book"
        params = {"token_id": token_id}
        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Error fetching orderbook for {token_id}: {e}")
            return {"bids": [], "asks": []}

    def get_market_price(self, token_id: str) -> Optional[float]:
        """
        Obtiene precio actual de un token via CLOB API.
        NOTA: El CLOB API puede estar bloqueado desde Argentina sin VPN.
        """
        url = f"{config.CLOB_API_URL}/price"
        params = {"token_id": token_id, "side": "buy"}
        try:
            resp = self.session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return float(data.get("price", 0))
        except Exception as e:
            logger.error(f"Error fetching price for {token_id}: {e}")
            return None
