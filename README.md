# LINE 排班 Bot

數十人群組用的免費 LINE 排班助手。支援新增、查詢、取消班表。

## 功能

| 指令 | 範例 | 說明 |
|------|------|------|
| 新增 | `7/21 9-13` | 沒帶名字 → 排自己（LINE 顯示名稱） |
| 新增 | `7/22 13-19 John` | 有帶名字 → 幫該人排 |
| 新增多行 | 見下方 | 一次貼多行，批次新增 |
| 查詢 | `查詢` | 列出**今日起**的班表 |
| 取消 | `取消 7/21 9-13` | 取消自己在該時段**最新一筆** |
| 取消 | `取消 7/22 13-19 John` | 取消該人最新一筆 |
| 說明 | `說明` | 指令說明 |

### 多行批次新增範例

同一則訊息可貼多行（每行一筆）：

```
7/21 9-12 Morris
7/22 9-21 Kelly
7/23 13-21 Annie
```

回覆會像：

```
✅ 已新增 3 筆

7/21（二） 09:00–12:00  Morris
7/22（三） 09:00–21:00  Kelly
7/23（四） 13:00–21:00  Annie
```

取消也可多行，例如：

```
取消 7/21 9-12 Morris
取消 7/22 9-21 Kelly
```

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
- **資料庫**：優先 `DATABASE_URL` → **PostgreSQL**（建議 Neon 免費）；未設定則 **SQLite**
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
# 本機可用 SQLite：
DATABASE_PATH=./data/shifts.db
# 或改用 Postgres（有設 DATABASE_URL 時會忽略 SQLite）：
# DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
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

## 部署到 Render（新手逐步）

Repo 已在 GitHub：https://github.com/morrislin1114/line-scheduler

### A. 註冊 / 登入 Render

1. 開啟 https://render.com/ → **Get Started**
2. 建議用 **GitHub** 帳號登入（之後才能一鍵連 repo）
3. 授權 Render 讀取你的 GitHub（至少允許 `line-scheduler` 這個 repo）

### B. 建立 Web Service

1. 登入後到 Dashboard → **New +** → **Web Service**
2. 若出現 Connect GitHub：選 **Connect account** / 授權
3. 在 repo 列表找到 **`morrislin1114/line-scheduler`** → **Connect**
4. 填寫設定（名稱可自訂）：

| 欄位 | 請填 |
|------|------|
| **Name** | `line-scheduler`（會變成網址的一部分） |
| **Region** | 選離台灣近的，例如 Singapore（若有）或預設 |
| **Branch** | `main` |
| **Root Directory** | 留空 |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | **Free** |

5. 展開 **Environment Variables** → **Add Environment Variable**，新增：

| Key | Value |
|-----|--------|
| `LINE_CHANNEL_SECRET` | LINE Developers → Channel → Basic settings 的 **Channel secret** |
| `LINE_CHANNEL_ACCESS_TOKEN` | Messaging API 分頁的 **Channel access token**（長字串） |
| `DATABASE_URL` | Neon（或其他）Postgres 連線字串，見下方 **「接上免費 Postgres」** |

> 若暫時不加 `DATABASE_URL`，可設 `DATABASE_PATH=/tmp/shifts.db`（Render 重啟可能掉資料）。

6. 按 **Create Web Service**（或 Deploy Web Service）
7. 等 Logs 出現類似 `Uvicorn running on...` / 狀態變 **Live**（第一次可能 3–10 分鐘）
8. 複製服務網址，例如：

   `https://line-scheduler-xxxx.onrender.com`

9. 瀏覽器開：`https://你的網址/health`  
   應看到類似：`{"status":"ok","db":"postgres","db_ok":"true",...}`

### C. 把 Webhook 接到 LINE

1. [LINE Developers Console](https://developers.line.biz/console/) → 你的 Messaging API channel  
2. **Messaging API** 分頁 → **Webhook URL** 填：

   ```text
   https://你的-render-網址.onrender.com/webhook
   ```

3. 打開 **Use webhook**  
4. 按 **Verify**（成功會顯示成功；若失敗等 Render 醒來再按一次，免費版有冷啟動）  
5. 建議關閉：自動回應訊息、歡迎訊息（在 [OA Manager](https://manager.line.biz/)）  
6. 確認 bot 可加入群組 → 把官方帳號 **加入排班群組**  
7. 在群組試：

   - `說明`
   - `7/21 9-13`
   - `查詢`

### D. 之後改程式怎麼更新？

本機改完後：

```bash
git add -A && git commit -m "your message" && git push
```

Render 若已開 **Auto-Deploy**，推到 `main` 會自動重新部署。

### 接上免費 Postgres（Neon，建議）

Render Free 的磁碟不持久，**正式排班請用外部 DB**。

1. 開啟 https://neon.tech/ → 用 GitHub / Email 註冊  
2. **Create project**（區域可選 Singapore 若有）  
3. 建立完成後，Dashboard → **Connection string** → 選 **URI**  
   形如：

   ```text
   postgresql://user:password@ep-xxxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```

4. 整段複製到 Render → Environment → **`DATABASE_URL`**  
5. **Save** 後手動 **Manual Deploy** 一次  
6. 開 `/health` 確認 `"db":"postgres","db_ok":"true"`

> 程式啟動時會自動 `CREATE TABLE IF NOT EXISTS shifts`，不用手動建表。

### 注意：免費方案

- Render **Free** 一段時間沒人打會**睡著**，第一次回應可能慢 30–60 秒。
- 有 `DATABASE_URL` 時班表存在 Neon，**重啟不會掉**。
- LINE 免費訊息有月額度；本 bot **只用 Reply**，不主動 Push。

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
  storage.py       # Postgres / SQLite
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
