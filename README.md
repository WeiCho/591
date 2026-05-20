# 台灣租房監控機器人

每日自動抓取 591/信義/永慶租屋資訊 → 過濾 → 歷史比對 → 輸出靜態 HTML 報表。

## 專案結構

```
main.py                        # 主程式入口
config.json                    # 搜尋條件設定
src/
  config_loader.py             # 設定檔讀取
  models.py                    # Property dataclass + parse_floor_string()
  diff_engine.py               # JSONL 歷史庫，偵測 New / Price Drop / Unchanged
  filter_engine.py             # 過濾：floor_min, exclude_rooftop, exclude_top_floor
  report_generator.py          # Jinja2 + Tailwind CDN → 靜態 HTML
  fetchers/
    base.py                    # clean_price(), clean_area(), throttle()
    fetcher_591.py             # 591 爬蟲
    sinyi.py                   # 信義房屋（架構完成，selector 待驗證）
    yungching.py               # 永慶房屋（架構完成，selector 待驗證）
```

## config.json 欄位

```json
{
  "target_cities": ["新北市"],
  "target_regions": ["全區"],
  "price_min": 15000,
  "price_max": 28000,
  "room_types": ["整層住家"],
  "has_elevator": true,
  "pet_friendly": false,
  "floor_min": 3,
  "exclude_rooftop_addition": true,
  "exclude_top_floor": true
}
```

## 完成狀態

### Phase 1 ✅ 全部完成
- `config_loader.py` — 11/11 assertions 通過
- `models.py` — `parse_floor_string()` 支援 5F/12F、B1/8F 等格式
- `diff_engine.py` — JSONL 歷史庫，New/Price Drop/Unchanged
- `filter_engine.py` — floor_min + exclude_rooftop + exclude_top_floor
- `test_phase1.py` — 情境 A/B/C/D 全通過

### Phase 2 ⚠️ 部分完成
- `fetcher_591.py` ✅ 完成，實測抓到 2734 筆（新北市整層住家）
- `sinyi.py` — 架構完成，selector 尚未驗證
- `yungching.py` — 架構完成，selector 尚未驗證
- `report_generator.py` ✅ 完成，`--dry-run` 正常產出報表
- `main.py` ✅ 完成

### 待處理
- 信義/永慶爬蟲 selector 驗證
- filter_engine 與 591 新資料格式的串接確認
