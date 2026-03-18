"""
Botardo Polymarket Live Trader
Ejecuta la estrategia Late-Window Momentum en mercados BTC 5-min.
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import os
import time
import json
import logging
import requests
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from dotenv import load_dotenv

load_dotenv()

from polymarket.strategy import LateWindowMomentum, BinancePriceFeed
from polymarket.trader import PolymarketTrader

logging.basicConfig(
    filename="logs/polymarket_live.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("botardo")
console = Console()

# Telegram alertas
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
    except:
        pass

def main():
    console.print("[bold magenta]BOTARDO Polymarket Live Trader[/bold magenta]")
    console.print("[dim]Estrategia: Late-Window Momentum en BTC 5-min[/dim]\n")

    # Conectar a Polymarket
    trader = PolymarketTrader()
    if not trader.connect():
        console.print("[red]Error conectando a Polymarket[/red]")
        return
    console.print("[green]Polymarket CLOB conectado[/green]")

    # Inicializar estrategia con bankroll actual
    # Verificar USDC en wallet
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider("https://polygon-bor-rpc.publicnode.com"))
    usdc_addr = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e (bridged) - lo que usa Polymarket
    abi = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]
    usdc = w3.eth.contract(address=Web3.to_checksum_address(usdc_addr), abi=abi)
    wallet = os.getenv("POLYMARKET_WALLET_ADDRESS", "")
    balance = usdc.functions.balanceOf(Web3.to_checksum_address(wallet)).call() / 1e6

    console.print(f"[cyan]Balance USDC: ${balance:.2f}[/cyan]")

    strategy = LateWindowMomentum(bankroll=balance)
    price_feed = BinancePriceFeed()

    send_telegram(f"*Botardo Live Trader iniciado*\nBankroll: ${balance:.2f} USDC\nEstrategia: Late-Window Momentum BTC 5-min")

    ronda = 0

    STOP_LOSS_USD = 40.0  # si el balance baja de $40, parar todo

    while True:
        try:
            ronda += 1

            # Check stop loss con balance real cada 10 rondas
            if ronda % 10 == 1:
                real_bal = usdc.functions.balanceOf(Web3.to_checksum_address(wallet)).call() / 1e6
                strategy.bankroll = real_bal
                if real_bal <= STOP_LOSS_USD:
                    msg = f"STOP LOSS: Balance ${real_bal:.2f} <= ${STOP_LOSS_USD:.2f}. Bot detenido."
                    console.print(f"[bold red]{msg}[/bold red]")
                    send_telegram(f"*{msg}*")
                    logger.info(msg)
                    break

            now = int(time.time())
            window_open = now - (now % 300)
            window_close = window_open + 300
            entry_time = window_close - strategy.ENTRY_SECONDS_BEFORE_CLOSE

            # Registrar precio de apertura
            if abs(now - window_open) < 5:
                strategy.register_window_open()
            elif strategy.window_open_price == 0:
                strategy.register_window_open()

            seconds_to_close = window_close - now
            seconds_to_entry = entry_time - now

            # Mostrar estado
            btc_now = price_feed.get_btc_price()
            if strategy.window_open_price > 0 and btc_now > 0:
                delta = (btc_now - strategy.window_open_price) / strategy.window_open_price * 100
            else:
                delta = 0

            console.print(
                f"[dim]Ronda {ronda} | BTC: ${btc_now:,.2f} | "
                f"Delta: {delta:+.4f}% | "
                f"Cierre en: {seconds_to_close}s | "
                f"Entry en: {max(0, seconds_to_entry)}s | "
                f"Bankroll: ${strategy.bankroll:.2f}[/dim]"
            )

            # A la hora de entrar
            if seconds_to_entry <= 0 and seconds_to_close > 3:
                # Buscar el mercado activo
                markets = trader.find_5min_btc_markets()

                # Encontrar el mercado que cierra en esta ventana
                current_market = None
                for m in markets:
                    ts = m.get("_timestamp", 0)
                    if abs(ts - window_close) < 60:
                        current_market = m
                        break

                if current_market:
                    # Obtener precio del mercado
                    prices_str = current_market.get("outcomePrices", "[]")
                    if isinstance(prices_str, str):
                        prices = [float(p) for p in json.loads(prices_str)]
                    else:
                        prices = [float(p) for p in prices_str]

                    market_price_up = prices[0] if prices else 0.50

                    # Calcular senal
                    signal = strategy.calculate_signal(market_price_up)

                    if signal and strategy.should_trade(signal):
                        console.print(Panel(
                            f"[bold]Senal: {signal.direction}[/bold]\n"
                            f"Confianza: {signal.confidence:.0%}\n"
                            f"Delta: {signal.window_delta_pct:+.4f}%\n"
                            f"BTC: ${signal.btc_open_price:,.2f} -> ${signal.btc_current_price:,.2f}\n"
                            f"Prob estimada: {signal.estimated_probability:.0%}\n"
                            f"Precio mercado: ${signal.market_price:.3f}\n"
                            f"Bet: ${signal.bet_size_usdc:.2f}\n"
                            f"Razon: {signal.reason}",
                            title="[bold green]TRADE SIGNAL[/bold green]",
                            border_style="green",
                        ))

                        # Determinar token ID
                        token_ids_str = current_market.get("clobTokenIds", "[]")
                        if isinstance(token_ids_str, str):
                            token_ids = json.loads(token_ids_str)
                        else:
                            token_ids = token_ids_str or []

                        if len(token_ids) >= 2:
                            # token_ids[0] = Up, token_ids[1] = Down
                            tid = token_ids[0] if signal.direction == "Up" else token_ids[1]

                            # Ejecutar orden FOK (se llena o se cancela, sin quedar colgada)
                            result = trader.place_market_order(
                                token_id=tid,
                                side="BUY",
                                price=min(signal.market_price + 0.02, 0.99),  # +2 cents de slippage para asegurar fill
                                size=signal.bet_size_usdc,
                            )

                            if result.get("success"):
                                console.print(f"[bold green]ORDEN EJECUTADA: {signal.direction} ${signal.bet_size_usdc:.2f} @ ${signal.market_price:.3f}[/bold green]")
                                send_telegram(
                                    f"*Trade ejecutado*\n"
                                    f"Direccion: *{signal.direction}*\n"
                                    f"Monto: ${signal.bet_size_usdc:.2f}\n"
                                    f"Confianza: {signal.confidence:.0%}\n"
                                    f"Delta BTC: {signal.window_delta_pct:+.4f}%\n"
                                    f"Razon: {signal.reason}"
                                )
                                logger.info(f"TRADE: {signal.direction} ${signal.bet_size_usdc:.2f} conf={signal.confidence:.2f} delta={signal.window_delta_pct:+.4f}%")

                                # === ESPERAR CIERRE Y VERIFICAR RESULTADO CON BALANCE REAL ===
                                # Leer balance ANTES del cierre
                                balance_before = usdc.functions.balanceOf(Web3.to_checksum_address(wallet)).call() / 1e6

                                remaining = window_close - int(time.time())
                                if remaining > 0:
                                    console.print(f"[dim]Esperando {remaining}s al cierre...[/dim]")
                                    time.sleep(remaining + 10)  # +10s para resolución on-chain

                                # Leer balance DESPUÉS del cierre (balance real on-chain)
                                balance_after = usdc.functions.balanceOf(Web3.to_checksum_address(wallet)).call() / 1e6
                                real_profit = balance_after - balance_before

                                # Determinar WIN/LOSS por balance real, no por precio BTC
                                btc_close = price_feed.get_btc_price()
                                won = real_profit > 0
                                profit = real_profit
                                payout = balance_after if won else 0

                                # Actualizar bankroll con balance real
                                strategy.bankroll = balance_after

                                # Registrar resultado en la estrategia (auto-ajuste)
                                strategy.record_result(signal, won, abs(profit) if won else 0)

                                # Mostrar resultado
                                btc_went_up = btc_close >= signal.btc_open_price

                                if won:
                                    console.print(Panel(
                                        f"[bold green]GANAMOS![/bold green]\n"
                                        f"BTC: ${signal.btc_open_price:,.2f} -> ${btc_close:,.2f}\n"
                                        f"Apostamos: {signal.direction}\n"
                                        f"Profit real: ${profit:+.2f}\n"
                                        f"Balance real: ${balance_after:.2f}",
                                        title="[bold green]WIN[/bold green]",
                                        border_style="green",
                                    ))
                                    send_telegram(
                                        f"*WIN!*\n"
                                        f"BTC: ${signal.btc_open_price:,.2f} -> ${btc_close:,.2f}\n"
                                        f"Apostamos: *{signal.direction}*\n"
                                        f"Profit real: *${profit:+.2f}*\n"
                                        f"Balance real: *${balance_after:.2f}*"
                                    )
                                else:
                                    console.print(Panel(
                                        f"[bold red]PERDIMOS[/bold red]\n"
                                        f"BTC: ${signal.btc_open_price:,.2f} -> ${btc_close:,.2f}\n"
                                        f"Apostamos: {signal.direction}\n"
                                        f"Loss real: ${profit:+.2f}\n"
                                        f"Balance real: ${balance_after:.2f}\n"
                                        f"Losses seguidos: {strategy.consecutive_losses}",
                                        title="[bold red]LOSS[/bold red]",
                                        border_style="red",
                                    ))
                                    send_telegram(
                                        f"*LOSS*\n"
                                        f"BTC: ${signal.btc_open_price:,.2f} -> ${btc_close:,.2f}\n"
                                        f"Apostamos: *{signal.direction}*\n"
                                        f"Loss real: *${profit:+.2f}*\n"
                                        f"Balance real: *${balance_after:.2f}*\n"
                                        f"Losses seguidos: {strategy.consecutive_losses}"
                                    )

                                logger.info(f"RESULTADO: {'WIN' if won else 'LOSS'} profit=${profit:+.2f} bankroll=${strategy.bankroll:.2f}")

                                # Registrar nueva ventana
                                strategy.window_open_price = 0
                                continue  # saltar al siguiente ciclo

                            else:
                                console.print(f"[red]Orden fallida: {result.get('error', 'unknown')}[/red]")
                                logger.error(f"Order failed: {result}")
                    elif signal:
                        console.print(f"[yellow]Skip: {signal.reason}[/yellow]")

                    # Esperar al cierre de ventana si no tradeamos
                    remaining = window_close - int(time.time())
                    if remaining > 0 and remaining < 20:
                        time.sleep(remaining + 2)

                    # Registrar nueva ventana
                    strategy.window_open_price = 0
                else:
                    console.print("[dim]No se encontro mercado BTC 5-min activo[/dim]")

            # Mostrar stats cada 10 rondas
            if ronda % 10 == 0:
                stats = strategy.get_stats()
                if stats["trades"] > 0:
                    console.print(
                        f"\n[cyan]Stats: {stats['trades']} trades | "
                        f"Win rate: {stats['win_rate']:.1f}% | "
                        f"P&L: ${stats['total_profit']:+.2f} | "
                        f"Bankroll: ${stats['bankroll']:.2f}[/cyan]\n"
                    )

            time.sleep(2)  # poll cada 2 segundos

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Trader detenido.[/bold yellow]")
            stats = strategy.get_stats()
            console.print(f"Stats finales: {stats}")
            send_telegram(f"*Botardo detenido*\nStats: {json.dumps(stats)}")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.error(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
