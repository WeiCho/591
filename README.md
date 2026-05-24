# 台灣租房監控機器人

每次執行抓取 591 租屋資訊 → 去重過濾 → 歷史比對 → 輸出靜態 HTML 報表 → 自動發布到 GitHub Pages。

## 執行

```powershell
py main.py                    # 全平台正式執行
py main.py --platforms 591    # 只跑 591
py main.py --dry-run          # 測試模式（不打網路）
```

> **重要**：Windows 上必須用 `py`，不是 `python`（python 指向 MS Store 空殼）

## 專案結構

```
main.py                   # 主程式入口
config.json               # 搜尋條件設定
src/
  config_loader.py        # 設定檔讀取與驗證
  models.py               # Property dataclass + parse_floor_string()
  diff_engine.py          # 歷史比對（history.jsonl + all_listings.jsonl）
  filter_engine.py        # 去重 + 條件過濾
  report_generator.py     # Jinja2 + Tailwind CDN → 靜態 HTML
  github_publisher.py     # GitHub Contents API → gh-pages 自動發布
  fetchers/
    base.py               # clean_price(), clean_area()
    fetcher_591.py        # 591 爬蟲（Playwright）
reports/                  # 產出的 HTML 報表（每次執行覆蓋）
history.jsonl             # diff 用歷史庫（精簡欄位）
all_listings.jsonl        # 顯示用歷史庫（完整 Property 欄位）
```

## config.json 欄位

```json
{
  "cities": [
    { "name": "新北市", "regions": ["新店區", "中和區", "永和區", "板橋區", "土城區", "三重區", "蘆洲區"] },
    { "name": "台北市", "regions": ["信義區", "中山區", "中正區", "松山區", "萬華區", "士林區", "大安區"] }
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

- `regions` 名稱需帶「區」，與 591 address 格式一致
- `regions` 設為空陣列則不限行政區
- `pet_friendly`：設定但過濾邏輯尚未實作
- `github_publish`：選填，省略則只產本機報表

## GitHub Pages 初次設定（一次性）

1. 在 GitHub 新建一個 **public** repo，例如 `rent-report`
2. 建立 **fine-grained PAT**：Settings → Developer settings → Fine-grained tokens
   - Repository access：只選 `rent-report`
   - Permissions → Contents：**Read and write**
3. 把 token 填入 `config.json` 的 `github_publish.token`
4. 跑一次 `py main.py` — publisher 會自動建立 `gh-pages` branch 並上傳 `index.html`
5. repo Settings → Pages → Source 選 **gh-pages** branch，root `/`
6. 之後報表網址固定為 `https://username.github.io/rent-report/`

## Report 功能

- **城市 tab**：多城市時顯示，切換後只顯示該城市的區域
- **區域 tag**：點選行政區快速篩選
- **建物分頁**：電梯大樓／華廈 vs 公寓（依 591 `tags` 欄位判斷）
- **四種狀態**：新上架 / 降價 / 在架中 / 本次下架
  - 下架：首次消失當天顯示一次（灰色遮罩），之後不再出現
- **上架日期**：從 `post_time` Unix timestamp 解析，卡片顯示，各 section 依上架日期降序排列

## 注意

591 受 Cloudflare 保護，爬蟲**只能在本機執行**，外部 IP（GitHub Actions 等）會被 403 擋。
