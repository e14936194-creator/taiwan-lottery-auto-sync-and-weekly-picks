# 台灣大樂透 & 威力彩自動蒐集與每週選號系統

純 Python 3 標準函式庫實作（無須 `pip install` 任何第三方套件），可直接串接台灣彩券官方 API，自動回補歷史開獎紀錄、開獎後增量更新，並產出統計分析與每週選號建議。

## 功能特色

1. **完整歷史自動蒐集與增量更新**
   - **大樂透（`lotto649`）**：自動抓取官方 API 自 **2007-01-02** 起之全部開獎紀錄。
   - **威力彩（`super638`）**：自動抓取官方 API 自 **2008-01-24**（首期開獎）起之全部開獎紀錄。
   - 平常執行採增量更新（僅補齊尚未存入 SQLite 的最新期數），並同步匯出 `data/lotto649.csv` 與 `data/super638.csv`。
2. **卡方隨機性檢定（Chi-Square Goodness-of-Fit）**
   - 針對多球無放回抽樣套用有限母體修正係數 $(M-1)/(M-k)$，檢定歷年號碼是否顯著偏離均勻分布。
3. **雙策略選號建議**
   - **理性避撞號策略**：均勻隨機抽出，並過濾掉高度集中的生日號（1–31 ≥ 5 顆）、三連號、純等差數列與極端偏態，在不改變中獎率的前提下降低多人平分頭獎的風險。
   - **統計權重選號**：結合歷史總次數（40%）、近 100 期次數（35%）、遺漏期數（25%）與奇偶平衡抽樣（僅供個人偏好／娛樂參考，實際中獎率與機選相同）。

---

## 快速開始

```bash
# 1. 更新最新開獎資料並產出每週報告（寫入 reports/latest_report.md）
python3 main.py run

# 2. 僅同步資料（加上 --full 可強制全量重抓）
python3 main.py sync

# 3. 僅產出報告（不打網路 API）
python3 main.py report

# 4. 執行單元測試
python3 -m unittest discover -s tests
```

---

## 分享給朋友使用（GitHub Pages 網頁版）

本專案已內建純靜態網頁介面（`docs/index.html` + `docs/data.json`），手機或電腦打開網頁即可查看最新開獎、歷史冷熱門與卡方檢定，並可各自按按鈕抽出不重複的專屬號碼。

1. 若 Repo 目前是 Private，先到 **Settings → General → Danger Zone** 改為 **Public**（GitHub 免費帳號需 Public Repo 才能免費開啟 GitHub Pages）。
2. 到 **Settings → Pages → Build and deployment**：
   - **Source**：選 `Deploy from a branch`
   - **Branch**：選 `main`，資料夾選 `/docs` → 按 **Save**
3. 等待約 1 分鐘後，即可分享你的專屬網站網址給朋友：
   `https://<你的GitHub帳號>.github.io/<你的Repo名稱>/`

---

## 自動化排程設定（二擇一或併用）

### 方式 A：GitHub Actions 雲端免費全自動（推薦）
本專案已內建 `.github/workflows/weekly_lottery.yml`：
1. 將此資料夾推上你的 GitHub Repository（建議設為 Private 或 Public 皆可）。
2. GitHub 會在台灣時間 **每週一、二、四、五 22:00**（開獎後）自動執行 `python3 main.py run --notify`，把更新後的 `data/lottery.db`、CSV 與 `reports/latest_report.md` 自動 commit 回 Repo，並在 Actions Summary 顯示報告。
3. （選用）若想同時自動寄 Email 或傳 Discord / Slack / Google Chat 通知，到 GitHub Repo 的 **Settings → Secrets and variables → Actions** 新增：
   - **Email (SMTP)**：`SMTP_HOST`、`SMTP_PORT`（預設 587）、`SMTP_USER`、`SMTP_PASS`、`SMTP_TO`
   - **Webhook**：`LOTTERY_WEBHOOK_URL`

### 方式 B：本地 Linux / macOS `crontab` 排程
在終端機執行 `crontab -e`，加入以下設定（台灣時間每週一、二、四、五 22:00 執行）：

```cron
0 22 * * 1,2,4,5 cd /usr/local/google/home/rexchu/Projects/tw-lottery-analyzer && /usr/bin/python3 main.py run >> /tmp/tw_lottery.log 2>&1
```
