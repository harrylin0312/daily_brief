# Daily Brief｜每日科技快報

只留下值得知道的資訊。以全球官方來源為起點，整理成精簡的繁體中文日報，適時配圖，兼顧電腦與手機閱讀。

**網站：https://harrylin0312.github.io/daily_brief/**

## 第一版功能

- 今日焦點、AI 實用情報、AI 開發與技術、科技與產業大事；依重要性挑選，沒有最低篇數。
- 原創概念封面、來源明確的比較圖及流程圖；AI 圖片清楚標示。
- 每則提供重點、重要性、限制、原文網址與發布日期。
- 主題篩選、關鍵字搜尋、歷史日報與 Atom／RSS 訂閱。
- 不依賴外部前端套件、字型服務、資料庫或付費 AI API。內容直接產生為 HTML，停用 JavaScript 仍可閱讀。

## 本機執行

需要 Python 3.10 以上；JavaScript 語法檢查使用 Node.js，網站閱讀不需要 Node.js。

```sh
python3 scripts/brief.py build
python3 scripts/brief.py check
python3 -m unittest discover -s tests
node --check app.js
python3 -m http.server 8000 --bind 127.0.0.1
```

開啟 http://127.0.0.1:8000。首頁、歷史頁與 feed 都由建置工具產生，不直接手改 HTML。

## 每日自動更新

已設定本機 Codex 排程，每天 **Asia/Taipei 05:00 開始**。Codex 負責搜尋、查核與編輯，Python 工具負責資料檢查、頁面產生、提交、推送及部署比對。這不是網站內建的雲端 AI 排程：Mac 需保持喚醒、連網且 Codex App 運作，亦受訂閱額度與工具可用性限制。

完整固定流程與錯誤處理見 [AUTOMATION.md](AUTOMATION.md)。刊期資料在 `content/issues/YYYY-MM-DD.json`；以既有刊期作為格式參考，每日新增一份。適時更新同一事件需標明前期與實質新變化，不能複製舊新聞湊數。

```sh
python3 scripts/brief.py build
python3 scripts/brief.py check-links
python3 scripts/brief.py publish
# GitHub Pages 更新可能需幾分鐘；若尚未一致，稍後僅重查：
python3 scripts/brief.py verify-deploy
```

publish 有執行鎖，僅接受當日日報與內容產出，會檢查分支、origin、遠端進度、既有暫存變更與非內容修改。沒有變更就不製造空提交；不強推、不自動 stash、不覆寫其他工作。若圖片無法生成可沿用合適的封面；關鍵來源或驗證失敗則保留上一期。HTTP 檢查與編輯查核分開，網站拒絕自動請求時需記錄當日實際讀過原文的替代證據。

## 發布授權與守則

使用者於 2026-11-06 明確授權 Codex 在本專案完成必要實作、測試、內容更新、git commit、正常 push 至 origin/main 與既有 GitHub Pages 發布，不需逐次確認。授權不包含額外付費、帳號安全權限變更、刪除歷史或強制推送，也不取代工具安全限制。使用 Codex，不使用 Gemini，不自行啟用另計費 API。

只追蹤公開內容、必要素材與網站程式；不得提交金鑰、.env、帳務資訊、私人檔案與快取。發生衝突、認證或額度不足時保留現狀並回報，不為了完成而繞過限制。

本機產出、commit、push 與網站部署是不同階段。部署確認會比對遠端首頁、當期歷史頁、歷史列表、CSS、JavaScript、索引與封面內容；未比對成功不得宣稱上線。

## 正式副本與版本

正式本機路徑：`/Users/linhengyu/Downloads/code/GHProjects/daily_brief`，分支 `main`。

遠端：https://github.com/harrylin0312/daily_brief

本機詳細指引位於未追蹤的 `AGENTS.md`；可版本追蹤的作業規範保存在 README 與 AUTOMATION.md。既有 `.nojekyll` 保留，使用 GitHub Pages 根目錄發布。
