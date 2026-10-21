"""主循环：拉行情 → 判断规则 → 去重 → 发通知。

用法：
  python -m copilot.main --once --dry-run   跑一轮，只打印不发送（第一次先这样看效果）
  python -m copilot.main                    每 60 秒检查一次，发 QQ 私聊
  python -m copilot.main --regime --dry-run 看今日环境灯（去掉 --dry-run 会发 QQ 私聊）
"""
import argparse
import logging
import time

from .config import ROOT, load_env, load_plans
from .macro import DXY, NASDAQ, US10Y, Macro
from .market import Market
from .notify import Notifier
from .premium import premium_series
from .regime import MacroData, evaluate_regime, format_regime
from .rules import evaluate, symbols_needed
from .state import AlertState

log = logging.getLogger('copilot')


def run_once(plans, market: Market, state: AlertState, notifier: Notifier) -> int:
    tick_syms, day_syms = symbols_needed(plans.plans)
    tickers = {s: market.ticker(s) for s in sorted(tick_syms)}
    daily = {s: market.daily(s) for s in sorted(day_syms)}
    signals = [s for p in plans.plans for s in evaluate(p, plans.settings, tickers, daily)]
    # 同一个 key 只保留一条（例如两个 AAVE 计划都会报"AAVE 不追"）
    by_key = {s.key: s for s in signals}
    new_keys = state.update(set(by_key))
    for key in sorted(new_keys):
        notifier.send(by_key[key])
    log.info('检查完成：%d 个币，成立 %d 条，新提醒 %d 条', len(tickers), len(by_key), len(new_keys))
    return len(new_keys)


def _try(name: str, fn, *args):
    """宏观数据缺一两项不影响出结果：失败记日志，该项按缺失处理。"""
    try:
        return fn(*args)
    except Exception as e:
        log.warning('%s 获取失败：%s', name, e)
        return None


def collect_macro(market: Market, macro: Macro) -> MacroData:
    series = {
        'nasdaq': _try('纳斯达克', macro.yahoo_series, NASDAQ),
        'dxy': _try('美元指数', macro.yahoo_series, DXY),
        'us10y': _try('美债收益率', macro.yahoo_series, US10Y),
        'stables': _try('稳定币总量', macro.stablecoin_supply),
    }
    funding = _try('资金费率', market.funding_rates, 'BTCUSDT')
    oi = _try('持仓量', market.open_interest, 'BTCUSDT')
    ls = _try('多空比', market.long_short_ratio, 'BTCUSDT')
    series['funding'] = funding
    series['oi'] = [(d, coins) for d, coins, _ in oi] if oi else None
    series['oi_usd'] = [(d, usd) for d, _, usd in oi] if oi else None
    series['ls_ratio'] = [(d, r) for d, r, _ in ls] if ls else None
    series['ls_long'] = [(d, long) for d, _, long in ls] if ls else None
    series['fng'] = _try('恐惧贪婪指数', macro.fear_greed)
    coinbase, binance = _try('Coinbase 小时线', macro.coinbase_hourly), _try('币安小时线', market.hourly, 'BTCUSDT')
    series['premium'] = premium_series(coinbase, binance) if coinbase and binance else None
    etf_rows = _try('BTC 现货 ETF 资金流', macro.etf_flows)
    series['etf'] = [(d, total) for d, total, _ in etf_rows] if etf_rows else None
    values = {k: [v for _, v in s] if s else None for k, s in series.items()}
    return MacroData(
        btc=market.daily('BTCUSDT', days=210),  # BTC 是核心，拿不到就直接报错；多拉一些给网页画均线、算 MA200
        funding=values['funding'], oi=values['oi'],
        nasdaq=values['nasdaq'], dxy=values['dxy'], us10y=values['us10y'], stables=values['stables'],
        fear_greed=series['fng'][-1][1] if series['fng'] else None,
        etf=series['etf'],
        series={k: s for k, s in series.items() if s},
        etf_funds=etf_rows[-1][2] if etf_rows else {},
    )


def regime_report(market: Market, macro: Macro) -> str:
    return format_regime(evaluate_regime(collect_macro(market, macro)))


def main():
    ap = argparse.ArgumentParser(description='trade-copilot：只提醒、不下单')
    ap.add_argument('--once', action='store_true', help='只跑一轮')
    ap.add_argument('--dry-run', action='store_true', help='只打印，不发 QQ / PushPlus')
    ap.add_argument('--interval', type=int, default=60, help='检查间隔（秒）')
    ap.add_argument('--regime', action='store_true', help='生成今日环境灯后退出')
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')

    env = load_env()
    plans = load_plans()
    market = Market(proxy=env.get('HTTPS_PROXY', ''))
    # dry-run 用单独的状态文件，测试不会影响正式运行的"已提醒"记录
    state = AlertState(ROOT / 'data' / ('state-dry.json' if args.dry_run else 'state.json'))
    notifier = Notifier(env, dry_run=args.dry_run)
    if args.regime:
        notifier.send_report(regime_report(market, Macro(proxy=env.get('HTTPS_PROXY', ''))))
        return
    log.info('加载 %d 个计划%s', len(plans.plans), '（dry-run，只打印）' if args.dry_run else '')

    while True:
        try:
            run_once(plans, market, state, notifier)
        except Exception as e:  # 网络抖动等问题：记录下来，下一轮继续
            log.warning('本轮检查失败：%s', e)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
