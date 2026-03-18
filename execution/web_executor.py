"""
Web executor para Binance P2P usando Selenium.
Permite interactuar con la interfaz web de Binance P2P
sin necesitar API keys con permisos de trading.
"""
import time
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("botardo")


@dataclass
class P2PAd:
    """Un anuncio P2P individual"""
    merchant_name: str
    price: float
    available_amount: float
    min_limit: float
    max_limit: float
    payment_methods: List[str]
    completion_rate: float
    orders_count: int
    side: str  # "BUY" or "SELL"


class BinanceP2PWebScraper:
    """
    Scraper avanzado para Binance P2P que obtiene datos detallados
    de anuncios usando la API publica (no necesita Selenium para esto).

    Para operaciones que SI necesitan login (colocar anuncios, ejecutar trades),
    se usaria Selenium con una sesion previamente autenticada.
    """

    P2P_API_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

    def __init__(self):
        self.session = None  # Se inicializa Selenium solo cuando se necesite

    def get_detailed_ads(self, side: str = "BUY", asset: str = "USDT",
                          fiat: str = "ARS", rows: int = 20,
                          pay_types: List[str] = None,
                          merchant_check: bool = False) -> List[P2PAd]:
        """
        Obtiene anuncios P2P detallados via la API publica.

        Args:
            side: "BUY" (merchants que venden = nosotros compramos) o
                  "SELL" (merchants que compran = nosotros vendemos)
            asset: crypto asset (USDT, BTC, etc)
            fiat: moneda fiat (ARS, USD, etc)
            rows: cantidad de resultados (max 20)
            pay_types: filtrar por metodo de pago (ej: ["Mercadopago", "BANK"])
            merchant_check: True para solo merchants verificados

        Returns:
            Lista de P2PAd con datos detallados de cada anuncio
        """
        import requests

        payload = {
            "asset": asset,
            "fiat": fiat,
            "merchantCheck": merchant_check,
            "page": 1,
            "rows": rows,
            "tradeType": side,
            "payTypes": pay_types or [],
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        try:
            resp = requests.post(self.P2P_API_URL, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Error fetching P2P ads: {e}")
            return []

        ads = []
        for item in data.get("data", []):
            adv = item.get("adv", {})
            advertiser = item.get("advertiser", {})

            # Extraer metodos de pago
            trade_methods = adv.get("tradeMethods", [])
            payment_methods = [m.get("tradeMethodName", "") for m in trade_methods]

            ad = P2PAd(
                merchant_name=advertiser.get("nickName", "Unknown"),
                price=float(adv.get("price", 0)),
                available_amount=float(adv.get("surplusAmount", 0)),
                min_limit=float(adv.get("minSingleTransAmount", 0)),
                max_limit=float(adv.get("maxSingleTransAmount", 0)),
                payment_methods=payment_methods,
                completion_rate=float(advertiser.get("monthFinishRate", 0)) * 100,
                orders_count=int(advertiser.get("monthOrderCount", 0)),
                side=side,
            )
            ads.append(ad)

        return ads

    def find_best_buy_price(self, max_amount_ars: float = None,
                             payment_method: str = None) -> Optional[P2PAd]:
        """
        Encuentra el mejor precio para COMPRAR USDT (el mas barato).
        Opcionalmente filtra por monto maximo en ARS y metodo de pago.
        """
        pay_types = [payment_method] if payment_method else []
        ads = self.get_detailed_ads(side="BUY", pay_types=pay_types)

        if not ads:
            return None

        # Filtrar por monto si se especifica
        if max_amount_ars:
            ads = [a for a in ads if a.min_limit <= max_amount_ars <= a.max_limit]

        # Ya vienen ordenados por precio (menor primero para BUY)
        return ads[0] if ads else None

    def find_best_sell_price(self, max_amount_ars: float = None,
                              payment_method: str = None) -> Optional[P2PAd]:
        """
        Encuentra el mejor precio para VENDER USDT (el mas caro).
        """
        pay_types = [payment_method] if payment_method else []
        ads = self.get_detailed_ads(side="SELL", pay_types=pay_types)

        if not ads:
            return None

        if max_amount_ars:
            ads = [a for a in ads if a.min_limit <= max_amount_ars <= a.max_limit]

        return ads[0] if ads else None

    def get_spread_analysis(self) -> dict:
        """
        Analisis completo del spread actual en Binance P2P.
        Incluye spread por metodo de pago.
        """
        buy_ads = self.get_detailed_ads(side="BUY", rows=20)
        sell_ads = self.get_detailed_ads(side="SELL", rows=20)

        if not buy_ads or not sell_ads:
            return {"error": "No se pudieron obtener ads"}

        best_buy = buy_ads[0].price   # precio mas bajo para comprar
        best_sell = sell_ads[0].price  # precio mas alto para vender

        # Spread dentro de Binance P2P mismo
        internal_spread = (best_sell - best_buy) / best_buy * 100

        # Analisis por metodo de pago
        payment_analysis = {}
        buy_by_payment = {}
        for ad in buy_ads:
            for pm in ad.payment_methods:
                if pm not in buy_by_payment or ad.price < buy_by_payment[pm].price:
                    buy_by_payment[pm] = ad

        sell_by_payment = {}
        for ad in sell_ads:
            for pm in ad.payment_methods:
                if pm not in sell_by_payment or ad.price > sell_by_payment[pm].price:
                    sell_by_payment[pm] = ad

        for pm in set(buy_by_payment.keys()) & set(sell_by_payment.keys()):
            spread = (sell_by_payment[pm].price - buy_by_payment[pm].price) / buy_by_payment[pm].price * 100
            payment_analysis[pm] = {
                "buy_price": buy_by_payment[pm].price,
                "sell_price": sell_by_payment[pm].price,
                "spread_pct": round(spread, 3),
            }

        return {
            "best_buy_price": best_buy,
            "best_sell_price": best_sell,
            "internal_spread_pct": round(internal_spread, 3),
            "total_buy_ads": len(buy_ads),
            "total_sell_ads": len(sell_ads),
            "by_payment_method": payment_analysis,
        }
