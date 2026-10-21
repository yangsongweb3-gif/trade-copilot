# trade-copilot

币安现货的交易副驾驶：只整理信息、按自己写的规则提醒，**不下单**，API Key 只开读取权限。

- **今日环境灯**：BTC 趋势、波动、杠杆、恐惧贪婪、ETF 资金流、纳指、美元美债、稳定币汇总成红黄绿灯
- **BTC 每日面板**：今日变化、关键价位、BTC 日线、宏观详情、Coinbase 溢价、行业快讯、未来 7 天日程
- **强势山寨扫描**：市值区间里近 7、14 天都跑赢 BTC 的币（本地网页，不公开发布）
- **到价提醒**：`config/plans.yaml` 里的交易计划，到买入区、止损、目标时发 QQ 私聊

每天生成的日报网页在 [`site/`](site/)，由 GitHub Actions 发布到 GitHub Pages。

## 本地运行

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env                       # 填代理、NapCat 等
copy config\plans.example.yaml config\plans.yaml

.venv\Scripts\python -m copilot.web --open   # 本地网页，或双击 start-web.bat
.venv\Scripts\python -m copilot.main         # 到价提醒，每 60 秒检查一次
.venv\Scripts\python -m copilot.report       # 生成日报长图，配置了 SITE_REPO 时发布网页版
.venv\Scripts\python -m pytest
```

设计说明见 [docs/系统设计.md](docs/系统设计.md)。

只整理信息，不构成投资建议。
