from dotenv import load_dotenv
import os

load_dotenv()

# Binance
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Parámetros del bot
MIN_SPREAD_PCT = float(os.getenv("MIN_SPREAD_PCT", "1.5"))
SCAN_INTERVAL_SEC = int(os.getenv("SCAN_INTERVAL_SEC", "8"))
CAPITAL_USDT = float(os.getenv("CAPITAL_USDT", "1000"))

# Fees por exchange (estos van hardcodeados, no en .env)
FEE_BINANCE_P2P = 0.0
FEE_BUENBIT = 0.003
FEE_RIPIO = 0.005
FEE_SATOSHI = 0.003

# Timeout en segundos para requests HTTP
REQUEST_TIMEOUT_SEC = 10

# P2P Analysis
P2P_ANALYSIS_INTERVAL = int(os.getenv("P2P_ANALYSIS_INTERVAL", "60"))  # cada 60 segundos analisis P2P detallado

# Archivo de log
LOG_FILE = "logs/arbitrage.log"
