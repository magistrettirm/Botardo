# ============================================================
# execution/manager.py — Orquestador de ejecucion de ordenes
# ============================================================

import logging
from typing import List

import config
from core.models import Opportunity
from execution.binance_executor import BinanceExecutor

logger = logging.getLogger("botardo")


class ExecutionManager:
    """
    Orquestador de ejecucion: verifica readiness, ejecuta oportunidades
    de arbitraje y trackea ordenes activas.

    Por defecto la ejecucion esta deshabilitada (solo monitoreo).
    Se activa manualmente seteando self.enabled = True.
    """

    def __init__(self):
        self.executor = BinanceExecutor()
        self.active_orders: List[dict] = []
        self.enabled = False  # se activa manualmente

    def check_readiness(self) -> dict:
        """
        Verifica que todo este listo para ejecutar ordenes.

        Retorna un dict con el estado de cada requisito:
            api_connected:    True si la API de Binance responde
            has_balance:      True si hay USDT disponible
            trading_enabled:  True si self.enabled es True
            balance_usdt:     Saldo libre de USDT
            balance_ars:      Saldo libre de ARS
        """
        result = {
            "api_connected": False,
            "has_balance": False,
            "trading_enabled": self.enabled,
            "balance_usdt": 0.0,
            "balance_ars": 0.0,
        }

        # Verificar conexion a Binance
        result["api_connected"] = self.executor.test_connection()

        if not result["api_connected"]:
            return result

        # Consultar balance USDT
        usdt = self.executor.get_balance("USDT")
        if "error" not in usdt:
            result["balance_usdt"] = usdt.get("free", 0.0)

        # Consultar balance ARS
        ars = self.executor.get_balance("ARS")
        if "error" not in ars:
            result["balance_ars"] = ars.get("free", 0.0)

        # Hay balance si tiene USDT o ARS
        result["has_balance"] = result["balance_usdt"] > 0 or result["balance_ars"] > 0

        return result

    def execute_opportunity(self, opp: Opportunity) -> dict:
        """
        Ejecuta una oportunidad de arbitraje si la ejecucion esta habilitada.

        Por ahora solo soporta el lado Binance de la operacion:
        coloca una orden limite de compra o venta de USDT en Binance spot.

        Args:
            opp: Oportunidad de arbitraje detectada por el scanner.

        Retorna:
            dict con resultado de la ejecucion.
        """
        if not self.enabled:
            logger.info("Ejecucion deshabilitada - solo monitoreo")
            return {"executed": False, "reason": "disabled"}

        # Verificar que Binance este involucrado en la oportunidad
        binance_side = None
        if "Binance" in opp.buy_exchange:
            binance_side = "BUY"
        elif "Binance" in opp.sell_exchange:
            binance_side = "SELL"
        else:
            logger.info(
                f"Oportunidad {opp.buy_exchange} -> {opp.sell_exchange}: "
                "Binance no involucrado, no se ejecuta"
            )
            return {"executed": False, "reason": "binance_not_involved"}

        # Determinar parametros de la orden
        symbol = "USDTARS"
        quantity = config.CAPITAL_USDT
        price = opp.buy_price if binance_side == "BUY" else opp.sell_price

        logger.info(
            f"Ejecutando: {binance_side} {quantity} USDT @ {price} ARS "
            f"(spread neto {opp.net_spread_pct:.2f}%)"
        )

        # Colocar la orden
        result = self.executor.place_limit_order(
            symbol=symbol,
            side=binance_side,
            quantity=quantity,
            price=price,
        )

        if "error" in result:
            logger.error(f"Error al ejecutar orden: {result['error']}")
            return {"executed": False, "reason": "order_error", "detail": result["error"]}

        # Trackear la orden activa
        order_info = {
            "orderId": result.get("orderId"),
            "symbol": symbol,
            "side": binance_side,
            "quantity": quantity,
            "price": price,
            "status": result.get("status", "UNKNOWN"),
            "opportunity": f"{opp.buy_exchange} -> {opp.sell_exchange}",
        }
        self.active_orders.append(order_info)

        logger.info(
            f"Orden ejecutada: orderId={order_info['orderId']} "
            f"status={order_info['status']}"
        )

        return {"executed": True, "order": order_info}

    def check_active_orders(self) -> List[dict]:
        """
        Verifica el estado de todas las ordenes activas.
        Remueve las que ya estan completadas o canceladas.

        Retorna lista de ordenes actualizadas.
        """
        updated = []
        still_active = []

        for order in self.active_orders:
            status = self.executor.get_order_status(
                order["symbol"], order["orderId"]
            )

            if "error" in status:
                logger.warning(
                    f"No se pudo verificar orden {order['orderId']}: {status['error']}"
                )
                still_active.append(order)
                continue

            order["status"] = status.get("status", "UNKNOWN")
            updated.append(order)

            if order["status"] in ("FILLED", "CANCELED", "EXPIRED", "REJECTED"):
                logger.info(
                    f"Orden {order['orderId']} finalizada: {order['status']}"
                )
            else:
                still_active.append(order)

        self.active_orders = still_active
        return updated

    def cancel_all_orders(self) -> List[dict]:
        """
        Cancela todas las ordenes activas.
        Retorna lista de resultados de cancelacion.
        """
        results = []
        for order in self.active_orders:
            result = self.executor.cancel_order(order["symbol"], order["orderId"])
            results.append({
                "orderId": order["orderId"],
                "result": result,
            })

        self.active_orders = []
        return results
