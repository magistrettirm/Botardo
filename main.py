#!/usr/bin/env python3
# ============================================================
# main.py — Entry point de BOTARDO: Scanner de arbitraje USDT/ARS
# ============================================================

# Forzar UTF-8 en stdout/stderr para evitar problemas en terminales Windows
import sys
import io
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

import config
from core.models import ExchangePrice
from core.scanner import scan, mejor_spread_info
from alerts.notifier import notify
from execution.manager import ExecutionManager
from execution.p2p_analyzer import P2PAnalyzer

# Importar todos los fetchers
from fetchers import binance_p2p, buenbit, ripio, satoshi_tango

# ── Logging a archivo ──────────────────────────────────────
logging.basicConfig(
    filename=config.LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
logger = logging.getLogger("botardo")

console = Console()

# Lista de fetchers disponibles (función get_price de cada módulo)
FETCHERS = [
    binance_p2p.get_price,
    buenbit.get_price,
    ripio.get_price,
    satoshi_tango.get_price,
]


def fetch_all_prices() -> List[ExchangePrice]:
    """
    Obtiene precios de todos los exchanges en paralelo usando ThreadPoolExecutor.
    Si un exchange falla, retorna su ExchangePrice con el error registrado.
    """
    resultados = []
    with ThreadPoolExecutor(max_workers=len(FETCHERS)) as executor:
        futuros = {executor.submit(fn): fn.__module__ for fn in FETCHERS}
        for futuro in as_completed(futuros):
            try:
                precio = futuro.result()
                resultados.append(precio)
                if precio.error:
                    logger.warning(f"Error en {precio.exchange}: {precio.error}")
                else:
                    logger.info(
                        f"{precio.exchange}: buy=${precio.buy_price:.2f} sell=${precio.sell_price:.2f}"
                    )
            except Exception as e:
                nombre = futuros[futuro]
                logger.error(f"Excepción inesperada en fetcher {nombre}: {e}")
    # Ordenar por nombre para display consistente
    resultados.sort(key=lambda p: p.exchange)
    return resultados


def mostrar_tabla(prices: List[ExchangePrice]) -> None:
    """
    Muestra la tabla de precios actuales en consola con rich.
    """
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tabla = Table(
        title=f"[bold cyan]BOTARDO — Scanner USDT/ARS[/bold cyan]\n[dim]{ahora}[/dim]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        expand=False,
    )
    tabla.add_column("Exchange", style="cyan", min_width=16)
    tabla.add_column("Compra (ask)", justify="right", style="green", min_width=14)
    tabla.add_column("Venta (bid)", justify="right", style="yellow", min_width=14)
    tabla.add_column("Estado", justify="center", min_width=8)

    for precio in prices:
        if precio.is_valid:
            tabla.add_row(
                precio.exchange,
                f"${precio.buy_price:>10,.2f}",
                f"${precio.sell_price:>10,.2f}",
                "[green]OK[/green]",
            )
        else:
            # Exchange con error: mostrar mensaje truncado
            error_corto = precio.error[:30] + "..." if len(precio.error) > 30 else precio.error
            tabla.add_row(
                precio.exchange,
                "[red]—[/red]",
                "[red]—[/red]",
                f"[red]ERR[/red]",
            )

    console.print(tabla)

    # Footer con la mejor oportunidad actual
    resumen = mejor_spread_info(prices)
    console.print(f"[dim]{resumen}[/dim]")
    console.print(f"[dim]Próximo scan en {config.SCAN_INTERVAL_SEC}s...[/dim]\n")


def mostrar_readiness(readiness: dict) -> None:
    """Muestra el estado de readiness de ejecucion en consola."""
    api = "[green]OK[/green]" if readiness["api_connected"] else "[red]NO[/red]"
    bal = "[green]OK[/green]" if readiness["has_balance"] else "[yellow]SIN SALDO[/yellow]"
    trd = "[green]ACTIVO[/green]" if readiness["trading_enabled"] else "[dim]DESHABILITADO[/dim]"

    console.print(
        f"[bold]Ejecucion Binance:[/bold] API={api}  Balance={bal}  "
        f"Trading={trd}  "
        f"USDT={readiness['balance_usdt']:.2f}  ARS={readiness['balance_ars']:.2f}"
    )
    console.print()


def main():
    """Loop principal del bot."""
    console.print(
        "[bold green]BOTARDO iniciado.[/bold green] "
        f"Escaneando USDT/ARS cada {config.SCAN_INTERVAL_SEC}s. "
        "Ctrl+C para detener.\n"
    )
    logger.info("=== BOTARDO iniciado ===")

    # Inicializar modulo de ejecucion
    exec_manager = ExecutionManager()

    # Inicializar analizador P2P
    p2p_analyzer = P2PAnalyzer()
    last_p2p_analysis = 0  # timestamp del ultimo analisis P2P

    # Verificar readiness al inicio
    console.print("[dim]Verificando conexion a Binance...[/dim]")
    readiness = exec_manager.check_readiness()
    mostrar_readiness(readiness)
    logger.info(f"Readiness: {readiness}")

    ciclo = 0
    alertas_enviadas = set()  # evitar spam de la misma oportunidad

    while True:
        ciclo += 1
        try:
            # 1. Obtener precios en paralelo
            prices = fetch_all_prices()

            # 2. Mostrar tabla de precios
            mostrar_tabla(prices)

            # 3. Detectar oportunidades
            oportunidades = scan(prices)

            if oportunidades:
                logger.info(f"Ciclo {ciclo}: {len(oportunidades)} oportunidad(es) detectada(s)")
                for opp in oportunidades:
                    # Clave única para evitar alertas repetidas en el mismo ciclo
                    clave = f"{opp.buy_exchange}->{opp.sell_exchange}"
                    notify(opp)
                    logger.info(
                        f"  OPORTUNIDAD: {opp.buy_exchange} → {opp.sell_exchange} "
                        f"spread_neto={opp.net_spread_pct:.2f}% "
                        f"ganancia_est=${opp.estimated_profit_ars:,.0f} ARS"
                    )

                    # Ejecutar si esta habilitado
                    if exec_manager.enabled:
                        exec_result = exec_manager.execute_opportunity(opp)
                        if exec_result.get("executed"):
                            order = exec_result["order"]
                            console.print(
                                f"[bold green]ORDEN EJECUTADA:[/bold green] "
                                f"{order['side']} {order['quantity']} USDT "
                                f"@ {order['price']} ARS "
                                f"(orderId={order['orderId']})"
                            )
                        elif exec_result.get("reason") != "disabled":
                            console.print(
                                f"[yellow]Orden no ejecutada: "
                                f"{exec_result.get('reason', 'desconocido')}[/yellow]"
                            )
            else:
                console.print("[dim]Sin oportunidades por encima del umbral "
                              f"({config.MIN_SPREAD_PCT}% neto).[/dim]\n")
                logger.info(f"Ciclo {ciclo}: sin oportunidades (umbral {config.MIN_SPREAD_PCT}%)")

            # 3b. Analisis P2P periodico
            now_ts = time.time()
            if now_ts - last_p2p_analysis >= config.P2P_ANALYSIS_INTERVAL:
                last_p2p_analysis = now_ts
                try:
                    p2p_opps = p2p_analyzer.analyze_internal_arbitrage()
                    if p2p_opps:
                        console.print(
                            f"\n[bold magenta]P2P Interno:[/bold magenta] "
                            f"{len(p2p_opps)} oportunidad(es) entre metodos de pago"
                        )
                        for opp in p2p_opps[:3]:
                            console.print(
                                f"  [magenta]{opp['buy_method']}[/magenta] "
                                f"${opp['buy_price']:,.2f} -> "
                                f"[magenta]{opp['sell_method']}[/magenta] "
                                f"${opp['sell_price']:,.2f} = "
                                f"[bold]{opp['spread_pct']:.2f}%[/bold]"
                            )
                        # Notificar por Telegram la mejor oportunidad P2P
                        best_p2p = p2p_opps[0]
                        if best_p2p["spread_pct"] > config.MIN_SPREAD_PCT:
                            report = p2p_analyzer.get_full_report()
                            notify_msg = (
                                f"P2P Interno: {best_p2p['buy_method']} -> "
                                f"{best_p2p['sell_method']} = {best_p2p['spread_pct']:.2f}%"
                            )
                            logger.info(notify_msg)
                    else:
                        console.print("[dim]P2P: sin oportunidades internas.[/dim]")
                except Exception as e:
                    logger.warning(f"Error en analisis P2P: {e}")

        except KeyboardInterrupt:
            console.print("\n[bold yellow]BOTARDO detenido por el usuario.[/bold yellow]")
            logger.info("=== BOTARDO detenido ===")
            break
        except Exception as e:
            console.print(f"[bold red]Error en el loop principal:[/bold red] {e}")
            logger.error(f"Error en loop principal: {e}")

        # 4. Esperar antes del siguiente ciclo
        try:
            time.sleep(config.SCAN_INTERVAL_SEC)
        except KeyboardInterrupt:
            console.print("\n[bold yellow]BOTARDO detenido por el usuario.[/bold yellow]")
            logger.info("=== BOTARDO detenido ===")
            break


if __name__ == "__main__":
    main()
