# ============================================================
# execution/binance_executor.py — Ejecutor de ordenes en Binance (spot)
# ============================================================

import hmac
import hashlib
import time
import logging
from urllib.parse import urlencode

import requests

import config

logger = logging.getLogger("botardo")


class BinanceExecutor:
    """
    Cliente para la API REST de Binance (spot market).

    Permite consultar balance, colocar ordenes limite,
    verificar estado y cancelar ordenes.
    Todas las requests autenticadas llevan HMAC SHA256 signature.
    """

    BASE_URL = "https://api.binance.com"

    def __init__(self):
        self.api_key = config.BINANCE_API_KEY
        self.secret_key = config.BINANCE_SECRET_KEY

    # ── Helpers internos ──────────────────────────────────────

    def _sign(self, params: dict) -> dict:
        """Agrega timestamp y firma HMAC SHA256 a los parametros."""
        params["timestamp"] = int(time.time() * 1000)
        query_string = urlencode(params)
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = signature
        return params

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key}

    def _has_keys(self) -> bool:
        """Retorna True si las API keys estan configuradas."""
        return bool(self.api_key) and bool(self.secret_key)

    def _get(self, path: str, params: dict, signed: bool = True) -> dict:
        """GET request generico con manejo de errores."""
        if signed:
            if not self._has_keys():
                return {"error": "API keys no configuradas"}
            params = self._sign(params)

        url = f"{self.BASE_URL}{path}"
        try:
            response = requests.get(
                url,
                params=params,
                headers=self._headers() if signed else {},
                timeout=config.REQUEST_TIMEOUT_SEC,
            )
            data = response.json()

            if response.status_code != 200:
                code = data.get("code", response.status_code)
                msg = data.get("msg", "Error desconocido")
                logger.error(f"Binance API error [{code}]: {msg}")
                return {"error": f"[{code}] {msg}"}

            return data
        except requests.exceptions.Timeout:
            logger.error("Binance API timeout")
            return {"error": "Timeout en request a Binance"}
        except Exception as e:
            logger.error(f"Binance API excepcion: {e}")
            return {"error": str(e)}

    def _post(self, path: str, params: dict) -> dict:
        """POST request generico con manejo de errores."""
        if not self._has_keys():
            return {"error": "API keys no configuradas"}

        params = self._sign(params)
        url = f"{self.BASE_URL}{path}"
        try:
            response = requests.post(
                url,
                params=params,
                headers=self._headers(),
                timeout=config.REQUEST_TIMEOUT_SEC,
            )
            data = response.json()

            if response.status_code != 200:
                code = data.get("code", response.status_code)
                msg = data.get("msg", "Error desconocido")
                # -2015 = Invalid API-key, IP, or permissions for action
                if code == -2015:
                    logger.warning(
                        f"Binance: sin permisos para esta operacion ({msg}). "
                        "Verificar que la API key tenga permisos de trading."
                    )
                else:
                    logger.error(f"Binance API error [{code}]: {msg}")
                return {"error": f"[{code}] {msg}"}

            return data
        except requests.exceptions.Timeout:
            logger.error("Binance API timeout en POST")
            return {"error": "Timeout en request a Binance"}
        except Exception as e:
            logger.error(f"Binance API excepcion POST: {e}")
            return {"error": str(e)}

    def _delete(self, path: str, params: dict) -> dict:
        """DELETE request generico con manejo de errores."""
        if not self._has_keys():
            return {"error": "API keys no configuradas"}

        params = self._sign(params)
        url = f"{self.BASE_URL}{path}"
        try:
            response = requests.delete(
                url,
                params=params,
                headers=self._headers(),
                timeout=config.REQUEST_TIMEOUT_SEC,
            )
            data = response.json()

            if response.status_code != 200:
                code = data.get("code", response.status_code)
                msg = data.get("msg", "Error desconocido")
                if code == -2015:
                    logger.warning(
                        f"Binance: sin permisos para cancelar orden ({msg})."
                    )
                else:
                    logger.error(f"Binance API error [{code}]: {msg}")
                return {"error": f"[{code}] {msg}"}

            return data
        except requests.exceptions.Timeout:
            logger.error("Binance API timeout en DELETE")
            return {"error": "Timeout en request a Binance"}
        except Exception as e:
            logger.error(f"Binance API excepcion DELETE: {e}")
            return {"error": str(e)}

    # ── Metodos publicos ──────────────────────────────────────

    def get_balance(self, asset: str = "USDT") -> dict:
        """
        Obtiene balance de un asset especifico.

        Retorna:
            {"asset": "USDT", "free": 1000.0, "locked": 0.0}
            o {"error": "..."} si falla.
        """
        data = self._get("/api/v3/account", {})
        if "error" in data:
            return data

        if "balances" not in data:
            return {"error": f"Respuesta inesperada: {str(data)[:200]}"}

        for balance in data["balances"]:
            if balance["asset"] == asset:
                return {
                    "asset": asset,
                    "free": float(balance["free"]),
                    "locked": float(balance["locked"]),
                }

        return {"asset": asset, "free": 0.0, "locked": 0.0}

    def place_limit_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> dict:
        """
        Coloca una orden limite en el spot market.

        Args:
            symbol:   Par de trading (ej: "USDTARS")
            side:     "BUY" o "SELL"
            quantity: Cantidad del base asset
            price:    Precio limite

        Retorna:
            Respuesta de Binance con orderId, status, etc.
            o {"error": "..."} si falla.
        """
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": f"{quantity:.8f}".rstrip("0").rstrip("."),
            "price": f"{price:.8f}".rstrip("0").rstrip("."),
        }

        logger.info(
            f"Colocando orden {side} {quantity} {symbol} @ {price}"
        )

        result = self._post("/api/v3/order", params)

        if "error" not in result:
            logger.info(
                f"Orden creada: orderId={result.get('orderId')} "
                f"status={result.get('status')}"
            )
        return result

    def get_order_status(self, symbol: str, order_id: int) -> dict:
        """
        Consulta el estado de una orden existente.

        Args:
            symbol:   Par de trading (ej: "USDTARS")
            order_id: ID de la orden retornado por place_limit_order

        Retorna:
            Respuesta de Binance con status, executedQty, etc.
            o {"error": "..."} si falla.
        """
        params = {
            "symbol": symbol,
            "orderId": order_id,
        }
        return self._get("/api/v3/order", params)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """
        Cancela una orden abierta.

        Args:
            symbol:   Par de trading (ej: "USDTARS")
            order_id: ID de la orden a cancelar

        Retorna:
            Respuesta de Binance con status de cancelacion.
            o {"error": "..."} si falla.
        """
        params = {
            "symbol": symbol,
            "orderId": order_id,
        }

        logger.info(f"Cancelando orden {order_id} en {symbol}")

        result = self._delete("/api/v3/order", params)

        if "error" not in result:
            logger.info(
                f"Orden {order_id} cancelada: status={result.get('status')}"
            )
        return result

    def test_connection(self) -> bool:
        """
        Verifica que las credenciales funcionen consultando el balance.
        Retorna True si la conexion es exitosa, False en caso contrario.
        """
        if not self._has_keys():
            logger.warning("Binance: API keys no configuradas")
            return False

        data = self._get("/api/v3/account", {})
        if "error" in data:
            logger.warning(f"Binance: test de conexion fallido: {data['error']}")
            return False

        logger.info("Binance: conexion verificada OK")
        return True
