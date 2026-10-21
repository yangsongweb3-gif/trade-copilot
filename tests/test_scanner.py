import pytest

from copilot.config import Scanner
from copilot.market import DailyBars, Ticker
from copilot.scanner import rank_alts, score_alt, universe

BTC = DailyBars('BTCUSDT', [100.0] * 30)                    # BTC 横盘，便于看超额收益


def bars(sym, closes, vols=None):
    return DailyBars(sym, closes, quote_volumes=vols or [1e8] * len(closes))


def tick(sym, price=1.0, pct=0.0, qv=5e7):
    return Ticker(sym, price, pct, qv)


def test_universe_filters_rank_holdings_stables_and_volume():
    ranks = {'BTC': 1, 'XRP': 5, 'SOL': 7, 'USDC': 6, 'SUI': 29, 'LOW': 30, 'PEPE': 52, 'NOTLISTED': 20}
    tickers = {s + 'USDT': tick(s + 'USDT') for s in ['BTC', 'XRP', 'SOL', 'USDC', 'SUI', 'PEPE']}
    tickers['LOWUSDT'] = tick('LOWUSDT', qv=1e6)              # 成交额不够
    assert universe(ranks, tickers, Scanner(hold=['BTC', 'SOL'])) == {'XRPUSDT': 5, 'SUIUSDT': 29}


def test_score_relative_strength_volume_and_no_chase():
    closes = [10.0] * 15 + [10 + i * 0.2 for i in range(1, 16)]   # 最近 15 天稳步上涨
    vols = [1e8] * 23 + [3e8] * 7                                 # 最近 7 天放量
    s = score_alt('SUIUSDT', 29, bars('SUIUSDT', closes, vols), tick('SUIUSDT', 13, 25), BTC, no_chase_pct=20)
    assert s.rs7 == pytest.approx((13 / 11.6 - 1) * 100)          # BTC 没涨，超额就是自己的涨幅
    assert s.strong and s.volume_up and s.above_ma20 and s.no_chase
    assert s.vs_btc[0] == 100 and s.vs_btc[-1] == pytest.approx(130)


def test_skips_new_listings_and_pegged_assets():
    assert score_alt('NEWUSDT', 40, bars('NEWUSDT', [1.0] * 10), tick('NEWUSDT'), BTC, 20) is None
    pegged = [1.0, 1.01] * 15
    assert score_alt('PEGUSDT', 40, bars('PEGUSDT', pegged), tick('PEGUSDT'), BTC, 20) is None


def test_rank_alts_sorts_strongest_first():
    up = [10.0] * 15 + [10 + i * 0.3 for i in range(1, 16)]
    down = [10.0] * 15 + [10 - i * 0.2 for i in range(1, 16)]
    result = rank_alts(BTC, {'AUSDT': bars('AUSDT', down), 'BUSDT': bars('BUSDT', up)},
                       {'AUSDT': tick('AUSDT'), 'BUSDT': tick('BUSDT')}, {'AUSDT': 10, 'BUSDT': 20}, 20)
    assert [s.name for s in result] == ['B', 'A']
    assert result[0].strong and not result[1].strong
