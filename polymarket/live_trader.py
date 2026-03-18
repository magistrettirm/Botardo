"""
Botardo Polymarket Live Trader v3
Ejecuta la estrategia Composite Snipe en mercados BTC 5-min.

Cambios vs v1/v2:
- Usa CompositeSnipeStrategy con 7 indicadores
- Acumula price samples durante la ventana para tick trend
- Intenta maker order (GTC) primero, fallback a FOK si no se llena
- Muestra indicadores detallados en el panel de trade
- Modo configurable via argumento: --mode SAFE|AGGRESSIVE|DEGEN
- Mejor logging con indicadores y edge
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
import argparse
import requests
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from dotenv import load_dotenv

load_dotenv()

from polymarket.strategy import CompositeSnipeStrategy, MultiExchangePriceFeed
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
    except Exception:
        pass


def format_indicators(indicators: dict) -> str:
    """Formatea indicadores para mostrar en panel"""
    lines = []
    for name, data in indicators.items():
        score = data.get("score", 0)
        detail = data.get("detail", "")
        color = "green" if score > 0 else "red" if score < 0 else "dim"
        lines.append(f"[{color}]{name}: {score:+.2f} ({detail})[/{color}]")
    return "\n".join(lines)


def execute_order(trader, token_id: str, signal, current_market: dict) -> dict:
    """
    Intenta ejecutar la orden. Estrategia:
    1. Primero intenta maker order (GTC limit) a precio justo — fee 0%
    2. Verifica si se lleno; si no, cancela y va a FOK
    3. Si el mercado cierra en <7s, directo FOK (market order) — paga taker fee
    """
    now = int(time.time())
    window_close_ts = current_market.get("_timestamp", 0)
    seconds_left = window_close_ts - now

    # Si quedan mas de 8 segundos, intentar maker order primero
    if seconds_left > 8:
        maker_price = round(signal.market_price - 0.01, 2)  # 1 cent mejor
        maker_price = max(0.01, min(maker_price, 0.99))
        result = trader.place_maker_order(
            token_id=token_id,
            side="BUY",
            price=maker_price,
            size=signal.bet_size_usdc,
        )
        if result.get("success"):
            order_id = result.get("response", {}).get("orderID") or result.get("response", {}).get("id")
            logger.info(f"Maker order publicada: BUY {signal.bet_size_usdc} @ {maker_price} | ID: {order_id}")
            # Esperar y verificar si se lleno
            time.sleep(2)
            filled = trader.check_order_filled(order_id)
            if filled:
                logger.info(f"Maker order FILLED: {order_id}")
                result["order_type"] = "maker"
                return result
            else:
                # No se lleno — cancelar y caer a FOK
                logger.info(f"Maker order NO filled, cancelando {order_id}")
                trader.cancel_order(order_id)
                time.sleep(0.5)

    # Fallback: FOK market order (paga taker fee pero se llena seguro)
    fok_price = min(signal.market_price + 0.02, 0.99)
    result = trader.place_market_order(
        token_id=token_id,
        side="BUY",
        price=fok_price,
        size=signal.bet_size_usdc,
    )
    if result.get("success"):
        result["order_type"] = "fok"
    return result


def save_dry_run_signal(signal, btc_close: float, won: bool, stats: dict):
    """Guarda señal de dry run en archivo JSON para analisis posterior"""
    log_file = "logs/dry_run_signals.json"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "direction": signal.direction,
        "composite_score": round(signal.composite_score, 3),
        "confidence": round(signal.confidence, 3),
        "window_delta_pct": round(signal.window_delta_pct, 5),
        "btc_open": round(signal.btc_open_price, 2),
        "btc_close": round(btc_close, 2),
        "estimated_prob": round(signal.estimated_probability, 4),
        "market_price": round(signal.market_price, 4),
        "fee_estimate": round(signal.fee_estimate, 5),
        "net_edge": round(signal.net_edge, 4),
        "kelly_fraction": round(signal.kelly_fraction, 4),
        "bet_size_usdc": round(signal.bet_size_usdc, 2),
        "would_have_won": won,
        "indicators": {k: {"score": round(v["score"], 3), "detail": v["detail"]}
                       for k, v in signal.indicators.items()},
        "stats_so_far": stats,
    }
    try:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = []
        data.append(entry)
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error guardando dry run signal: {e}")


def main():
    parser = argparse.ArgumentParser(description="Botardo Polymarket Live Trader v3")
    parser.add_argument("--mode", choices=["SAFE", "AGGRESSIVE", "DEGEN"],
                        default="SAFE", help="Modo de operacion")
    parser.add_argument("--stop-loss", type=float, default=400.0,
                        help="Stop loss en USD (default: 400 = 20%% drawdown de 500)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Modo dry run: no ejecuta ordenes, solo loggea señales y verifica resultado")
    parser.add_argument("--bankroll", type=float, default=0,
                        help="Bankroll simulado para dry run (default: lee balance real de wallet)")
    args = parser.parse_args()

    dry_run = args.dry_run
    mode_label = f"{args.mode} | DRY RUN" if dry_run else args.mode

    console.print(f"[bold magenta]BOTARDO Polymarket Live Trader v3[/bold magenta]")
    if dry_run:
        console.print(f"[bold yellow]*** MODO DRY RUN — NO SE EJECUTAN ORDENES ***[/bold yellow]")
    console.print(f"[dim]Estrategia: Composite Snipe | Modo: {mode_label} | Stop: ${args.stop_loss}[/dim]\n")

    # Conectar a Polymarket (necesario para leer precios de mercado incluso en dry run)
    trader = PolymarketTrader()
    if not trader.connect():
        if not dry_run:
            console.print("[red]Error conectando a Polymarket[/red]")
            return
        console.print("[yellow]CLOB no disponible — dry run usa solo Gamma API[/yellow]")

    if not dry_run:
        console.print("[green]Polymarket CLOB conectado[/green]")

    # Verificar USDC en wallet
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider("https://polygon-bor-rpc.publicnode.com"))
    usdc_addr = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # USDC native (Polymarket usa este)
    abi = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"}]
    usdc = w3.eth.contract(address=Web3.to_checksum_address(usdc_addr), abi=abi)
    wallet = os.getenv("POLYMARKET_WALLET_ADDRESS", "")

    if args.bankroll > 0:
        balance = args.bankroll
        console.print(f"[cyan]Bankroll simulado: ${balance:.2f}[/cyan]")
    else:
        try:
            balance = usdc.functions.balanceOf(Web3.to_checksum_address(wallet)).call() / 1e6
            console.print(f"[cyan]Balance USDC real: ${balance:.2f}[/cyan]")
        except Exception:
            balance = 500.0
            console.print(f"[yellow]No se pudo leer balance, usando ${balance:.2f} simulado[/yellow]")

    if dry_run and balance < 100:
        balance = 500.0
        console.print(f"[cyan]Dry run con bankroll simulado: ${balance:.2f}[/cyan]")

    strategy = CompositeSnipeStrategy(bankroll=balance, mode=args.mode)
    price_feed = MultiExchangePriceFeed()

    send_telegram(
        f"*Botardo v3 iniciado{'  DRY RUN' if dry_run else ''}*\n"
        f"Modo: *{mode_label}*\n"
        f"Bankroll: ${balance:.2f} USDC{' (simulado)' if dry_run else ''}\n"
        f"Stop loss: ${args.stop_loss:.2f}\n"
        f"Estrategia: Composite Snipe (7 indicadores)"
    )

    ronda = 0
    traded_this_window = False

    while True:
        try:
            ronda += 1

            # Check stop loss con balance real cada 10 rondas (skip en dry run)
            if not dry_run and ronda % 10 == 1:
                real_bal = usdc.functions.balanceOf(Web3.to_checksum_address(wallet)).call() / 1e6
                strategy.bankroll = real_bal
                if real_bal <= args.stop_loss:
                    msg = f"STOP LOSS: Balance ${real_bal:.2f} <= ${args.stop_loss:.2f}. Bot detenido."
                    console.print(f"[bold red]{msg}[/bold red]")
                    send_telegram(f"*{msg}*")
                    logger.info(msg)
                    break

            now = int(time.time())
            window_open = now - (now % 300)
            window_close = window_open + 300
            entry_time = window_close - strategy.ENTRY_SECONDS_BEFORE_CLOSE

            # Registrar precio de apertura SOLO al inicio real de ventana
            if abs(now - window_open) < 5:
                strategy.register_window_open()
                traded_this_window = False
            elif strategy.window_open_price == 0:
                # Bot arranco a mitad de ventana — NO registrar precio actual
                # como apertura, esperar la proxima ventana
                seconds_to_next = window_close - now
                if seconds_to_next > strategy.ENTRY_SECONDS_BEFORE_CLOSE + 5:
                    # Queda suficiente tiempo, pero marcar que es late-join
                    strategy.register_window_open()
                    traded_this_window = True  # skip esta ventana, delta estaria mal
                    console.print(f"[yellow]Late join: skip esta ventana, esperando la proxima[/yellow]")
                else:
                    traded_this_window = True  # skip

            seconds_to_close = window_close - now
            seconds_to_entry = entry_time - now

            # Acumular price sample para tick trend (cada poll)
            strategy.sample_price()

            # Mostrar estado
            btc_now = price_feed.get_btc_price()
            if strategy.window_open_price > 0 and btc_now > 0:
                delta = (btc_now - strategy.window_open_price) / strategy.window_open_price * 100
            else:
                delta = 0

            console.print(
                f"[dim]R{ronda} | BTC: ${btc_now:,.2f} | "
                f"D: {delta:+.4f}% | "
                f"Close: {seconds_to_close}s | "
                f"Entry: {max(0, seconds_to_entry)}s | "
                f"${strategy.bankroll:.2f} | {args.mode}[/dim]"
            )

            # A la hora de entrar (T-10s a T-5s)
            if (seconds_to_entry <= 0 and seconds_to_close > strategy.HARD_DEADLINE_BEFORE_CLOSE
                    and not traded_this_window):

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

                    # Calcular senal con sistema de 7 indicadores
                    signal = strategy.calculate_signal(market_price_up)

                    if signal and strategy.should_trade(signal):
                        # Panel detallado con todos los indicadores
                        indicators_text = format_indicators(signal.indicators)
                        panel_title = (f"[bold yellow]DRY RUN SIGNAL - {args.mode}[/bold yellow]"
                                       if dry_run else
                                       f"[bold green]TRADE SIGNAL - {args.mode}[/bold green]")
                        console.print(Panel(
                            f"[bold]Direccion: {signal.direction}[/bold]\n"
                            f"Score: {signal.composite_score:+.2f}/{strategy.MAX_SCORE:.0f}\n"
                            f"Confianza: {signal.confidence:.0%}\n"
                            f"Delta: {signal.window_delta_pct:+.4f}%\n"
                            f"BTC: ${signal.btc_open_price:,.2f} -> ${signal.btc_current_price:,.2f}\n"
                            f"Prob estimada: {signal.estimated_probability:.0%}\n"
                            f"Precio mkt: ${signal.market_price:.3f}\n"
                            f"Fee: ${signal.fee_estimate:.4f}\n"
                            f"Edge neto: {signal.net_edge:+.3f}\n"
                            f"Kelly: {signal.kelly_fraction:.3f}\n"
                            f"Bet: ${signal.bet_size_usdc:.2f}\n\n"
                            f"[bold]Indicadores:[/bold]\n{indicators_text}",
                            title=panel_title,
                            border_style="yellow" if dry_run else "green",
                        ))

                        traded_this_window = True
                        logger.info(
                            f"{'DRY_RUN ' if dry_run else ''}SIGNAL: {signal.direction} "
                            f"${signal.bet_size_usdc:.2f} "
                            f"score={signal.composite_score:+.2f} "
                            f"conf={signal.confidence:.2f} "
                            f"delta={signal.window_delta_pct:+.4f}% "
                            f"edge={signal.net_edge:+.3f}"
                        )

                        if dry_run:
                            # --- DRY RUN: no ejecutar, esperar cierre y verificar ---
                            remaining = window_close - int(time.time())
                            if remaining > 0:
                                console.print(f"[dim]Esperando {remaining}s al cierre para verificar...[/dim]")
                                time.sleep(remaining + 3)

                            btc_close = price_feed.get_btc_price()
                            if signal.direction == "Up":
                                won = btc_close > signal.btc_open_price
                            else:
                                won = btc_close < signal.btc_open_price

                            # Simular profit: si gano, payout = bet/price - bet; si perdio, -bet
                            if won:
                                sim_profit = (signal.bet_size_usdc / signal.market_price) - signal.bet_size_usdc
                            else:
                                sim_profit = -signal.bet_size_usdc

                            strategy.record_result(signal, won, sim_profit)
                            strategy.bankroll += sim_profit
                            stats = strategy.get_stats()

                            result_color = "green" if won else "red"
                            result_label = "WIN" if won else "LOSS"

                            console.print(Panel(
                                f"[bold {result_color}]{result_label} (DRY RUN)[/bold {result_color}]\n"
                                f"BTC: ${signal.btc_open_price:,.2f} -> ${btc_close:,.2f}\n"
                                f"Dir: {signal.direction} | Score: {signal.composite_score:+.2f}\n"
                                f"P/L simulado: ${sim_profit:+.2f}\n"
                                f"Bankroll sim: ${strategy.bankroll:.2f}\n"
                                f"Win rate: {stats.get('win_rate', 0):.1f}% ({stats.get('wins', 0)}/{stats.get('trades', 0)})\n"
                                f"Losses seguidos: {strategy.consecutive_losses}",
                                title=f"[bold {result_color}]{result_label} (DRY RUN)[/bold {result_color}]",
                                border_style=result_color,
                            ))
                            send_telegram(
                                f"*{result_label} (DRY RUN v3)*\n"
                                f"BTC: ${signal.btc_open_price:,.2f} -> ${btc_close:,.2f}\n"
                                f"Dir: *{signal.direction}* | Score: {signal.composite_score:+.2f}\n"
                                f"P/L sim: *${sim_profit:+.2f}*\n"
                                f"Bankroll: *${strategy.bankroll:.2f}*\n"
                                f"WR: {stats.get('win_rate', 0):.1f}% ({stats['wins']}/{stats['trades']})"
                            )
                            logger.info(
                                f"DRY_RUN RESULTADO: {result_label} "
                                f"profit_sim=${sim_profit:+.2f} "
                                f"bankroll=${strategy.bankroll:.2f} "
                                f"WR={stats.get('win_rate', 0):.1f}%"
                            )
                            save_dry_run_signal(signal, btc_close, won, stats)

                            strategy.window_open_price = 0
                            continue

                        # --- MODO REAL: ejecutar orden ---
                        # Determinar token ID
                        token_ids_str = current_market.get("clobTokenIds", "[]")
                        if isinstance(token_ids_str, str):
                            token_ids = json.loads(token_ids_str)
                        else:
                            token_ids = token_ids_str or []

                        if len(token_ids) >= 2:
                            tid = token_ids[0] if signal.direction == "Up" else token_ids[1]

                            result = execute_order(trader, tid, signal, current_market)

                            if result.get("success"):
                                console.print(
                                    f"[bold green]ORDEN EJECUTADA: "
                                    f"{signal.direction} ${signal.bet_size_usdc:.2f} "
                                    f"@ ${signal.market_price:.3f} "
                                    f"(edge: {signal.net_edge:+.3f})[/bold green]"
                                )
                                send_telegram(
                                    f"*Trade ejecutado (v3 {args.mode})*\n"
                                    f"Dir: *{signal.direction}*\n"
                                    f"Monto: ${signal.bet_size_usdc:.2f}\n"
                                    f"Conf: {signal.confidence:.0%}\n"
                                    f"Score: {signal.composite_score:+.2f}\n"
                                    f"Delta: {signal.window_delta_pct:+.4f}%\n"
                                    f"Edge: {signal.net_edge:+.3f}\n"
                                )
                                logger.info(
                                    f"TRADE: {signal.direction} "
                                    f"${signal.bet_size_usdc:.2f} "
                                    f"score={signal.composite_score:+.2f} "
                                    f"conf={signal.confidence:.2f} "
                                    f"delta={signal.window_delta_pct:+.4f}% "
                                    f"edge={signal.net_edge:+.3f}"
                                )

                                # Esperar cierre y verificar resultado
                                balance_before = usdc.functions.balanceOf(
                                    Web3.to_checksum_address(wallet)
                                ).call() / 1e6

                                remaining = window_close - int(time.time())
                                if remaining > 0:
                                    console.print(f"[dim]Esperando {remaining}s al cierre...[/dim]")
                                    time.sleep(remaining + 10)

                                balance_after = usdc.functions.balanceOf(
                                    Web3.to_checksum_address(wallet)
                                ).call() / 1e6
                                real_profit = balance_after - balance_before

                                btc_close = price_feed.get_btc_price()
                                won = real_profit > 0
                                profit = real_profit

                                strategy.bankroll = balance_after
                                # Pasar profit neto real (positivo o negativo)
                                strategy.record_result(signal, won, profit)

                                result_color = "green" if won else "red"
                                result_label = "WIN" if won else "LOSS"
                                stats = strategy.get_stats()

                                console.print(Panel(
                                    f"[bold {result_color}]{result_label}[/bold {result_color}]\n"
                                    f"BTC: ${signal.btc_open_price:,.2f} -> ${btc_close:,.2f}\n"
                                    f"Dir: {signal.direction} | Score: {signal.composite_score:+.2f}\n"
                                    f"P/L real: ${profit:+.2f}\n"
                                    f"Balance: ${balance_after:.2f}\n"
                                    f"Win rate: {stats.get('win_rate', 0):.1f}% ({stats.get('wins', 0)}/{stats.get('trades', 0)})\n"
                                    f"Losses seguidos: {strategy.consecutive_losses}",
                                    title=f"[bold {result_color}]{result_label}[/bold {result_color}]",
                                    border_style=result_color,
                                ))
                                send_telegram(
                                    f"*{result_label}* (v3)\n"
                                    f"BTC: ${signal.btc_open_price:,.2f} -> ${btc_close:,.2f}\n"
                                    f"Dir: *{signal.direction}* | Score: {signal.composite_score:+.2f}\n"
                                    f"P/L: *${profit:+.2f}*\n"
                                    f"Balance: *${balance_after:.2f}*\n"
                                    f"WR: {stats.get('win_rate', 0):.1f}%"
                                )
                                logger.info(
                                    f"RESULTADO: {result_label} "
                                    f"profit=${profit:+.2f} "
                                    f"bankroll=${strategy.bankroll:.2f} "
                                    f"WR={stats.get('win_rate', 0):.1f}%"
                                )

                                strategy.window_open_price = 0
                                continue

                            else:
                                console.print(
                                    f"[red]Orden fallida: {result.get('error', 'unknown')}[/red]"
                                )
                                logger.error(f"Order failed: {result}")

                    elif signal:
                        console.print(
                            f"[yellow]Skip: score={signal.composite_score:+.2f} "
                            f"conf={signal.confidence:.0%} "
                            f"edge={signal.net_edge:+.3f} | "
                            f"{signal.reason}[/yellow]"
                        )

                    # Esperar al cierre si no tradeamos
                    remaining = window_close - int(time.time())
                    if 0 < remaining < 20:
                        time.sleep(remaining + 2)
                    strategy.window_open_price = 0
                else:
                    console.print("[dim]No se encontro mercado BTC 5-min activo[/dim]")

            # Stats cada 20 rondas
            if ronda % 20 == 0:
                stats = strategy.get_stats()
                if stats["trades"] > 0:
                    dr_tag = " DRY RUN" if dry_run else ""
                    console.print(
                        f"\n[cyan]Stats{dr_tag}: {stats['trades']} trades | "
                        f"WR: {stats['win_rate']:.1f}% | "
                        f"P&L: ${stats['total_profit']:+.2f} | "
                        f"Avg edge: {stats['avg_net_edge']:+.4f} | "
                        f"DD: {stats['drawdown_pct']:.1f}% | "
                        f"${stats['bankroll']:.2f} | {mode_label}[/cyan]\n"
                    )

            time.sleep(2)

        except KeyboardInterrupt:
            dr_tag = " (DRY RUN)" if dry_run else ""
            console.print(f"\n[bold yellow]Trader detenido{dr_tag}.[/bold yellow]")
            stats = strategy.get_stats()
            console.print(f"Stats finales: {json.dumps(stats, indent=2)}")
            if dry_run and stats["trades"] > 0:
                wr = stats.get("win_rate", 0)
                verdict = "[green]EDGE DETECTADO" if wr > 52 else "[red]SIN EDGE CLARO"
                console.print(f"\n{verdict}: Win rate {wr:.1f}% en {stats['trades']} trades simulados[/]")
                console.print(f"[dim]Seniales guardadas en logs/dry_run_signals.json[/dim]")
            send_telegram(f"*Botardo v3 detenido{dr_tag}*\nStats: {json.dumps(stats)}")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.error(f"Error: {e}", exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
