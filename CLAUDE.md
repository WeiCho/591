# 台灣租房監控機器人 — 開發參考

## 執行

```powershell
py main.py --platforms 591    # 只跑 591（目前唯一實作的平台）
py main.py --dry-run          # 不打網路，測試 diff + report 流程
```

---

## 591 爬蟲

**API**：`GET https://bff-house.591.com.tw/v3/web/rent/list`

必要 headers：`device: pc`、`Referer: https://rent.591.com.tw/`

關鍵 params：

| 參數 | 說明 |
|------|------|
| `regionid` | 新北市=3, 台北市=1 |
| `section` | 板橋=26, 中和=38, 永和=37, 新店=34, 土城=39, 三重=43, 蘆洲=47, 信義=6, 中山=4, 大安=7 |
| `kind` | 整層住家=1, 獨立套房=2, 分租套房=3 |
| `firstRow` | 分頁起始，每頁 30 筆 |
| `price` | `"15000_28000"` |
| `floor` | `"2_"` |

**陷阱**：
- 舊版端點 `rent.591.com.tw/home/search/rsList` 已廢棄（419），勿使用
- pure httpx 會被 Cloudflare 擋 → 必須用 Playwright headless 暖身建 session，再用 `context.request.get()` 打 API
- 每個 section 各自開一個 browser，間隔 1.2 秒，`if not items` 判斷最後一頁
- `price` 欄位是字串 `"25,000"`，需 replace 逗號轉 int
- `has_elevator`：`tags` 含 `"有電梯"` **或** `total_floors >= 7` **或** `current_floor >= 7`（台灣公寓最高 6 層，7F+ 必有電梯）

---

## 過濾規則（filter_engine.py）

- **去重**：address + price + area + floor 完全相同 → 只保留第一筆
- **社宅**：title **或** tags 含「社宅」/「社會住宅」→ 排除（寫死）
- **頂加**：title/floor/address 含「頂加」等關鍵字 → 排除（config 開關）
- **頂樓**：current_floor == total_floors → 排除（config 開關）
- **樓層/坪數下限**：低於 floor_min / area_min → 排除

---

## 資料流

```
fetcher → dedup → filter → diff → report → publish
```

- `history.jsonl`：精簡記錄，供 diff 比對用
- `all_listings.jsonl`：完整 Property 欄位，含 listed_date / delisted_date
- 下架偵測：本次首次消失 → 進報表一次（灰色遮罩）；已有 delisted_date → 不再出現
- `reports/report_YYYYMMDD.html`：每次產出前先刪舊的
- publish：PUT index.html 到 gh-pages（GitHub Contents API，不需要 git CLI），失敗只 log warning

---

## config.json 結構

```json
{
  "cities": [{ "name": "新北市", "regions": ["新店區"] }],
  "price_min": 15000, "price_max": 28000,
  "room_types": ["整層住家"],
  "floor_min": 2, "area_min": 15,
  "exclude_rooftop_addition": true,
  "exclude_top_floor": true,
  "github_publish": { "repo": "owner/repo", "token": "ghp_xxxx" }
}
```
