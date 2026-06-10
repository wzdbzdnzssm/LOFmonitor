# LOFmonitor

A 股场内 LOF / QDII-LOF 套利机会监控：交易日抓取并推送 **|溢价率| > 10% 且可申购** 的标的。

## 安装

```bash
git clone <repo-url> /opt/lofmonitor
cd /opt/lofmonitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# 编辑 config.yaml 配置推送渠道
```

## 使用

```bash
# 生产运行（非交易日自动跳过，无机会时静默）
python main.py run

# 强制测试（无视交易日）
python main.py run --force
```

## 筛选逻辑

- `|溢价率| > 10%`（溢价或折价都抓）
- `申购状态 ≠ 暂停申购`（必须能申购才能套利）
- 按 |溢价率| 降序排列

无符合条件的标的时**静默退出**，不产生任何输出文件或推送。

## 推送渠道

编辑 `config.yaml`：

```yaml
push:
  enabled: true
  channel: pushplus    # console | pushplus | serverchan | webhook
  pushplus:
    token: "YOUR_TOKEN"
```

| 渠道 | 说明 |
|------|------|
| `console` | 仅 stdout 输出（默认） |
| `pushplus` | [PushPlus](https://www.pushplus.plus) 微信推送 |
| `serverchan` | [ServerChan](https://sct.ftqq.com) 微信推送 |
| `webhook` | 自定义 HTTP POST |

## 定时运行（cron）

```bash
# crontab -e
30 14 * * 1-5 cd /opt/lofmonitor && /opt/lofmonitor/.venv/bin/python main.py run >> /var/log/lofmonitor.log 2>&1
```

| 项 | 值 |
|----|-----|
| 运行时间 | 工作日 14:30 |
| 非交易日 | 程序内部自动跳过 |
| 无套利机会 | **静默退出**，不推送 |

## 数据源

- 主数据源：[东方财富](https://fund.eastmoney.com)（净值、行情、申购状态）
- 备用：[集思录](https://www.jisilu.cn)（净值、溢价）、[新浪财经](https://finance.sina.com.cn)（行情）

## 文件说明

| 路径 | 说明 |
|------|------|
| `output/lof_premium_*.txt` | 推送正文副本（**仅当有套利机会时生成**） |
| `output/lof_premium_*.csv` | 套利标的表格 |
| `data/*.json` | 缓存，可删会自动重建 |
| `config.yaml` | 用户配置（gitignore，需手动创建） |

## License

MIT
