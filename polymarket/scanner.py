import logging
from typing import List
from datetime import datetime
from polymarket.models import PolyMarket, ArbOpportunity
from polymarket.market_fetcher import PolymarketFetcher
from polymarket import config

logger = logging.getLogger("botardo")


class PolymarketScanner:
    def __init__(self):
        self.fetcher = PolymarketFetcher()

    def scan_binary_arbitrage(self, markets: List[PolyMarket] = None) -> List[ArbOpportunity]:
        """
        Busca arbitraje en mercados binarios: Yes + No < $1.00
        """
        if markets is None:
            markets = self.fetcher.get_active_markets(limit=200)

        opportunities = []

        for market in markets:
            # Solo mercados binarios con 2 outcomes
            if len(market.outcome_prices) != 2:
                continue

            # Filtrar por liquidez y volumen
            if market.volume < config.MIN_VOLUME:
                continue
            if market.liquidity < config.MIN_LIQUIDITY:
                continue

            yes_price = market.outcome_prices[0]
            no_price = market.outcome_prices[1]

            # Validar precios
            if yes_price <= 0 or no_price <= 0:
                continue
            if yes_price >= 1 or no_price >= 1:
                continue

            total_cost = yes_price + no_price

            # Si total_cost < 1, hay arbitraje
            if total_cost < 1.0:
                gross_edge = (1.0 - total_cost) / total_cost * 100
                # Restar fees estimados (como taker ~3% en crypto, ~0.1% en standard)
                is_crypto = any(kw in market.question.lower() for kw in ["bitcoin", "btc", "eth", "sol", "crypto"])
                fee_estimate = config.MAX_SPREAD_COST if is_crypto else 0.2
                net_edge = gross_edge - fee_estimate

                # Capital de referencia: $100 USDC por trade
                capital = 100
                estimated_profit = capital * gross_edge / 100

                opp = ArbOpportunity(
                    market=market,
                    total_cost=total_cost,
                    guaranteed_payout=1.0,
                    gross_edge_pct=round(gross_edge, 3),
                    net_edge_pct=round(net_edge, 3),
                    estimated_profit_usd=round(estimated_profit, 2),
                    arb_type="binary",
                )
                opportunities.append(opp)

        # Ordenar por edge neto desc
        opportunities.sort(key=lambda x: x.net_edge_pct, reverse=True)
        return opportunities

    def scan_all(self) -> dict:
        """Scan completo: binary arb + mejores mercados crypto"""
        markets = self.fetcher.get_active_markets(limit=200)

        binary_opps = self.scan_binary_arbitrage(markets)
        crypto_markets = [m for m in markets if any(
            kw in m.question.lower() for kw in ["bitcoin", "btc", "ethereum", "eth"]
        )]

        # Top mercados por volumen
        top_volume = sorted(markets, key=lambda m: m.volume, reverse=True)[:10]

        return {
            "binary_arbitrage": binary_opps,
            "crypto_markets": crypto_markets[:10],
            "top_volume_markets": top_volume,
            "total_markets_scanned": len(markets),
            "timestamp": datetime.now().isoformat(),
        }

    def format_report(self, scan_result: dict) -> str:
        """Formatea un reporte para Telegram"""
        lines = ["\U0001f4ca *Polymarket Scanner*\n"]
        lines.append(f"Mercados escaneados: {scan_result['total_markets_scanned']}")

        binary = scan_result.get("binary_arbitrage", [])
        if binary:
            lines.append(f"\n\U0001f525 *{len(binary)} oportunidad(es) de arbitraje:*")
            for opp in binary[:5]:
                lines.append(
                    f"  \u2022 {opp.market.question[:60]}\n"
                    f"    Cost: ${opp.total_cost:.4f} | Edge bruto: {opp.gross_edge_pct:.2f}% | "
                    f"Neto: {opp.net_edge_pct:.2f}%"
                )
        else:
            lines.append("\nSin oportunidades de arbitraje binario.")

        crypto = scan_result.get("crypto_markets", [])
        if crypto:
            lines.append(f"\n\U0001f4b0 *Mercados crypto ({len(crypto)}):*")
            for m in crypto[:5]:
                prices_str = " / ".join(f"{o}: ${p:.2f}" for o, p in zip(m.outcomes, m.outcome_prices))
                lines.append(f"  \u2022 {m.question[:50]}\n    {prices_str} | Vol: ${m.volume:,.0f}")

        return "\n".join(lines)
