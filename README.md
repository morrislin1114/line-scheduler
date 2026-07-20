# LINE 排班 Bot

數十人群組用的免費 LINE 排班助手。支援新增、查詢、取消班表。

**正式環境資料庫建議：** [使用 Neon 免費 Postgres](#使用-neon-免費資料庫建議正式環境)（設定 `DATABASE_URL`）。

## 功能

| 指令 | 範例 | 說明 |
|------|------|------|
| 新增 | `7/21 9-13` | 沒帶名字 → 排自己（LINE 顯示名稱） |
| 新增 | `7/22 13-19 John` | 有帶名字 → 幫該人排 |
| 新增多行 | 見下方 | 一次貼多行，批次新增 |
| 查詢 | `查詢` | 列出**今日起**全部班表 |
| 查詢 N 天 | `查詢 7` | 列出**今日算起 7 天內**（含今天） |
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
| `DATABASE_URL` | **先做下方「使用 Neon 免費資料庫」**，再把連線字串貼這裡 |

> 正式排班**強烈建議**設 `DATABASE_URL`（Neon）。  
> 若暫時不加，可設 `DATABASE_PATH=/tmp/shifts.db`，但 Render 重啟／sleep **可能整包掉班表**。

6. 按 **Create Web Service**（或 Deploy Web Service）
7. 等 Logs 出現類似 `Uvicorn running on...` / 狀態變 **Live**（第一次可能 3–10 分鐘）
8. 複製服務網址，例如：

   `https://line-scheduler-xxxx.onrender.com`

9. 瀏覽器開：`https://你的網址/health`  
   - 有接 Neon：`{"status":"ok","db":"postgres","db_ok":"true",...}`  
   - 只有 SQLite：`"db":"sqlite"`（不建議當正式環境）

### C. 把 Webhook 接到 LINE

1. [LINE Developers Console](https://developers.line.biz/console/) → 你的 Messaging API channel  
2. **Messaging API** 分頁 → **Webhook URL** 填：

   ```text
   https://你的-render-網址.onrender.com/webhook
   ```

3. 打開 **Use webhook**  
4. 按 **Verify**（成功會顯示成功；若失敗等 Render 醒來再按一次，免費版有冷啟動）  
5. 建議關閉：自動回應訊息、歡迎訊息（在 [OA Manager](https://manager.line.biz/)）  
6. 確認 bot 可加入群組（**Allow bot to join group chats**）→ 把官方帳號 **加入排班群組**  
7. 在群組試：

   - `說明`
   - `7/21 9-13`
   - `查詢` / `查詢 7`

### D. 之後改程式怎麼更新？

本機改完後：

```bash
git add -A && git commit -m "your message" && git push
```

Render 若已開 **Auto-Deploy**，推到 `main` 會自動重新部署。

---

## 使用 Neon 免費資料庫（建議正式環境）

Render Free 的 Web 磁碟**不持久**（sleep／重啟常清檔）。班表應存在 **外部 Postgres**。  
本專案建議使用 [Neon](https://neon.tech/) 免費方案：長期可用、不需信用卡也能開始（以官網當下方案為準）。

### 為什麼用 Neon？

| 方案 | 說明 |
|------|------|
| **Neon Free（建議）** | 資料在雲端 Postgres；Render 重啟**不會**清班表 |
| Render 本機 SQLite | 設定簡單，但 Free 上**易掉資料** |
| Render Free Postgres | 也可用，但整顆 DB 約 **建立後 30 天到期**（不是只刪舊資料） |

程式只要讀環境變數 **`DATABASE_URL`**，**不用改 code、不用手動建表**（啟動時會自動建立 `shifts`）。

### 步驟 1：註冊 Neon 並建立專案

1. 開啟 https://console.neon.tech/ （或 https://neon.tech/ → Sign up）
2. 建議用 **GitHub** 登入（較快）
3. 若提示建立組織／專案，依畫面操作
4. **Create a project**（或 New Project）：
   - **Project name**：例如 `line-scheduler`
   - **Postgres version**：預設即可
   - **Region**：選離你近的（若有 **Singapore / Asia** 可優先；沒有就用預設）
5. 按建立，等專案就緒

### 步驟 2：複製連線字串（Connection string）

1. 進入剛建好的 Project Dashboard  
2. 找到 **Connection string** / **Connect** 區塊  
3. 連線方式選：
   - **Connection string**
   - 驅動選 **PostgreSQL** / 一般 URI 即可（不要選 Prisma 專用格式也沒關係，重點是下面這種 URL）
4. 建議勾選／確認有 **`sslmode=require`**（Neon 通常預設會帶）  
5. 複製整段 URI，格式類似：

   ```text
   postgresql://neondb_owner:你的密碼@ep-cool-name-a1b2c3d4.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
   ```

6. **密碼只顯示一次或藏在字串裡**：請整段複製，不要只複製一半  
7. 這串字**等同密碼**，不要貼到公開 GitHub Issue／群組

> 若介面有 **Pooled connection** 與 **Direct**：  
> - 給 Render 這種少數連線的 Web Service，**兩種通常都能用**  
> - 先用畫面上預設的 **URI** 即可；若連線失敗再換另一種試  

### 步驟 3：填進 Render 環境變數

1. 開啟 [Render Dashboard](https://dashboard.render.com/)  
2. 點你的 **Web Service**（`line-scheduler`）  
3. 上方選 **Environment**  
4. **Add Environment Variable**：

   | Key | Value |
   |-----|--------|
   | `DATABASE_URL` | 步驟 2 複製的**整段** `postgresql://...` |

5. 若以前有設 `DATABASE_PATH=/tmp/shifts.db`：
   - **可留著**（有 `DATABASE_URL` 時程式會**優先用 Neon，忽略 SQLite**）  
   - 或刪掉也可以  
6. 按 **Save Changes**

### 步驟 4：重新部署並確認

1. 到 **Manual Deploy** → **Deploy latest commit**（或 Save 後若有提示重新部署就照做）  
2. 等狀態變 **Live**  
3. 瀏覽器開啟：

   ```text
   https://你的-render-網址.onrender.com/health
   ```

4. **成功**應類似：

   ```json
   {
     "status": "ok",
     "db": "postgres",
     "db_ok": "true",
     "has_secret": "true",
     "has_token": "true"
   }
   ```

| `/health` 結果 | 意思 |
|----------------|------|
| `"db":"postgres","db_ok":"true"` | Neon 已接上，可正式用 |
| `"db":"sqlite"` | 沒讀到 `DATABASE_URL`（檢查 Key 名稱是否完全是 `DATABASE_URL`、是否已 Save + Redeploy） |
| `"db_ok":"false"` / `status":"degraded"` | 連線失敗（密碼錯、字串被截斷、缺 `sslmode=require`、Neon 專案暫停） |
| 網站打不開 | Render 在 sleep：多等 30–60 秒再重整 |

5. 在 LINE 群組測試：

   ```text
   7/21 9-12 Morris
   7/22 9-21 Kelly
   ```

   再送 `查詢`。  
6. （可選）到 Neon Console → **Tables** / SQL Editor，應能看到 `shifts` 表與資料。

### 步驟 5：本機也想連同一顆 Neon 時（可選）

編輯專案根目錄 `.env`（**不要 commit 到 Git**）：

```bash
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...
DATABASE_URL=postgresql://neondb_owner:你的密碼@ep-xxxx.neon.tech/neondb?sslmode=require
```

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

開 `http://localhost:8000/health`，同樣應看到 `"db":"postgres"`。  
注意：本機與 Render 共用同一顆 DB 時，**班表資料是同一份**。

### 常見問題

| 問題 | 處理 |
|------|------|
| Render 已設 `DATABASE_URL` 但 health 仍是 `sqlite` | Key 必須完全是 `DATABASE_URL`；改完要 **Save + Redeploy**；Logs 裡應有 `ShiftStore backend=postgres` |
| `db_ok` 為 false | 重新從 Neon 複製 URI；確認密碼特殊字元完整；URL 需含 `sslmode=require` |
| 會不會要手動建表？ | **不用**。App 啟動會 `CREATE TABLE IF NOT EXISTS shifts` |
| Neon 免費會不會 30 天刪整庫？ | **不會像 Render Free Postgres 那樣 30 天到期砍庫**（仍受 Neon 免費方案用量限制，以官網為準） |
| 連線字串洩漏了怎麼辦？ | 到 Neon 重設角色密碼 / 換連線密，並更新 Render 的 `DATABASE_URL` |
| 舊的 SQLite 資料會自動搬到 Neon 嗎？ | **不會**。接上 Neon 後是新庫；需在群組重新輸入排班，或自行匯出匯入 |

### 注意：免費方案其他限制

- Render **Free** Web 一段時間沒流量會**睡著**，第一次回應可能慢 30–60 秒（DB 在 Neon 上，醒來後資料仍在）。
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
