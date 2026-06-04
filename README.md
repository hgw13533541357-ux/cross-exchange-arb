# 跨交易所搬砖套利机器人

监控 Gate.io vs Binance 现货价差，自动套利。

## 原理

当同一个币在两个交易所出现价差时，低价买入、高价卖出，吃差价。

## 运行

1. 在 GitHub Secrets 中添加：
   - `GATE_API_KEY`
   - `GATE_API_SECRET`

2. 自动每15分钟扫描一次
3. 手动: Actions → Run workflow

## 参数

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `MIN_PROFIT` | `0.3` | 最小利润阈值(%) |
| `TRADE_USDT` | `10` | 每笔交易USDT金额 |
| `DRY_RUN` | `true` | 模拟模式 |

## 监控币种

- BTC_USDT
- ETH_USDT
- SOL_USDT