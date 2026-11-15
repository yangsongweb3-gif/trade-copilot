import pytest

from copilot.revenue import by_gecko, gecko_index, price_to_sales

PROTOCOLS = [
    {'id': '2198', 'name': 'Uniswap V3', 'gecko_id': None, 'parentProtocol': 'parent#uniswap'},
    {'id': '5507', 'name': 'Hyperliquid Perps', 'gecko_id': None, 'parentProtocol': 'parent#hyperliquid'},
    {'id': '3905', 'name': 'Chainlink Staking', 'gecko_id': 'chainlink', 'parentProtocol': None},
    {'id': '9999', 'name': '没有币的协议', 'gecko_id': None, 'parentProtocol': None},
]
PARENTS = [{'id': 'parent#uniswap', 'gecko_id': 'uniswap'}, {'id': 'parent#hyperliquid', 'gecko_id': 'hyperliquid'}]
CHAINS = [{'name': 'Solana', 'gecko_id': 'solana'}, {'name': 'Moonbeam', 'gecko_id': None}]


def test_gecko_index_uses_own_id_then_parent_then_chain():
    idx = gecko_index(PROTOCOLS, PARENTS, CHAINS)
    assert idx == {'2198': 'uniswap', '5507': 'hyperliquid', '3905': 'chainlink', 'chain#solana': 'solana'}


def test_by_gecko_sums_child_protocols():
    rows = [{'defillamaId': '2198', 'total30d': 8e6}, {'defillamaId': '5507', 'total30d': 60e6},
            {'defillamaId': '5507', 'total30d': 6.6e6}, {'defillamaId': 'chain#solana', 'total30d': 3.4e6},
            {'defillamaId': '9999', 'total30d': 1e6}, {'defillamaId': '3905', 'total30d': None}]
    totals = by_gecko(rows, gecko_index(PROTOCOLS, PARENTS, CHAINS))
    assert totals == {'uniswap': 8e6, 'hyperliquid': pytest.approx(66.6e6), 'solana': 3.4e6, 'chainlink': 0}


def test_price_to_sales():
    assert price_to_sales(12e9, 66.6e6) == pytest.approx(12e9 / (66.6e6 * 365 / 30))
    assert price_to_sales(1e9, 5_000) is None          # 收入太少当作没有
    assert price_to_sales(None, 1e6) is None
