# 台灣租房監控機器人

每次執行抓取 591 租屋資訊 → 去重過濾 → 歷史比對 → 輸出靜態 HTML 報表 → 自動發布到 GitHub Pages。

## 執行方式

```powershell
py main.py                    # 全平台正式執行
py main.py --platforms 591    # 只跑 591
py main.py --dry-run          # 不打網路，測試 diff + report 流程
```

> **重要**：Windows 上必須用 `py`，不是 `python`（python 指向 MS Store 空殼）

跑完後若 config 有 `github_publish`，自動 PUT `index.html` 到 gh-pages branch（GitHub Contents API，不需要 git CLI）。失敗只 log warning，不中斷流程。

---

## 591 爬蟲技術重點

### API 端點
```
GET https://bff-house.591.com.tw/v3/web/rent/list
```

### 必要 Request Headers
```
device:   pc
Referer:  https://rent.591.com.tw/
```

### 關鍵 Query Params
| 參數 | 說明 | 範例 |
|------|------|------|
| `regionid` | 城市 ID | 新北市=3, 台北市=1 |
| `section` | 行政區 ID（實測值） | 板橋=26, 中和=38, 永和=37, 新店=34, 土城=39, 三重=43, 蘆洲=47 |
| `kind` | 房型代碼 | 整層住家=1, 獨立套房=2, 分租套房=3, 雅房=4 |
| `timestamp` | 毫秒時間戳 | `int(time.time() * 1000)` |
| `firstRow` | 分頁起始列 | 0, 30, 60, ... |
| `price` | 價格區間 | `"15000_28000"` |
| `floor` | 最低樓層 | `"2_"` |

### 注意事項
- 舊版端點 `rent.591.com.tw/home/search/rsList` 已廢棄（回 419）
- `deviceid` 可省略，WARNING 可忽略
- 最後一頁之後 `status=0`，items 為空，用 `if not items` 判斷停止
- 591 是 Vue.js SPA，pure httpx/requests 會被 Cloudflare 擋，**必須用 Playwright**
- **GitHub Actions / 外部 IP 會被 Cloudflare 擋（403）**，爬蟲只能在本機執行
- `price` 欄位是字串如 `"25,000"`，需 replace 逗號後轉 int
- `tags` 陣列含 `"有電梯"` 字串時，`has_elevator = True`
- 策略：Playwright headless Chromium 載入首頁建立 session → `context.request.get()` 打 API → 每頁 30 筆，間隔 1.2 秒
- 每個 section 各自開一個 Playwright browser，跑完關閉
- `listed_date`：從 `post_time`（Unix timestamp 秒）解析，fallback `posttime` / `insert_time`；確認有效，無需額外處理
- 執行後若有新欄位出現可看 log `591 raw item keys: [...]` 確認

---

## config.json 結構

巢狀城市格式（支援多城市）：

```json
{
  "cities": [
    { "name": "新北市", "regions": ["新店區", "中和區", "永和區", "板橋區"] },
    { "name": "台北市", "regions": ["信義區", "中山區", "大安區"] }
  ],
  "price_min": 15000,
  "price_max": 28000,
  "room_types": ["整層住家"],
  "pet_friendly": false,
  "floor_min": 2,
  "area_min": 15,
  "exclude_rooftop_addition": true,
  "exclude_top_floor": true,
  "github_publish": {
    "repo":  "username/rent-report",
    "token": "ghp_xxxx"
  }
}
```

- `regions` 名稱需帶「區」，與 591 address 格式一致（`板橋區-文化路`）
- `regions` 設為空陣列則不限行政區
- `github_publish`：選填；`repo` = `owner/repo`，`token` = fine-grained PAT（Contents R+W）

---

## 過濾規則

- `exclude_rooftop_addition`：title/floor/address 含「頂加」等關鍵字 → 排除
- `exclude_top_floor`：current_floor == total_floors → 排除
- **社宅過濾**：title 含「社宅」或「社會住宅」→ 排除（寫死，不可設定）
- **去重**：address + price + area + floor 完全相同 → 只保留第一筆（不比對 title）

---

## 資料流

```
爬蟲抓取
  └─ dedup_properties()     # address + price + area + floor 完全比對去重
  └─ apply_filters()        # floor_min, area_min, exclude_rooftop, exclude_top_floor, 社宅
  └─ run_diff()             # 比對 history.jsonl → new / price_drop / unchanged / delisted
       └─ 下架偵測：本次才首次下架 → 進報表一次（delisted_date 寫入）；已有 delisted_date → 不再出現
       └─ 更新 all_listings.jsonl  # 完整 Property 欄位，含 listed_date / delisted_date
       └─ 更新 history.jsonl       # 精簡記錄，供 diff 邏輯用
  └─ render_report()        # 產出 reports/report_YYYYMMDD.html（先刪舊的）
  └─ publish()              # PUT index.html 到 gh-pages（選填，config 有設定才跑）
```
