# ============================================================
# alerts/notifier.py — Alertas de oportunidades de arbitraje
# ============================================================

import requests
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

import config
from core.models import Opportunity

console = Console()


def alert_console(opp: Opportunity) -> None:
    """
    Muestra una alerta visual en la consola usando rich.
    """
    texto = Text()
    texto.append("OPORTUNIDAD DETECTADA\n\n", style="bold yellow")
    texto.append(f"  Comprar en:   ", style="white")
    texto.append(f"{opp.buy_exchange:<14}", style="bold cyan")
    texto.append(f"@ ${opp.buy_price:>10,.2f}\n", style="green")
    texto.append(f"  Vender en:    ", style="white")
    texto.append(f"{opp.sell_exchange:<14}", style="bold cyan")
    texto.append(f"@ ${opp.sell_price:>10,.2f}\n", style="green")
    texto.append(f"\n  Spread bruto: ", style="white")
    texto.append(f"{opp.gross_spread_pct:.2f}%\n", style="yellow")
    texto.append(f"  Spread neto:  ", style="white")
    texto.append(f"{opp.net_spread_pct:.2f}%\n", style="bold green")
    texto.append(f"\n  Ganancia est: ", style="white")
    texto.append(
        f"${opp.estimated_profit_ars:,.0f} ARS  ",
        style="bold green",
    )
    texto.append(f"(con {config.CAPITAL_USDT} USDT)", style="dim")

    panel = Panel(
        texto,
        title="[bold red] BOTARDO ALERTA [/bold red]",
        border_style="bright_red",
        expand=False,
    )
    console.print(panel)


def alert_telegram(opp: Opportunity) -> None:
    """
    Envía alerta a Telegram si TOKEN y CHAT_ID están configurados.
    No interrumpe si falla.
    """
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        return

    mensaje = (
        f"🔥 *OPORTUNIDAD BOTARDO*\n\n"
        f"Comprar en: *{opp.buy_exchange}* @ ${opp.buy_price:,.2f}\n"
        f"Vender en:  *{opp.sell_exchange}* @ ${opp.sell_price:,.2f}\n\n"
        f"Spread neto: *{opp.net_spread_pct:.2f}%*\n"
        f"Ganancia est: *${opp.estimated_profit_ars:,.0f} ARS*"
    )

    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
        requests.post(
            url,
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": mensaje,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
    except Exception as e:
        console.print(f"[dim red]Telegram error: {e}[/dim red]")


def notify(opp: Opportunity) -> None:
    """
    Punto de entrada principal: dispara todos los canales de alerta.
    """
    alert_console(opp)
    alert_telegram(opp)
