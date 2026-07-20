# LINE 排班 Bot

數十人群組用的免費 LINE 排班助手。支援新增、查詢、取消班表。

## 功能

| 指令 | 範例 | 說明 |
|------|------|------|
| 新增 | `7/21 9-13` | 沒帶名字 → 排自己（LINE 顯示名稱） |
| 新增 | `7/22 13-19 John` | 有帶名字 → 幫該人排 |
| 查詢 | `查詢` | 列出**今日起**的班表 |
| 取消 | `取消 7/21 9-13` | 取消自己在該時段**最新一筆** |
| 取消 | `取消 7/22 13-19 John` | 取消該人最新一筆 |
| 說明 | `說明` | 指令說明 |

- 時間為 24 小時制整點，例如 `9-13`、`13-19`
- **可重複排班**（同人同時段可多筆，不擋衝突）
- 非指令訊息不會回覆，避免洗版
- 時區：`Asia/Taipei`

### 查詢回覆範例

```
📅 排班一覽（今日起）

7/21（二）
  09:00–13:00  Morris
  13:00–19:00  John

共 2 筆
```

## 技術

- Python 3.11+ / FastAPI
- SQLite
- LINE Messaging API（Webhook + Reply）

## 快速開始（本機）

### 1. 安裝

```bash
cd line-scheduler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

編輯 `.env`：

```bash
LINE_CHANNEL_SECRET=你的_Channel_Secret
LINE_CHANNEL_ACCESS_TOKEN=你的_Channel_Access_Token
DATABASE_PATH=./data/shifts.db
```

### 2. 建立 LINE Messaging API Channel

1. 開啟 [LINE Developers Console](https://developers.line.biz/console/)
2. 建立 Provider → 建立 **Messaging API** channel
3. 在 channel 基本設定取得 **Channel secret**
4. 在 **Messaging API** 分頁發行 **Channel access token**
5. 到 [LINE Official Account Manager](https://manager.line.biz/)：
   - 回應設定：關閉「自動回應訊息」「歡迎訊息」較不易打架
   - 啟用 **Webhook**
   - 允許 bot 加入群組（群組／多人聊天相關權限）

### 3. 啟動服務

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

健康檢查：`http://localhost:8000/health`

### 4. 用 ngrok 暴露 webhook

```bash
ngrok http 8000
```

在 LINE Developers Console → Messaging API → Webhook URL：

```
https://<你的-ngrok-網域>/webhook
```

按 Verify。成功後把 bot 加進排班群組即可使用。

> 本機除錯若暫時跳過簽章驗證，可設 `SKIP_SIGNATURE_VERIFY=true`（**正式環境請關閉**）。

## 部署到 Render（免費）

1. 將專案推上 GitHub
2. [Render](https://render.com/) → New → Web Service → 連 repo
3. 設定：
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Environment：
   - `LINE_CHANNEL_SECRET`
   - `LINE_CHANNEL_ACCESS_TOKEN`
   - `DATABASE_PATH` = `/tmp/shifts.db`（或 `./data/shifts.db`）
5. 部署完成後，Webhook URL 設為：

   `https://<你的-render-服務>.onrender.com/webhook`

### 注意：SQLite 與免費方案

Render 免費實例重啟後**磁碟可能清空**，班表有遺失風險。若需要持久化，可改掛外部免費 Postgres（如 Neon）或改用有 volume 的方案（Railway 等）。數十人、可接受偶爾重建班表時，SQLite 通常夠用。

LINE 免費訊息有月額度；本 bot **只用 Reply**（回應用戶訊息），不主動 Push。

## 開發與測試

```bash
source .venv/bin/activate
pytest -q
```

## 專案結構

```
app/
  main.py          # /webhook, /health
  config.py
  parser.py        # 指令解析
  service.py       # 業務邏輯
  storage.py       # SQLite
  formatter.py     # 回覆格式
  line_client.py   # 簽章、reply、顯示名稱
  models.py
tests/
```

## 行為細節

- 日期 `M/D`：預設當年；若早於今天（台北）則視為明年
- 取消自己：優先依 LINE `userId` 找自己建立的班，找不到再比顯示名稱
- 取消有名字：`person_name` 不分大小寫完全比對
- 每次取消只刪**最新一筆**；若有重複需取消多次
- 多群組資料以 `groupId` 隔離；1:1 聊天也可測（獨立空間）
