"""
Polymarket Trader - Ejecuta trades en mercados de 5-min BTC Up/Down
Estrategia: Maker limit orders para evitar fees de taker (~3%)
"""
import os
import time
import logging
import requests
from typing import Optional, List, Dict
from datetime import datetime
from dotenv import load_dotenv

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, BalanceAllowanceParams
from py_clob_client.order_builder.constants import BUY, SELL

load_dotenv()
logger = logging.getLogger("botardo")


class PolymarketTrader:
    def __init__(self):
        self.private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
        self.wallet_address = os.getenv("POLYMARKET_WALLET_ADDRESS", "")
        self.client = None
        self.connected = False

    def connect(self) -> bool:
        """Conecta al CLOB de Polymarket y genera API creds"""
        try:
            self.client = ClobClient(
                "https://clob.polymarket.com",
                key=self.private_key,
                chain_id=137,
                signature_type=0,  # EOA wallet (MetaMask)
                funder=self.wallet_address,
            )
            creds = self.client.create_or_derive_api_creds()
            self.client.set_api_creds(creds)
            self.connected = True
            logger.info("Polymarket CLOB connected")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Polymarket: {e}")
            return False

    def find_5min_btc_markets(self) -> List[Dict]:
        """
        Busca mercados activos de BTC 5-min Up or Down.
        Slug pattern: btc-updown-5m-{unix_timestamp}
        Se generan nuevos cada 5 minutos.
        """
        markets = []
        now = int(time.time())
        # Buscar mercados en los proximos 30 minutos (6 slots de 5 min)
        base = now - (now % 300)

        for offset in range(-2, 8):
            ts = base + (offset * 300)
            slug = f"btc-updown-5m-{ts}"
            try:
                r = requests.get(
                    "https://gamma-api.polymarket.com/events",
                    params={"slug": slug},
                    timeout=8,
                )
                data = r.json()
                if data:
                    for evt in data:
                        for mkt in evt.get("markets", []):
                            mkt["_slug"] = slug
                            mkt["_timestamp"] = ts
                            markets.append(mkt)
            except Exception:
                continue

        logger.info(f"Found {len(markets)} BTC 5-min markets")
        return markets

    def get_orderbook(self, token_id: str) -> Dict:
        """Obtiene el orderbook de un token"""
        try:
            book = self.client.get_order_book(token_id)
            return book
        except Exception as e:
            logger.error(f"Error getting orderbook: {e}")
            return {"bids": [], "asks": []}

    def analyze_opportunity(self, market: Dict) -> Optional[Dict]:
        """
        Analiza si hay oportunidad de arbitraje o edge en un mercado.

        Para mercados binarios (Up/Down):
        - Si Yes + No < $1.00 -> arbitraje risk-free
        - Si el orderbook tiene buen spread -> oportunidad de maker
        """
        import json

        outcomes = market.get("outcomes", "[]")
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)

        prices_str = market.get("outcomePrices", "[]")
        if isinstance(prices_str, str):
            prices = [float(p) for p in json.loads(prices_str)]
        else:
            prices = [float(p) for p in prices_str]

        token_ids_str = market.get("clobTokenIds", "[]")
        if isinstance(token_ids_str, str):
            token_ids = json.loads(token_ids_str)
        else:
            token_ids = token_ids_str or []

        if len(prices) != 2 or len(token_ids) != 2:
            return None

        total_cost = sum(prices)

        result = {
            "question": market.get("question", "?"),
            "condition_id": market.get("conditionId", ""),
            "outcomes": outcomes,
            "prices": prices,
            "token_ids": token_ids,
            "total_cost": total_cost,
            "arb_edge": (1.0 - total_cost) / total_cost * 100
            if total_cost < 1.0
            else 0,
        }

        # Get orderbook for both sides
        if self.connected and self.client:
            for i, tid in enumerate(token_ids):
                try:
                    book = self.client.get_order_book(tid)
                    bids = book.get("bids", [])
                    asks = book.get("asks", [])
                    result[f"outcome_{i}_bids"] = len(bids)
                    result[f"outcome_{i}_asks"] = len(asks)
                    result[f"outcome_{i}_best_bid"] = (
                        float(bids[0]["price"]) if bids else 0
                    )
                    result[f"outcome_{i}_best_ask"] = (
                        float(asks[0]["price"]) if asks else 0
                    )
                except Exception:
                    result[f"outcome_{i}_bids"] = 0
                    result[f"outcome_{i}_asks"] = 0
                    result[f"outcome_{i}_best_bid"] = 0
                    result[f"outcome_{i}_best_ask"] = 0

        return result

    def place_maker_order(
        self, token_id: str, side: str, price: float, size: float
    ) -> Dict:
        """
        Coloca una limit order GTC (maker).
        """
        try:
            order_args = OrderArgs(
                price=price,
                size=size,
                side=BUY if side == "BUY" else SELL,
                token_id=token_id,
            )
            signed_order = self.client.create_order(order_args)
            resp = self.client.post_order(signed_order, OrderType.GTC)
            logger.info(f"Order placed: {side} {size} @ {price} | Response: {resp}")
            return {"success": True, "response": resp}
        except Exception as e:
            logger.error(f"Order failed: {e}")
            return {"success": False, "error": str(e)}

    def place_market_order(
        self, token_id: str, side: str, price: float, size: float
    ) -> Dict:
        """
        Coloca una order FOK (Fill or Kill) que se ejecuta inmediatamente
        o se cancela. Esto garantiza ejecución cuando hay liquidez.
        Paga fee de taker pero se llena seguro.
        """
        try:
            order_args = OrderArgs(
                price=price,
                size=size,
                side=BUY if side == "BUY" else SELL,
                token_id=token_id,
            )
            signed_order = self.client.create_order(order_args)
            resp = self.client.post_order(signed_order, OrderType.FOK)
            logger.info(f"Market order (FOK): {side} {size} @ {price} | Response: {resp}")
            return {"success": True, "response": resp}
        except Exception as e:
            logger.error(f"Market order failed: {e}")
            return {"success": False, "error": str(e)}

    def execute_binary_arbitrage(
        self, market: Dict, amount_usdc: float = 10.0
    ) -> Dict:
        """
        Ejecuta arbitraje binario: compra Yes + No si total < $1.00
        Usa limit orders como maker para evitar fees.

        Args:
            market: Market data con token_ids y prices
            amount_usdc: Cuanto invertir en USDC
        """
        import json

        token_ids = market.get("clobTokenIds", "[]")
        if isinstance(token_ids, str):
            token_ids = json.loads(token_ids)

        prices = market.get("outcomePrices", "[]")
        if isinstance(prices, str):
            prices = [float(p) for p in json.loads(prices)]

        if len(token_ids) != 2 or len(prices) != 2:
            return {"success": False, "error": "Not a binary market"}

        total_cost = sum(prices)
        if total_cost >= 1.0:
            return {"success": False, "error": f"No arb: total={total_cost:.4f}"}

        # Calculate shares to buy
        shares = amount_usdc / total_cost

        results = []
        for i, (tid, price) in enumerate(zip(token_ids, prices)):
            result = self.place_maker_order(
                token_id=tid,
                side="BUY",
                price=price,
                size=shares,
            )
            results.append(result)

        return {
            "success": all(r.get("success") for r in results),
            "total_cost": total_cost,
            "edge": (1.0 - total_cost) / total_cost * 100,
            "orders": results,
        }
