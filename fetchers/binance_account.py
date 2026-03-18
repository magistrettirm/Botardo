"""
Consulta de balance en Binance usando API key (read-only).
Útil para ver cuánto USDT y ARS (o stablecoins) hay disponibles.
"""
import hmac
import hashlib
import time
import requests
from config import BINANCE_API_KEY, BINANCE_SECRET_KEY

BINANCE_BASE = "https://api.binance.com"

def get_account_balance() -> dict:
    """
    Obtiene el balance de la cuenta de Binance.
    Retorna dict con {asset: free_amount} para los activos relevantes.
    """
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return {"error": "API keys no configuradas"}

    timestamp = int(time.time() * 1000)
    params = f"timestamp={timestamp}"

    signature = hmac.new(
        BINANCE_SECRET_KEY.encode('utf-8'),
        params.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    url = f"{BINANCE_BASE}/api/v3/account?{params}&signature={signature}"

    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()

        if "balances" not in data:
            return {"error": str(data)}

        # Filtrar solo los activos relevantes con saldo > 0
        relevant = ["USDT", "USDC", "BTC", "ETH", "BNB", "ARS", "BUSD"]
        balances = {}
        for b in data["balances"]:
            if b["asset"] in relevant and float(b["free"]) > 0:
                balances[b["asset"]] = {
                    "free": float(b["free"]),
                    "locked": float(b["locked"])
                }
        return balances
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    print("Balance Binance:")
    balance = get_account_balance()
    for asset, info in balance.items():
        if isinstance(info, dict):
            print(f"  {asset}: {info['free']:.4f} libre, {info['locked']:.4f} bloqueado")
        else:
            print(f"  Error: {info}")
