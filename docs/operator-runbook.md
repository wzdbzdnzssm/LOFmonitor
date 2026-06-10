# 运维手册 — LOFmonitor

## 1. 部署

```bash
git clone <repo-url> /opt/lofmonitor
cd /opt/lofmonitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# 编辑 config.yaml 配置推送 token
```

## 2. 验证

```bash
cd /opt/lofmonitor && source .venv/bin/activate
python main.py run --force
```

检查终端输出。无套利机会时静默退出（exit 0，无 output 文件）。

## 3. 定时（cron）

```bash
# crontab -e
30 14 * * 1-5 cd /opt/lofmonitor && /opt/lofmonitor/.venv/bin/python main.py run >> /var/log/lofmonitor.log 2>&1
```

| 项 | 值 |
|----|-----|
| 工作目录 | `/opt/lofmonitor` |
| 命令 | `/opt/lofmonitor/.venv/bin/python main.py run` |
| 时区 | `Asia/Shanghai`（由程序内部 exchange-calendars 判断交易日） |
| 计划 | 工作日 14:30 |

非交易日程序内部自动跳过；无套利机会时静默不输出。

## 4. 运行产物

| 路径 | 说明 |
|------|------|
| `output/lof_premium_*.txt` | 推送正文副本（**仅当有套利机会时生成**） |
| `output/lof_premium_*.csv` | 套利标的表格 |
| `data/*.json` | 缓存，可删会自动重建 |
| `/var/log/lofmonitor.log` | cron 运行日志（可选） |

## 5. 推送配置示例

### PushPlus（微信）

```yaml
push:
  enabled: true
  channel: pushplus
  pushplus:
    token: "your-pushplus-token"
```

### ServerChan（方糖）

```yaml
push:
  enabled: true
  channel: serverchan
  serverchan:
    sendkey: "your-sendkey"
```

### Webhook

```yaml
push:
  enabled: true
  channel: webhook
  webhook:
    url: "https://your-webhook-url"
```

## 6. 故障排查

### 程序运行但无输出

正常现象。表示当前没有 |溢价率| > 10% 且可申购的 LOF 标的。

### 东方财富 API 连接失败

部分服务器 IP 可能被东方财富封禁。可尝试：
- 更换服务器/IP
- 配置代理（修改 `http_client.py` 中的 `session.proxies`）

### 日志查看

```bash
tail -f /var/log/lofmonitor.log
# 或查看程序输出
cd /opt/lofmonitor && source .venv/bin/activate
python main.py run --force
```
