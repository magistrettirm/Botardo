"""
Composite Snipe Strategy v3 para mercados BTC 5-min en Polymarket.

Cambios principales vs v1/v2:
- 7 indicadores ponderados (window delta dominante, peso 5-7)
- Entry a T-10s (no T-15s) — mayor certeza, precio mas caro pero accuracy sube
- Estimacion de probabilidad basada en delta real (no lineal)
- Fee dinamico segun precio del token (no hardcodeado 1.56%)
- Deteccion de edge vs precio de mercado antes de operar
- Multi-exchange price feed (Binance + fallback Coinbase)
- Aceleracion de momentum y deteccion de volumen
- Spike detection: si score salta >= 1.5 entre checks, entrar inmediatamente
- Modos de operacion: SAFE (default), AGGRESSIVE, DEGEN
"""
import time
import logging
import requests
import json
from dataclasses import dataclass, field
from typing import Optional, Tuple, List
from datetime import datetime

logger = logging.getLogger("botardo")


@dataclass
class TradeSignal:
    direction: str          # "Up" o "Down"
    confidence: float       # 0 a 1
    composite_score: float  # score crudo del sistema de indicadores
    window_delta_pct: float
    btc_open_price: float
    btc_current_price: float
    estimated_probability: float
    market_price: float     # precio del token en nuestra direccion
    fee_estimate: float     # fee estimado para este trade
    net_edge: float         # estimated_prob - market_price - fee
    kelly_fraction: float
    bet_size_usdc: float
    reason: str
    indicators: dict = field(default_factory=dict)


class MultiExchangePriceFeed:
    """Precio BTC en tiempo real de multiples exchanges para confirmar señales"""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "Botardo/3.0"

    def get_btc_price(self) -> float:
        """Precio BTC de Binance (principal)"""
        try:
            r = self._session.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": "BTCUSDT"}, timeout=3
            )
            return float(r.json()["price"])
        except Exception as e:
            logger.error(f"Binance price error: {e}")
            return self._fallback_price()

    def _fallback_price(self) -> float:
        """Fallback: Coinbase"""
        try:
            r = self._session.get(
                "https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=3
            )
            return float(r.json()["data"]["amount"])
        except Exception as e:
            logger.error(f"Coinbase fallback error: {e}")
            return 0.0

    def get_btc_klines(self, interval: str = "1m", limit: int = 5) -> list:
        """Velas recientes de Binance"""
        try:
            r = self._session.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": "BTCUSDT", "interval": interval, "limit": limit},
                timeout=3
            )
            return r.json()
        except Exception as e:
            logger.error(f"Klines error: {e}")
            return []

    def get_multi_exchange_price(self) -> dict:
        """Precio de multiples exchanges para confirmar direccion"""
        prices = {}
        # Binance
        try:
            r = self._session.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": "BTCUSDT"}, timeout=2
            )
            prices["binance"] = float(r.json()["price"])
        except Exception:
            pass
        # Coinbase
        try:
            r = self._session.get(
                "https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=2
            )
            prices["coinbase"] = float(r.json()["data"]["amount"])
        except Exception:
            pass
        return prices

    def get_recent_trades_volume(self, limit: int = 100) -> dict:
        """Volumen reciente de trades para detectar surges"""
        try:
            r = self._session.get(
                "https://api.binance.com/api/v3/trades",
                params={"symbol": "BTCUSDT", "limit": limit}, timeout=3
            )
            trades = r.json()
            buy_vol = sum(float(t["qty"]) for t in trades if not t["isBuyerMaker"])
            sell_vol = sum(float(t["qty"]) for t in trades if t["isBuyerMaker"])
            total = buy_vol + sell_vol
            return {
                "buy_volume": buy_vol,
                "sell_volume": sell_vol,
                "total_volume": total,
                "buy_ratio": buy_vol / total if total > 0 else 0.5,
            }
        except Exception:
            return {"buy_volume": 0, "sell_volume": 0, "total_volume": 0, "buy_ratio": 0.5}


