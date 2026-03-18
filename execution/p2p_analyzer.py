"""
Analizador de oportunidades P2P - busca arbitraje dentro de Binance
y entre Binance P2P y otros exchanges.
"""
import logging
from typing import List
from execution.web_executor import BinanceP2PWebScraper, P2PAd
from core.models import Opportunity
from datetime import datetime
import config

logger = logging.getLogger("botardo")


class P2PAnalyzer:
    """
    Analiza oportunidades de arbitraje en P2P:
    1. Spread entre diferentes merchants en P2P
    2. Spread entre metodos de pago (Mercadopago vs transferencia)
    3. Arbitraje interno: comprar con un metodo, vender con otro
    """

    def __init__(self):
        self.scraper = BinanceP2PWebScraper()

    def analyze_internal_arbitrage(self) -> List[dict]:
        """
        Busca oportunidades de arbitraje DENTRO de Binance P2P.
        Ejemplo: comprar USDT con Mercadopago a $1460, vender por
        transferencia bancaria a $1480.
        """
        analysis = self.scraper.get_spread_analysis()

        if "error" in analysis:
            return []

        opportunities = []
        payment_data = analysis.get("by_payment_method", {})

        # Cruzar todos los pares de metodos de pago
        methods = list(payment_data.keys())
        for i, buy_method in enumerate(methods):
            for sell_method in methods[i+1:]:
                buy_data = payment_data[buy_method]
                sell_data = payment_data[sell_method]

                # Caso 1: comprar con buy_method, vender con sell_method
                spread1 = (sell_data["sell_price"] - buy_data["buy_price"]) / buy_data["buy_price"] * 100
                if spread1 > 0.5:  # umbral mas bajo para P2P interno (sin fees)
                    opportunities.append({
                        "type": "p2p_internal",
                        "buy_method": buy_method,
                        "buy_price": buy_data["buy_price"],
                        "sell_method": sell_method,
                        "sell_price": sell_data["sell_price"],
                        "spread_pct": round(spread1, 3),
                        "estimated_profit": round(config.CAPITAL_USDT * spread1 / 100 * buy_data["buy_price"], 2),
                    })

                # Caso 2: inverso
                spread2 = (buy_data["sell_price"] - sell_data["buy_price"]) / sell_data["buy_price"] * 100
                if spread2 > 0.5:
                    opportunities.append({
                        "type": "p2p_internal",
                        "buy_method": sell_method,
                        "buy_price": sell_data["buy_price"],
                        "sell_method": buy_method,
                        "sell_price": buy_data["sell_price"],
                        "spread_pct": round(spread2, 3),
                        "estimated_profit": round(config.CAPITAL_USDT * spread2 / 100 * sell_data["buy_price"], 2),
                    })

        # Ordenar por spread desc
        opportunities.sort(key=lambda x: x["spread_pct"], reverse=True)
        return opportunities

    def get_full_report(self) -> str:
        """Genera un reporte completo para Telegram"""
        analysis = self.scraper.get_spread_analysis()
        internal = self.analyze_internal_arbitrage()

        lines = ["\U0001f4ca *Reporte P2P Binance*\n"]

        if "error" not in analysis:
            lines.append(f"Mejor compra: ${analysis['best_buy_price']:,.2f}")
            lines.append(f"Mejor venta: ${analysis['best_sell_price']:,.2f}")
            lines.append(f"Spread interno: {analysis['internal_spread_pct']:.2f}%\n")

            lines.append("*Por metodo de pago:*")
            for pm, data in analysis.get("by_payment_method", {}).items():
                lines.append(f"  {pm}: compra ${data['buy_price']:,.2f} / venta ${data['sell_price']:,.2f} ({data['spread_pct']:.2f}%)")

        if internal:
            lines.append("\n\U0001f525 *Oportunidades internas:*")
            for opp in internal[:3]:
                lines.append(
                    f"  Comprar {opp['buy_method']} ${opp['buy_price']:,.2f} -> "
                    f"Vender {opp['sell_method']} ${opp['sell_price']:,.2f} = {opp['spread_pct']:.2f}%"
                )

        return "\n".join(lines)
