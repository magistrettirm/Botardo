import sys
sys.stdout.reconfigure(encoding='utf-8')
from polymarket.trader import PolymarketTrader

t = PolymarketTrader()
t.connect()

print('Buscando mercados BTC 5-min...')
markets = t.find_5min_btc_markets()
print(f'Encontrados: {len(markets)}')

for m in markets[:3]:
    q = m.get("question", "?")
    print(f'\n--- {q} ---')
    analysis = t.analyze_opportunity(m)
    if analysis:
        p0 = analysis["prices"][0]
        p1 = analysis["prices"][1]
        tc = analysis["total_cost"]
        ae = analysis["arb_edge"]
        print(f'  Up: ${p0:.3f} | Down: ${p1:.3f}')
        print(f'  Total: ${tc:.4f} | Arb edge: {ae:.2f}%')
        for i in range(2):
            bb = analysis.get(f'outcome_{i}_best_bid', 0)
            ba = analysis.get(f'outcome_{i}_best_ask', 0)
            name = analysis["outcomes"][i] if i < len(analysis["outcomes"]) else f"outcome_{i}"
            print(f'  {name}: best_bid=${bb:.3f} best_ask=${ba:.3f}')
