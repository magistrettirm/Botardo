import os
from dotenv import load_dotenv

load_dotenv()

# Polymarket APIs (publicas, no requieren auth)
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

# Wallet (para cuando se configure)
POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
POLYMARKET_WALLET_ADDRESS = os.getenv("POLYMARKET_WALLET_ADDRESS", "")

# Parametros de scanning
POLY_SCAN_INTERVAL = int(os.getenv("POLY_SCAN_INTERVAL", "5"))  # segundos
MIN_ARB_EDGE = float(os.getenv("MIN_ARB_EDGE", "1.5"))  # % minimo de edge para alertar
MAX_SPREAD_COST = float(os.getenv("MAX_SPREAD_COST", "3.0"))  # fee estimado taker %

# Filtros de mercado
MIN_VOLUME = float(os.getenv("MIN_VOLUME", "10000"))  # volumen minimo USD
MIN_LIQUIDITY = float(os.getenv("MIN_LIQUIDITY", "5000"))  # liquidez minima USD