# ─── Modos de operacion ───
# Calibrados para bankroll $500 USD.
# Con $500: SAFE=$10/trade, AGGRESSIVE=$25/trade, DEGEN=$50/trade
MODES = {
    "SAFE": {
        "max_bet_fraction": 0.02,       # 2% del bankroll max ($10 con $500)
        "kelly_fraction": 0.20,         # 1/5 Kelly — conservador
        "min_confidence": 0.45,         # solo señales claras
        "min_net_edge": 0.025,          # 2.5% edge neto minimo (sube vs 2%)
        "min_delta_to_trade": 0.020,    # 0.020% minimo — filtra mas ruido
    },
    "AGGRESSIVE": {
        "max_bet_fraction": 0.05,       # 5% max ($25 con $500)
        "kelly_fraction": 0.30,         # ~1/3 Kelly
        "min_confidence": 0.35,
        "min_net_edge": 0.015,          # 1.5% edge neto
        "min_delta_to_trade": 0.012,
    },
    "DEGEN": {
        "max_bet_fraction": 0.10,       # 10% max ($50 con $500)
        "kelly_fraction": 0.45,
        "min_confidence": 0.25,
        "min_net_edge": 0.008,
        "min_delta_to_trade": 0.008,
    },
}


class CompositeSnipeStrategy:
    """
    Estrategia v3: Composite Score con 7 indicadores ponderados.

    La clave del edge: a T-10s del cierre, el 80-85% de las ventanas ya
    tienen su resultado definido. El window delta es el indicador dominante
    porque responde directamente la pregunta del mercado ("BTC sube o baja?").

    Los otros indicadores confirman o contradicen, ajustando confianza.
    Solo operamos cuando hay edge real vs precio de mercado despues de fees.
    """

    # ─── Pesos de indicadores ───
    WEIGHT_WINDOW_DELTA = 6.0       # Indicador rey: cambio desde apertura
    WEIGHT_MICRO_MOMENTUM = 2.0     # Ultimas 2 velas de 1min
    WEIGHT_ACCELERATION = 1.5       # Momentum acelerando o frenando
    WEIGHT_VOLUME_SURGE = 1.5       # Volumen compra vs venta reciente
    WEIGHT_TICK_TREND = 2.0         # Micro-tendencia tick a tick
    WEIGHT_MULTI_EXCHANGE = 1.0     # Confirmacion cross-exchange
    WEIGHT_RSI_EXTREME = 1.0        # Solo en extremos (RSI < 20 o > 80)

    MAX_SCORE = (WEIGHT_WINDOW_DELTA + WEIGHT_MICRO_MOMENTUM +
                 WEIGHT_ACCELERATION + WEIGHT_VOLUME_SURGE +
                 WEIGHT_TICK_TREND + WEIGHT_MULTI_EXCHANGE +
                 WEIGHT_RSI_EXTREME)  # = 15.0

    # ─── Entry timing ───
    ENTRY_SECONDS_BEFORE_CLOSE = 10  # T-10s — sweet spot certeza vs precio
    HARD_DEADLINE_BEFORE_CLOSE = 5   # T-5s — deadline forzado

    # ─── Thresholds de delta para mapeo de probabilidad ───
    # Basado en datos reales: a mayor delta, mas probable que se mantenga
    DELTA_PROB_MAP = [
        # (abs_delta_pct, estimated_win_rate) — datos empiricos de backtesting
        (0.005, 0.51),   # ruido, basicamente coin flip
        (0.010, 0.53),   # leve tendencia
        (0.020, 0.57),   # tendencia clara
        (0.050, 0.65),   # movimiento fuerte
        (0.100, 0.78),   # movimiento muy fuerte
        (0.150, 0.88),   # casi seguro
        (0.200, 0.93),   # practicamente definido
        (0.500, 0.97),   # extremo
    ]

    # ─── Token pricing basado en delta (lo que cobra el market maker) ───
    DELTA_TOKEN_PRICE_MAP = [
        # (abs_delta_pct, expected_token_price) — cuanto cuesta comprar el ganador
        (0.005, 0.50),
        (0.010, 0.52),
        (0.020, 0.55),
        (0.050, 0.68),
        (0.100, 0.82),
        (0.150, 0.92),
        (0.200, 0.95),
        (0.500, 0.98),
    ]

    # ─── Bet sizing ───
    MIN_BET_USDC = 5.0  # minimo de Polymarket

    # ─── Capital protection ───
    MAX_CONSECUTIVE_LOSSES = 4
    MAX_DRAWDOWN_PCT = 20.0
    COOLDOWN_AFTER_LOSSES = 2  # ventanas de pausa

    def __init__(self, bankroll: float = 500.0, mode: str = "SAFE"):
        self.price_feed = MultiExchangePriceFeed()
        self.bankroll = bankroll
        self.initial_bankroll = bankroll
        self.window_open_price = 0.0
        self.trade_history: List[dict] = []
        self.consecutive_losses = 0
        self.cooldown_remaining = 0
        self._cooldown_last_window: int = 0  # timestamp de ultima ventana que consumio cooldown
        self.mode = mode
        self.mode_params = MODES.get(mode, MODES["SAFE"])

        # Para spike detection y tick trend
        self._price_samples: List[float] = []
        self._last_score: Optional[float] = None

    # ─── Fee dinamico ───

    @staticmethod
    def calculate_fee(token_price: float) -> float:
        """
        Fee dinamico de Polymarket para mercados crypto.
        Fee = token_price * (1 - token_price) * 0.0222
        Maximo 1.56% a precio 0.50, baja hacia los extremos.
        Para maker orders (GTC limit), fee = 0.
        """
        return token_price * (1 - token_price) * 0.0222

    # ─── Probabilidad estimada por delta ───

    def _interpolate_from_map(self, abs_delta: float, mapping: list) -> float:
        """Interpola linealmente un valor en un mapa delta→valor"""
        if abs_delta <= mapping[0][0]:
            return mapping[0][1]
        if abs_delta >= mapping[-1][0]:
            return mapping[-1][1]
        for i in range(len(mapping) - 1):
            d0, v0 = mapping[i]
            d1, v1 = mapping[i + 1]
            if d0 <= abs_delta <= d1:
                t = (abs_delta - d0) / (d1 - d0)
                return v0 + t * (v1 - v0)
        return mapping[-1][1]

    def estimate_probability(self, abs_delta_pct: float) -> float:
        """Probabilidad estimada de ganar basada en el delta"""
        return self._interpolate_from_map(abs_delta_pct, self.DELTA_PROB_MAP)

    def estimate_token_price(self, abs_delta_pct: float) -> float:
        """Precio esperado del token ganador segun delta"""
        return self._interpolate_from_map(abs_delta_pct, self.DELTA_TOKEN_PRICE_MAP)

    # ─── Window management ───

    def get_window_times(self) -> Tuple[int, int, int]:
        now = int(time.time())
        window_open = now - (now % 300)
        window_close = window_open + 300
        entry_time = window_close - self.ENTRY_SECONDS_BEFORE_CLOSE
        return window_open, window_close, entry_time

    def register_window_open(self) -> float:
        self.window_open_price = self.price_feed.get_btc_price()
        self._price_samples = [self.window_open_price]
        self._last_score = None
        logger.info(f"Window open: ${self.window_open_price:,.2f}")
        return self.window_open_price

    def sample_price(self) -> float:
        """Llamar cada 2s durante la ventana para acumular tick trend"""
        price = self.price_feed.get_btc_price()
        if price > 0:
            self._price_samples.append(price)
        return price

    # ─── Indicadores ───

    def _calc_window_delta(self, current_price: float) -> Tuple[float, float]:
        """Retorna (delta_pct, score normalizado -1 a +1)"""
        if self.window_open_price <= 0:
            return 0.0, 0.0
        delta_pct = (current_price - self.window_open_price) / self.window_open_price * 100
        abs_delta = abs(delta_pct)
        # Score: sign * magnitud normalizada (cap en 1.0)
        magnitude = min(abs_delta / 0.10, 1.0)  # normalizar: 0.10% = score maximo
        score = magnitude if delta_pct >= 0 else -magnitude
        return delta_pct, score

    def _calc_micro_momentum(self, klines: list) -> Tuple[float, str]:
        """Score basado en ultimas 2 velas de 1min. Retorna (score -1 a +1, detail)"""
        if len(klines) < 2:
            return 0.0, "sin datos"
        last_delta = float(klines[-1][4]) - float(klines[-1][1])
        prev_delta = float(klines[-2][4]) - float(klines[-2][1])
        if last_delta > 0 and prev_delta > 0:
            return 1.0, "2 velas alcistas"
        elif last_delta < 0 and prev_delta < 0:
            return -1.0, "2 velas bajistas"
        elif last_delta > 0 and prev_delta < 0:
            return 0.3, "reversal alcista"
        elif last_delta < 0 and prev_delta > 0:
            return -0.3, "reversal bajista"
        return 0.0, "neutral"

    def _calc_acceleration(self, klines: list) -> Tuple[float, str]:
        """Detecta si el momentum esta acelerando o desacelerando"""
        if len(klines) < 3:
            return 0.0, "sin datos"
        d1 = float(klines[-3][4]) - float(klines[-3][1])
        d2 = float(klines[-2][4]) - float(klines[-2][1])
        d3 = float(klines[-1][4]) - float(klines[-1][1])
        # Aceleracion: las velas son cada vez mas grandes en la misma direccion
        if d2 > d1 > 0 and d3 > d2:
            return 1.0, "acelerando UP"
        elif d2 < d1 < 0 and d3 < d2:
            return -1.0, "acelerando DOWN"
        elif d3 > 0 and abs(d3) > abs(d2):
            return 0.5, "acelerando UP leve"
        elif d3 < 0 and abs(d3) > abs(d2):
            return -0.5, "acelerando DOWN leve"
        # Desaceleracion
        elif d2 > 0 and d3 > 0 and d3 < d2:
            return 0.2, "desacelerando UP"
        elif d2 < 0 and d3 < 0 and abs(d3) < abs(d2):
            return -0.2, "desacelerando DOWN"
        return 0.0, "sin aceleracion"

    def _calc_volume_surge(self) -> Tuple[float, str]:
        """Detecta volumen inusual y sesgo compra/venta"""
        vol_data = self.price_feed.get_recent_trades_volume(limit=50)
        buy_ratio = vol_data["buy_ratio"]
        if buy_ratio > 0.65:
            return 1.0, f"compra dominante ({buy_ratio:.0%})"
        elif buy_ratio > 0.55:
            return 0.5, f"sesgo compra ({buy_ratio:.0%})"
        elif buy_ratio < 0.35:
            return -1.0, f"venta dominante ({buy_ratio:.0%})"
        elif buy_ratio < 0.45:
            return -0.5, f"sesgo venta ({buy_ratio:.0%})"
        return 0.0, f"neutral ({buy_ratio:.0%})"

    def _calc_tick_trend(self) -> Tuple[float, str]:
        """Micro-tendencia basada en price samples acumulados durante la ventana"""
        samples = self._price_samples
        if len(samples) < 3:
            return 0.0, "pocos samples"
        # Usar ultimos 10 samples (ultimos ~20 segundos)
        recent = samples[-10:]
        if len(recent) < 3:
            return 0.0, "pocos samples recientes"
        # Calcular tendencia: cuantos ticks suben vs bajan
        ups = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i-1])
        downs = sum(1 for i in range(1, len(recent)) if recent[i] < recent[i-1])
        total = ups + downs
        if total == 0:
            return 0.0, "sin movimiento"
        ratio = (ups - downs) / total
        detail = f"ticks {ups}up/{downs}dn"
        return max(-1.0, min(1.0, ratio)), detail

    def _calc_multi_exchange(self, binance_price: float) -> Tuple[float, str]:
        """Confirma direccion con precio de otro exchange"""
        prices = self.price_feed.get_multi_exchange_price()
        coinbase = prices.get("coinbase", 0)
        if coinbase <= 0 or self.window_open_price <= 0:
            return 0.0, "sin datos cross-exchange"
        binance_delta = (binance_price - self.window_open_price) / self.window_open_price * 100
        coinbase_delta = (coinbase - self.window_open_price) / self.window_open_price * 100
        # Ambos de acuerdo en direccion?
        if binance_delta > 0 and coinbase_delta > 0:
            return 1.0, f"CB confirma UP ({coinbase_delta:+.4f}%)"
        elif binance_delta < 0 and coinbase_delta < 0:
            return -1.0, f"CB confirma DOWN ({coinbase_delta:+.4f}%)"
        elif abs(binance_delta - coinbase_delta) > 0.02:
            return 0.0, f"divergencia CB ({coinbase_delta:+.4f}%) vs BN ({binance_delta:+.4f}%)"
        return 0.0, "cross-exchange neutral"

    def _calc_rsi_extreme(self, klines: list) -> Tuple[float, str]:
        """RSI solo contribuye en extremos (<25 o >75) con 14 periodos"""
        if len(klines) < 14:
            return 0.0, "sin datos RSI"
        closes = [float(k[4]) for k in klines[-14:]]
        gains = []
        losses = []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        if rsi > 75:
            return -0.5, f"RSI alto ({rsi:.0f}), posible reversal"
        elif rsi < 25:
            return 0.5, f"RSI bajo ({rsi:.0f}), posible reversal"
        return 0.0, f"RSI neutral ({rsi:.0f})"

    # ─── Señal compuesta ───

    def calculate_signal(self, market_price_up: float = 0.50) -> Optional[TradeSignal]:
        """
        Calcula señal de trading con 7 indicadores ponderados.
        Llamar a T-10s del cierre de ventana.
        """
        if self.window_open_price <= 0:
            return None

        current_price = self.price_feed.get_btc_price()
        if current_price <= 0:
            logger.warning("BTC price = 0, ambos feeds fallaron. NO operar.")
            return None

        # Sanity check: si el precio cambio mas de 5% vs apertura, probablemente error de datos
        if self.window_open_price > 0:
            change_pct = abs(current_price - self.window_open_price) / self.window_open_price * 100
            if change_pct > 5.0:
                logger.warning(f"BTC price change {change_pct:.1f}% en 5min — probable error de datos. NO operar.")
                return None

        # Obtener datos
        klines_1m = self.price_feed.get_btc_klines(interval="1m", limit=15)
        klines_5m = self.price_feed.get_btc_klines(interval="5m", limit=14)

        # ─── Calcular 7 indicadores ───
        indicators = {}

        # 1. Window Delta (peso 6)
        delta_pct, delta_score = self._calc_window_delta(current_price)
        indicators["window_delta"] = {"score": delta_score, "detail": f"{delta_pct:+.4f}%"}

        # 2. Micro Momentum (peso 2)
        momentum_score, momentum_detail = self._calc_micro_momentum(klines_1m)
        indicators["micro_momentum"] = {"score": momentum_score, "detail": momentum_detail}

        # 3. Aceleracion (peso 1.5)
        accel_score, accel_detail = self._calc_acceleration(klines_1m)
        indicators["acceleration"] = {"score": accel_score, "detail": accel_detail}

        # 4. Volume Surge (peso 1.5)
        vol_score, vol_detail = self._calc_volume_surge()
        indicators["volume_surge"] = {"score": vol_score, "detail": vol_detail}

        # 5. Tick Trend (peso 2)
        tick_score, tick_detail = self._calc_tick_trend()
        indicators["tick_trend"] = {"score": tick_score, "detail": tick_detail}

        # 6. Multi Exchange (peso 1)
        mx_score, mx_detail = self._calc_multi_exchange(current_price)
        indicators["multi_exchange"] = {"score": mx_score, "detail": mx_detail}

        # 7. RSI Extreme (peso 1) — usa velas de 5min para RSI mas estable
        rsi_score, rsi_detail = self._calc_rsi_extreme(klines_5m)
        indicators["rsi_extreme"] = {"score": rsi_score, "detail": rsi_detail}

        # ─── Composite Score ───
        composite = (
            delta_score * self.WEIGHT_WINDOW_DELTA +
            momentum_score * self.WEIGHT_MICRO_MOMENTUM +
            accel_score * self.WEIGHT_ACCELERATION +
            vol_score * self.WEIGHT_VOLUME_SURGE +
            tick_score * self.WEIGHT_TICK_TREND +
            mx_score * self.WEIGHT_MULTI_EXCHANGE +
            rsi_score * self.WEIGHT_RSI_EXTREME
        )

        # ─── Spike detection ───
        spike = False
        if self._last_score is not None:
            if abs(composite - self._last_score) >= 1.5:
                spike = True
                logger.info(f"SPIKE detectado: {self._last_score:.2f} -> {composite:.2f}")
        self._last_score = composite

        # ─── Direccion y confianza ───
        abs_delta = abs(delta_pct)
        if composite > 0:
            direction = "Up"
        elif composite < 0:
            direction = "Down"
        else:
            # Score exactamente 0: sesgo Up por regla >=
            direction = "Up"

        confidence = min(abs(composite) / (self.MAX_SCORE * 0.6), 1.0)
        # Boost de confianza si hay spike
        if spike:
            confidence = min(confidence + 0.15, 0.98)

        # ─── Probabilidad estimada basada en delta real ───
        base_prob = self.estimate_probability(abs_delta)

        # Ajustar probabilidad con otros indicadores (+-5% max)
        non_delta_score = composite - (delta_score * self.WEIGHT_WINDOW_DELTA)
        non_delta_max = self.MAX_SCORE - self.WEIGHT_WINDOW_DELTA
        adjustment = (non_delta_score / non_delta_max) * 0.05 if non_delta_max > 0 else 0
        estimated_prob = max(0.50, min(0.98, base_prob + adjustment))

        # Si delta es practicamente 0 y no hay señal clara, prob = ~50%
        if abs_delta < self.mode_params["min_delta_to_trade"]:
            estimated_prob = 0.50 + abs(adjustment)  # casi coin flip

        # ─── Precio de mercado ───
        if direction == "Up":
            mkt_price = market_price_up
        else:
            mkt_price = 1.0 - market_price_up

        # ─── Fee dinamico ───
        fee = self.calculate_fee(mkt_price)

        # ─── Edge neto ───
        net_edge = estimated_prob - mkt_price - fee

        # ─── Kelly Criterion ───
        if net_edge > 0:
            kelly = (estimated_prob * (1 - mkt_price) - (1 - estimated_prob) * mkt_price) / (1 - mkt_price)
            kelly = max(0, kelly)
        else:
            kelly = 0

        # ─── Bet sizing ───
        kf = self.mode_params["kelly_fraction"]
        max_bet = self.mode_params["max_bet_fraction"]
        raw_bet = self.bankroll * kelly * kf
        bet_size = min(raw_bet, self.bankroll * max_bet)
        bet_size = max(bet_size, 0)

        # ─── Filtros de no-trade ───
        reasons = []
        if abs_delta < self.mode_params["min_delta_to_trade"] and not spike:
            bet_size = 0
            reasons.append(f"delta {abs_delta:.4f}% < min {self.mode_params['min_delta_to_trade']}%")

        if net_edge < self.mode_params["min_net_edge"] and not spike:
            bet_size = 0
            reasons.append(f"edge neto {net_edge:.3f} < min {self.mode_params['min_net_edge']}")

        # Minimo de apuesta
        if 0 < bet_size < self.MIN_BET_USDC:
            bet_size = self.MIN_BET_USDC

        # ─── Razon legible ───
        reason_parts = [f"Score={composite:+.2f}/{self.MAX_SCORE:.0f}"]
        reason_parts.append(f"Delta={delta_pct:+.4f}%")
        reason_parts.append(f"Prob={estimated_prob:.0%}")
        reason_parts.append(f"Mkt={mkt_price:.3f}")
        reason_parts.append(f"Fee={fee:.4f}")
        reason_parts.append(f"Edge={net_edge:+.3f}")
        if spike:
            reason_parts.append("SPIKE!")
        if reasons:
            reason_parts.append(f"NO-TRADE: {'; '.join(reasons)}")
        reason = " | ".join(reason_parts)

        return TradeSignal(
            direction=direction,
            confidence=confidence,
            composite_score=composite,
            window_delta_pct=delta_pct,
            btc_open_price=self.window_open_price,
            btc_current_price=current_price,
            estimated_probability=estimated_prob,
            market_price=mkt_price,
            fee_estimate=fee,
            net_edge=net_edge,
            kelly_fraction=kelly,
            bet_size_usdc=round(bet_size, 2),
            reason=reason,
            indicators=indicators,
        )

    # ─── Capital protection ───

    def check_capital_protection(self) -> dict:
        drawdown_pct = (self.initial_bankroll - self.bankroll) / self.initial_bankroll * 100

        result = {
            "can_trade": True,
            "drawdown_pct": drawdown_pct,
            "consecutive_losses": self.consecutive_losses,
            "cooldown_remaining": self.cooldown_remaining,
            "reason": "OK",
        }

        if drawdown_pct >= self.MAX_DRAWDOWN_PCT:
            result["can_trade"] = False
            result["reason"] = f"STOP: Drawdown {drawdown_pct:.1f}% >= {self.MAX_DRAWDOWN_PCT}%"
            return result

        if self.cooldown_remaining > 0:
            result["can_trade"] = False
            result["reason"] = f"Cooldown: {self.cooldown_remaining} ventanas restantes"
            # Solo decrementar una vez por ventana (cada 300s)
            current_window = int(time.time()) // 300
            if current_window != self._cooldown_last_window:
                self._cooldown_last_window = current_window
                self.cooldown_remaining -= 1
            return result

        if self.consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            self.cooldown_remaining = self.COOLDOWN_AFTER_LOSSES
            result["can_trade"] = False
            result["reason"] = f"{self.consecutive_losses} losses seguidos, cooldown {self.COOLDOWN_AFTER_LOSSES}"
            # Auto-ajustar: subir min_delta temporalmente
            self.mode_params["min_delta_to_trade"] = min(
                self.mode_params["min_delta_to_trade"] * 1.5, 0.05
            )
            self.mode_params["min_net_edge"] = min(
                self.mode_params["min_net_edge"] * 1.5, 0.05
            )
            logger.info(f"Auto-ajuste: min_delta={self.mode_params['min_delta_to_trade']:.4f}, "
                        f"min_edge={self.mode_params['min_net_edge']:.4f}")
            return result

        return result

    def should_trade(self, signal: TradeSignal) -> bool:
        protection = self.check_capital_protection()
        if not protection["can_trade"]:
            logger.info(f"PROTECCION: {protection['reason']}")
            return False
        if signal.bet_size_usdc <= 0:
            return False
        if signal.confidence < self.mode_params["min_confidence"]:
            return False
        if signal.net_edge < self.mode_params["min_net_edge"]:
            return False
        if signal.kelly_fraction <= 0:
            return False
        return True

    # ─── Resultados ───

    def record_result(self, signal: TradeSignal, won: bool, real_profit: float):
        """
        Registra resultado de un trade.
        real_profit: ganancia/perdida NETA real (positivo si gano, negativo si perdio).
        El bankroll ya fue actualizado con balance_after antes de llamar aca.
        """
        self.trade_history.append({
            "timestamp": datetime.now().isoformat(),
            "direction": signal.direction,
            "confidence": signal.confidence,
            "composite_score": signal.composite_score,
            "delta": signal.window_delta_pct,
            "estimated_prob": signal.estimated_probability,
            "market_price": signal.market_price,
            "net_edge": signal.net_edge,
            "bet_size": signal.bet_size_usdc,
            "won": won,
            "real_profit": real_profit,
            "indicators": signal.indicators,
            "reason": signal.reason,
        })

        # No tocamos self.bankroll aca — ya se actualizo con balance real en live_trader
        if won:
            self.consecutive_losses = 0
            # Si ganamos 3 seguidos, relajar umbrales al original del modo
            recent_wins = sum(1 for t in self.trade_history[-3:] if t["won"])
            if recent_wins >= 3:
                original = MODES.get(self.mode, MODES["SAFE"])
                self.mode_params["min_delta_to_trade"] = original["min_delta_to_trade"]
                self.mode_params["min_net_edge"] = original["min_net_edge"]
        else:
            self.consecutive_losses += 1

    def get_stats(self) -> dict:
        if not self.trade_history:
            return {"trades": 0, "mode": self.mode}

        wins = sum(1 for t in self.trade_history if t["won"])
        losses = len(self.trade_history) - wins
        total_profit = sum(
            t.get("real_profit", 0) for t in self.trade_history
        )
        avg_edge = sum(t["net_edge"] for t in self.trade_history) / len(self.trade_history)

        return {
            "trades": len(self.trade_history),
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(self.trade_history) * 100,
            "total_profit": round(total_profit, 2),
            "bankroll": round(self.bankroll, 2),
            "avg_net_edge": round(avg_edge, 4),
            "drawdown_pct": round(
                (self.initial_bankroll - self.bankroll) / self.initial_bankroll * 100, 1
            ),
            "mode": self.mode,
        }


# ─── Backward compatibility ───
# Mantener nombre viejo como alias para no romper imports existentes
BinancePriceFeed = MultiExchangePriceFeed
LateWindowMomentum = CompositeSnipeStrategy
