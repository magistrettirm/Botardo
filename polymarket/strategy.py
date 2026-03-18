"""
Late-Window Momentum Strategy para mercados BTC 5-min en Polymarket.
Espera hasta los ultimos 10 segundos de la ventana para entrar.
"""
import time
import logging
import requests
from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger("botardo")

@dataclass
class TradeSignal:
    direction: str  # "Up" o "Down"
    confidence: float  # 0 a 1
    window_delta_pct: float  # cambio % desde apertura
    btc_open_price: float
    btc_current_price: float
    estimated_probability: float  # nuestra estimacion
    market_price: float  # precio actual en Polymarket
    kelly_fraction: float  # fraccion Kelly
    bet_size_usdc: float  # tamano de apuesta sugerido
    reason: str  # explicacion

class BinancePriceFeed:
    """Obtiene precio de BTC en tiempo real de Binance"""

    def __init__(self):
        self.url = "https://api.binance.com/api/v3/ticker/price"

    def get_btc_price(self) -> float:
        """Obtiene precio actual de BTC/USDT"""
        try:
            r = requests.get(self.url, params={"symbol": "BTCUSDT"}, timeout=5)
            return float(r.json()["price"])
        except Exception as e:
            logger.error(f"Error getting BTC price: {e}")
            return 0.0

    def get_btc_klines(self, interval="1m", limit=5) -> list:
        """Obtiene velas recientes de BTC"""
        try:
            r = requests.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": "BTCUSDT", "interval": interval, "limit": limit},
                timeout=5
            )
            return r.json()
        except Exception as e:
            logger.error(f"Error getting klines: {e}")
            return []

