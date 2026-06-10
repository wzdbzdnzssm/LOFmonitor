# AGENTS.md — LOFmonitor

> 给其他 Agent（Hermes、Codex、Cursor 等）用的项目速查。

## 项目是什么

Python CLI：抓取 A 股场内 LOF 溢价/折价，筛选 **|溢价率| > 10% 且可申购** 的套利标的，在交易日输出/推送。无 Web 服务、无数据库。

## 目录结构

```
main.py
config.example.yaml
config.yaml             # gitignore，用户自己配
lofmonitor/
  calculator.py         # 溢价计算、套利筛选、format_top_message()
  scheduler.py          # run_once，无标的时静默退出
  notifier.py           # pushplus | serverchan | webhook | console
  data_sources/         # eastmoney / purchase / sina / jisilu
data/ output/           # 运行时，gitignore
```

## 命令

```bash
python main.py run              # 生产：非交易日跳过，无标的静默
python main.py run --force      # 测试
```

## 筛选逻辑

- `|premium_pct| > 10`（溢价或折价都抓）
- `purchase_label != "暂停申购"`（必须可申购）
- 按 `abs(premium_pct)` 降序

无符合条件的记录时：**不生成 output 文件、不推送、exit 0**

## 配置

`config.yaml`：`push.channel` = `console`（默认）| `pushplus` | `serverchan` | `webhook`

申购展示：`不限购` / `限购xx元` / `暂停申购`

## 定时（cron）

```bash
30 14 * * 1-5 cd /opt/lofmonitor && /opt/lofmonitor/.venv/bin/python main.py run
```

非交易日程序内部会跳过；无套利机会时静默不输出。
