# 台灣租房監控機器人

每次執行抓取 591 租屋資訊 → 去重過濾 → 歷史比對 → 輸出靜態 HTML 報表。

## 執行

```powershell
py main.py --platforms 591    # 正式執行
py main.py --dry-run          # 測試模式（不打網路）
```

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
  fetchers/
    base.py               # clean_price(), clean_area()
    fetcher_591.py        # 591 爬蟲（Playwright）
    sinyi.py              # 信義房屋（架構完成，selector 待驗證）
    yungching.py          # 永慶房屋（架構完成，selector 待驗證）
reports/                  # 產出的 HTML 報表（每次執行覆蓋）
history.jsonl             # diff 用歷史庫（精簡欄位）
all_listings.jsonl        # 顯示用歷史庫（完整 Property 欄位）
```

## config.json 欄位

```json
{
  "target_cities": ["新北市"],
  "target_regions": ["新店", "中和", "永和", "板橋", "土城", "三重", "蘆洲"],
  "price_min": 15000,
  "price_max": 28000,
  "room_types": ["整層住家"],
  "pet_friendly": false,
  "floor_min": 2,
  "area_min": 15,
  "exclude_rooftop_addition": true,
  "exclude_top_floor": true
}
```

`target_regions` 設為 `["全區"]` 或空陣列則不限行政區。

## Report 功能

- **區域 tag**：點選行政區快速篩選，支援「全部」
- **建物分頁**：電梯大樓／華廈 vs 公寓（依 591 `tags` 欄位判斷）
- **四種狀態**：新上架 / 降價 / 在架中 / 已下架
- **下架偵測**：上次有、這次沒撈到的物件自動標為已下架

## 完成狀態

- `fetcher_591.py` — 實測正常，支援 section 行政區篩選
- `diff_engine.py` — history + all_listings 雙庫，下架偵測
- `filter_engine.py` — 去重（address+price+area+title）+ 條件過濾
- `report_generator.py` — 區域 tag + 電梯/公寓 tab + 互動篩選
- `sinyi.py` / `yungching.py` — 架構完成，selector 尚未驗證

## 注意

591 受 Cloudflare 保護，爬蟲**只能在本機執行**，外部 IP（GitHub Actions 等）會被 403 擋。