class LateWindowMomentum:
    """
    Estrategia: esperar hasta T-10s del cierre de ventana y apostar
    en base al Window Delta (cambio de precio desde apertura).
    """

    # Configuracion
    ENTRY_SECONDS_BEFORE_CLOSE = 15  # entrar a T-15s (margen para latencia blockchain)
    MIN_DELTA_TO_TRADE = 0.005  # 0.005% minimo para operar
    MEDIUM_DELTA = 0.02  # 0.02% para confianza media
    HIGH_DELTA = 0.10  # 0.10% para confianza alta

    KELLY_FRACTION = 0.25  # Quarter Kelly
    MAX_BET_FRACTION = 0.05  # maximo 5% del bankroll
    MIN_BET_USDC = 5.0  # apuesta minima (Polymarket requiere min 5 shares)

    # Fee en mercados crypto a ~50%
    FEE_AT_50PCT = 0.0156  # 1.56%

    # Auto-ajuste y protección de capital
    MAX_CONSECUTIVE_LOSSES = 3  # después de 3 losses seguidos → pausar y subir umbral
    MAX_DRAWDOWN_PCT = 15.0  # si perdemos 15% del capital inicial → STOP total
    COOLDOWN_AFTER_LOSSES = 3  # skipear N ventanas después de racha perdedora

    def __init__(self, bankroll: float = 100.0):
        self.price_feed = BinancePriceFeed()
        self.bankroll = bankroll
        self.initial_bankroll = bankroll
        self.window_open_price = 0.0
        self.trade_history = []
        self.consecutive_losses = 0
        self.cooldown_remaining = 0
        self.adaptation_level = 0  # 0=normal, 1=cauteloso, 2=muy cauteloso
        self._adapt_thresholds()

    def _adapt_thresholds(self):
        """Ajusta umbrales según el nivel de adaptación"""
        if self.adaptation_level == 0:  # Normal
            self.MIN_DELTA_TO_TRADE = 0.005
            self.MEDIUM_DELTA = 0.02
            self.HIGH_DELTA = 0.10
            self.ENTRY_SECONDS_BEFORE_CLOSE = 15
            self.MAX_BET_FRACTION = 0.05
            self.min_confidence_to_trade = 0.25
        elif self.adaptation_level == 1:  # Cauteloso (después de 3 losses)
            self.MIN_DELTA_TO_TRADE = 0.03
            self.MEDIUM_DELTA = 0.06
            self.HIGH_DELTA = 0.15
            self.ENTRY_SECONDS_BEFORE_CLOSE = 10  # entrar más tarde = más certeza
            self.MAX_BET_FRACTION = 0.03
            self.min_confidence_to_trade = 0.50
            logger.info("ADAPTACION: Modo cauteloso - umbrales subidos, bets más chicos")
        elif self.adaptation_level >= 2:  # Muy cauteloso (después de 6 losses)
            self.MIN_DELTA_TO_TRADE = 0.05
            self.MEDIUM_DELTA = 0.10
            self.HIGH_DELTA = 0.20
            self.ENTRY_SECONDS_BEFORE_CLOSE = 8  # entrar MUY tarde
            self.MAX_BET_FRACTION = 0.02
            self.min_confidence_to_trade = 0.65
            logger.info("ADAPTACION: Modo muy cauteloso - solo señales fuertes")

    def check_capital_protection(self) -> dict:
        """Verifica si debemos seguir operando o parar"""
        drawdown_pct = (self.initial_bankroll - self.bankroll) / self.initial_bankroll * 100

        result = {
            "can_trade": True,
            "drawdown_pct": drawdown_pct,
            "consecutive_losses": self.consecutive_losses,
            "adaptation_level": self.adaptation_level,
            "cooldown_remaining": self.cooldown_remaining,
            "reason": "OK",
        }

        # Stop total si drawdown > 15%
        if drawdown_pct >= self.MAX_DRAWDOWN_PCT:
            result["can_trade"] = False
            result["reason"] = f"STOP: Drawdown {drawdown_pct:.1f}% >= {self.MAX_DRAWDOWN_PCT}%"
            return result

        # Cooldown activo
        if self.cooldown_remaining > 0:
            result["can_trade"] = False
            result["reason"] = f"Cooldown: {self.cooldown_remaining} ventanas restantes"
            self.cooldown_remaining -= 1
            return result

        # Auto-ajuste por racha perdedora
        if self.consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            new_level = min(self.consecutive_losses // self.MAX_CONSECUTIVE_LOSSES, 2)
            if new_level != self.adaptation_level:
                self.adaptation_level = new_level
                self._adapt_thresholds()
                self.cooldown_remaining = self.COOLDOWN_AFTER_LOSSES
                result["can_trade"] = False
                result["reason"] = f"Adaptando: {self.consecutive_losses} losses seguidos → nivel {self.adaptation_level}, cooldown {self.COOLDOWN_AFTER_LOSSES}"
                return result

        return result

    def record_result(self, signal: TradeSignal, won: bool, payout: float):
        """Registra el resultado y actualiza auto-ajuste"""
        self.trade_history.append({
            "timestamp": datetime.now().isoformat(),
            "direction": signal.direction,
            "confidence": signal.confidence,
            "delta": signal.window_delta_pct,
            "estimated_prob": signal.estimated_probability,
            "market_price": signal.market_price,
            "bet_size": signal.bet_size_usdc,
            "won": won,
            "payout": payout,
            "reason": signal.reason,
        })

        if won:
            self.bankroll += payout - signal.bet_size_usdc
            self.consecutive_losses = 0
            # Si ganamos 2 seguidos y estamos en modo cauteloso, relajar
            recent_wins = sum(1 for t in self.trade_history[-3:] if t["won"])
            if recent_wins >= 2 and self.adaptation_level > 0:
                self.adaptation_level = max(0, self.adaptation_level - 1)
                self._adapt_thresholds()
                logger.info(f"ADAPTACION: Racha ganadora → nivel bajado a {self.adaptation_level}")
        else:
            self.bankroll -= signal.bet_size_usdc
            self.consecutive_losses += 1

    def get_window_times(self) -> Tuple[int, int, int]:
        """
        Calcula los timestamps de apertura, cierre y entry de la ventana actual.
        Las ventanas de 5 min se alinean a multiplos de 300.
        Returns: (window_open_ts, window_close_ts, entry_ts)
        """
        now = int(time.time())
        window_open = now - (now % 300)
        window_close = window_open + 300
        entry_time = window_close - self.ENTRY_SECONDS_BEFORE_CLOSE
        return window_open, window_close, entry_time

    def register_window_open(self) -> float:
        """Registra el precio de apertura de la ventana"""
        self.window_open_price = self.price_feed.get_btc_price()
        logger.info(f"Window open price: ${self.window_open_price:,.2f}")
        return self.window_open_price

    def calculate_signal(self, market_price_up: float = 0.50) -> Optional[TradeSignal]:
        """
        Calcula la senal de trading basada en el Window Delta.
        Llamar a T-10s del cierre.

        Args:
            market_price_up: precio actual del token "Up" en Polymarket
        """
        if self.window_open_price <= 0:
            return None

        current_price = self.price_feed.get_btc_price()
        if current_price <= 0:
            return None

        # Window Delta
        delta_pct = (current_price - self.window_open_price) / self.window_open_price * 100
        abs_delta = abs(delta_pct)

        # Determinar direccion y confianza
        if abs_delta >= self.HIGH_DELTA:
            direction = "Up" if delta_pct > 0 else "Down"
            confidence = min(0.95, 0.70 + abs_delta * 2)
            reason = f"Delta alto ({delta_pct:+.4f}%), momentum fuerte"
        elif abs_delta >= self.MEDIUM_DELTA:
            direction = "Up" if delta_pct > 0 else "Down"
            confidence = 0.40 + abs_delta * 5
            reason = f"Delta medio ({delta_pct:+.4f}%), momentum moderado"
        elif abs_delta >= self.MIN_DELTA_TO_TRADE:
            direction = "Up" if delta_pct > 0 else "Down"
            confidence = 0.30
            reason = f"Delta bajo ({delta_pct:+.4f}%), senal debil"
        else:
            # Delta muy pequeno - sesgo estructural "Up" (>= cuenta como Up)
            direction = "Up"
            confidence = 0.20
            reason = f"Delta minimo ({delta_pct:+.4f}%), sesgo Up por regla >="

        # Obtener micro momentum (ultimas 2 velas de 1 min)
        klines = self.price_feed.get_btc_klines(interval="1m", limit=3)
        if len(klines) >= 2:
            last_candle_delta = float(klines[-1][4]) - float(klines[-1][1])  # close - open
            prev_candle_delta = float(klines[-2][4]) - float(klines[-2][1])

            # Confirma momentum
            if direction == "Up" and last_candle_delta > 0 and prev_candle_delta > 0:
                confidence = min(confidence + 0.10, 0.95)
                reason += " + micro momentum confirma"
            elif direction == "Down" and last_candle_delta < 0 and prev_candle_delta < 0:
                confidence = min(confidence + 0.10, 0.95)
                reason += " + micro momentum confirma"
            # Contradice momentum
            elif direction == "Up" and last_candle_delta < 0:
                confidence = max(confidence - 0.10, 0.10)
                reason += " + micro momentum contradice"
            elif direction == "Down" and last_candle_delta > 0:
                confidence = max(confidence - 0.10, 0.10)
                reason += " + micro momentum contradice"

        # Estimacion de probabilidad
        estimated_prob = 0.50 + (confidence * 0.30)  # mapea a 50-80%

        # Precio de mercado para nuestra direccion
        if direction == "Up":
            mkt_price = market_price_up
        else:
            mkt_price = 1.0 - market_price_up

        # Kelly criterion
        if estimated_prob > mkt_price:
            kelly = (estimated_prob - mkt_price) / (1.0 - mkt_price)
        else:
            kelly = 0

        # Bet size con Quarter Kelly y cap
        raw_bet = self.bankroll * kelly * self.KELLY_FRACTION
        bet_size = min(raw_bet, self.bankroll * self.MAX_BET_FRACTION)
        bet_size = max(bet_size, 0)

        # No operar si el edge no justifica el fee
        net_edge = estimated_prob - mkt_price - self.FEE_AT_50PCT
        if net_edge <= 0 and confidence < 0.50:
            bet_size = 0
            reason += f" | Edge insuficiente ({net_edge:.3f})"

        # Minimo de apuesta
        if 0 < bet_size < self.MIN_BET_USDC:
            bet_size = self.MIN_BET_USDC

        return TradeSignal(
            direction=direction,
            confidence=confidence,
            window_delta_pct=delta_pct,
            btc_open_price=self.window_open_price,
            btc_current_price=current_price,
            estimated_probability=estimated_prob,
            market_price=mkt_price,
            kelly_fraction=kelly,
            bet_size_usdc=round(bet_size, 2),
            reason=reason,
        )

    def should_trade(self, signal: TradeSignal) -> bool:
        """Decide si ejecutar el trade basado en la señal + protección de capital"""
        # Chequear protección de capital
        protection = self.check_capital_protection()
        if not protection["can_trade"]:
            logger.info(f"PROTECCION: {protection['reason']}")
            return False

        if signal.bet_size_usdc <= 0:
            return False
        if signal.confidence < self.min_confidence_to_trade:
            return False
        if signal.kelly_fraction <= 0:
            return False
        return True

    def get_stats(self) -> dict:
        """Estadisticas de performance"""
        if not self.trade_history:
            return {"trades": 0}

        wins = sum(1 for t in self.trade_history if t["won"])
        losses = len(self.trade_history) - wins
        total_profit = sum(
            t["payout"] - t["bet_size"] if t["won"] else -t["bet_size"]
            for t in self.trade_history
        )

        return {
            "trades": len(self.trade_history),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(self.trade_history) * 100,
            "total_profit": total_profit,
            "bankroll": self.bankroll,
        }
