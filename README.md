# 台灣租房監控機器人

抓取 591 租屋資訊 → 去重過濾 → 歷史比對 → 輸出靜態 HTML 報表 → 自動發布 GitHub Pages。

## 設定

複製範例並填入你的搜尋條件：

```powershell
cp config.example.json config.json
```

- `regions` 帶「區」字；空陣列則不限行政區
- `github_publish` 選填，省略則只產本機報表；token 需 Contents R+W 權限

## 安裝

```powershell
pip install -r requirements.txt
playwright install chromium
```

## 執行

```powershell
py main.py                    # 正式執行
py main.py --platforms 591    # 只跑 591
py main.py --dry-run          # 測試模式（不打網路）
```

> Windows 必須用 `py`，不是 `python`（python 指向 MS Store 空殼）

## GitHub Pages 初次設定

1. 新建 **public** repo（例如 `rent-report`）
2. 建立 fine-grained PAT：Settings → Developer settings → Fine-grained tokens → Contents: Read and write
3. token 填入 `config.json` 的 `github_publish.token`
4. 跑一次 `py main.py` — 自動建立 `gh-pages` branch 並上傳
5. repo Settings → Pages → Source 選 **gh-pages** branch

報表網址：`https://username.github.io/rent-report/`

## 注意

591 受 Cloudflare 保護，**只能在本機執行**，外部 IP（GitHub Actions 等）會被 403 擋。
