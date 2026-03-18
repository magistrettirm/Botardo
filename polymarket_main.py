#!/usr/bin/env python3
"""
Botardo Polymarket Scanner - Monitoreo de oportunidades de arbitraje
Incluye trading module para deteccion de mercados 5-min BTC Up/Down
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import time
import logging
from rich.console import Console
from rich.table import Table
from rich import box

from polymarket.scanner import PolymarketScanner
from polymarket.trader import PolymarketTrader
from polymarket.allowance import AllowanceManager, CTF_EXCHANGE, NEG_RISK_CTF_EXCHANGE
from polymarket import config as poly_config

logging.basicConfig(
    filename="logs/polymarket.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger("botardo")
console = Console()


def mostrar_resultados(scan_result: dict):
    # Tabla de arbitraje
    binary = scan_result.get("binary_arbitrage", [])

    tabla = Table(
        title="[bold magenta]BOTARDO \u2014 Polymarket Scanner[/bold magenta]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    tabla.add_column("Mercado", style="white", max_width=50)
    tabla.add_column("Yes", justify="right", style="green")
    tabla.add_column("No", justify="right", style="green")
    tabla.add_column("Costo", justify="right", style="yellow")
    tabla.add_column("Edge bruto", justify="right", style="bold green")
    tabla.add_column("Edge neto", justify="right", style="bold cyan")

    if binary:
        for opp in binary[:10]:
            tabla.add_row(
                opp.market.question[:50],
                f"${opp.market.outcome_prices[0]:.3f}",
                f"${opp.market.outcome_prices[1]:.3f}",
                f"${opp.total_cost:.4f}",
                f"{opp.gross_edge_pct:.2f}%",
                f"{opp.net_edge_pct:.2f}%",
            )

    console.print(tabla)

    # Tabla de mercados crypto
    crypto = scan_result.get("crypto_markets", [])
    if crypto:
        tabla2 = Table(
            title="[bold yellow]Mercados Crypto Activos[/bold yellow]",
            box=box.SIMPLE,
        )
        tabla2.add_column("Pregunta", style="white", max_width=60)
        tabla2.add_column("Precio", justify="right", style="green")
        tabla2.add_column("Volumen", justify="right", style="cyan")

        for m in crypto[:10]:
            prices = " / ".join(f"{o}=${p:.2f}" for o, p in zip(m.outcomes, m.outcome_prices))
            tabla2.add_row(
                m.question[:60],
                prices,
                f"${m.volume:,.0f}",
            )
        console.print(tabla2)

    console.print(f"\n[dim]Mercados escaneados: {scan_result['total_markets_scanned']} | "
                  f"Arbitraje encontrado: {len(binary)} | "
                  f"Proximo scan en {poly_config.POLY_SCAN_INTERVAL}s[/dim]\n")


def mostrar_5min_markets(trader: PolymarketTrader, markets_5min: list):
    """Muestra mercados 5-min BTC detectados y sus oportunidades"""
    if not markets_5min:
        console.print("[dim]No se encontraron mercados BTC 5-min Up/Down activos.[/dim]")
        return

    tabla = Table(
        title="[bold red]BTC 5-min Up/Down Markets[/bold red]",
        box=box.DOUBLE_EDGE,
        show_header=True,
        header_style="bold white on red",
    )
    tabla.add_column("Pregunta", style="white", max_width=55)
    tabla.add_column("Up $", justify="right", style="green")
    tabla.add_column("Down $", justify="right", style="red")
    tabla.add_column("Total", justify="right", style="yellow")
    tabla.add_column("Arb Edge", justify="right", style="bold cyan")
    tabla.add_column("Bids/Asks", justify="right", style="dim")

    for mkt in markets_5min:
        analysis = trader.analyze_opportunity(mkt)
        if not analysis:
            continue

        edge_str = f"{analysis['arb_edge']:.2f}%" if analysis['arb_edge'] > 0 else "---"
        edge_style = "bold green" if analysis['arb_edge'] > 1.0 else "dim"

        # Orderbook info
        bids_0 = analysis.get("outcome_0_bids", "?")
        asks_0 = analysis.get("outcome_0_asks", "?")
        ob_str = f"{bids_0}b/{asks_0}a"

        tabla.add_row(
            analysis["question"][:55],
            f"${analysis['prices'][0]:.3f}" if len(analysis['prices']) > 0 else "?",
            f"${analysis['prices'][1]:.3f}" if len(analysis['prices']) > 1 else "?",
            f"${analysis['total_cost']:.4f}",
            f"[{edge_style}]{edge_str}[/{edge_style}]",
            ob_str,
        )

    console.print(tabla)


def init_trading_modules():
    """Inicializa trader y verifica allowances (sin ejecutar trades)"""
    # 1. Connect to CLOB
    trader = PolymarketTrader()
    console.print("[dim]Conectando al CLOB de Polymarket...[/dim]")
    if trader.connect():
        console.print("[green]CLOB conectado OK[/green]")
    else:
        console.print("[yellow]CLOB no disponible - solo modo lectura (Gamma API)[/yellow]")

    # 2. Check allowances (read-only, no transactions)
    console.print("[dim]Verificando allowances en Polygon...[/dim]")
    try:
        am = AllowanceManager()
        ctf_allowance = am.check_usdc_allowance(CTF_EXCHANGE)
        neg_risk_allowance = am.check_usdc_allowance(NEG_RISK_CTF_EXCHANGE)

        ctf_usdc = ctf_allowance / 10**6  # USDC has 6 decimals
        neg_usdc = neg_risk_allowance / 10**6

        if ctf_usdc > 100:
            console.print(f"[green]  CTF Exchange allowance: OK (${ctf_usdc:,.0f})[/green]")
        else:
            console.print(f"[yellow]  CTF Exchange allowance: ${ctf_usdc:.2f} - necesita approval[/yellow]")

        if neg_usdc > 100:
            console.print(f"[green]  NegRisk Exchange allowance: OK (${neg_usdc:,.0f})[/green]")
        else:
            console.print(f"[yellow]  NegRisk Exchange allowance: ${neg_usdc:.2f} - necesita approval[/yellow]")

    except Exception as e:
        console.print(f"[yellow]No se pudo verificar allowances: {e}[/yellow]")

    return trader


def main():
    console.print("[bold magenta]BOTARDO Polymarket Scanner + Trading Module iniciado.[/bold magenta]\n")

    # Init trading modules
    trader = init_trading_modules()
    console.print()

    scanner = PolymarketScanner()

    while True:
        try:
            # 1. Scan general de arbitraje
            result = scanner.scan_all()
            mostrar_resultados(result)

            # 2. Buscar mercados 5-min BTC Up/Down
            try:
                markets_5min = trader.find_5min_btc_markets()
                mostrar_5min_markets(trader, markets_5min)
            except Exception as e:
                console.print(f"[dim red]Error buscando mercados 5-min: {e}[/dim red]")

            # Log oportunidades
            binary = result.get("binary_arbitrage", [])
            if binary:
                for opp in binary:
                    logger.info(
                        f"ARB: {opp.market.question[:50]} | "
                        f"edge_bruto={opp.gross_edge_pct:.2f}% | "
                        f"edge_neto={opp.net_edge_pct:.2f}%"
                    )

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Scanner Polymarket detenido.[/bold yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.error(f"Error en scan: {e}")

        try:
            time.sleep(poly_config.POLY_SCAN_INTERVAL)
        except KeyboardInterrupt:
            console.print("\n[bold yellow]Scanner Polymarket detenido.[/bold yellow]")
            break


if __name__ == "__main__":
    main()
