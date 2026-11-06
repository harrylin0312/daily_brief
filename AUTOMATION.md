# 每日自動產製與發布

此文件是本機 Codex 排程的固定作業流程。使用繁體中文，先讀集合與正式副本的 `AGENTS.md`。使用者已事先授權本專案內容更新、必要驗證、commit、正常 push 與既有 GitHub Pages 發布，不需每日確認。不得啟用額外付費 API 或使用 Gemini。

## 1. 開工與防止重複

- 正式副本 `/Users/linhengyu/Downloads/code/GHProjects/daily_brief`，分支 `main`，origin 必須為 `https://github.com/harrylin0312/daily_brief.git`。
- 每天臺灣時間 05:00 開始。先檢查工作目錄、暫存區與未推送提交，再 fetch。乾淨且可快轉才 `git pull --ff-only`；衝突、其他人的修改或不明提交都保留並回報，不自動 stash、不強推。
- 若臺灣當日刊期已提交並推送，先執行 `python3 scripts/brief.py verify-deploy`。確認成功就結束，不重複刊登、產圖或消耗額度。若是本次流程留下的未推送日報提交，可用 publish 續推；無法辨認則停止。
- 同一對話排程不要重疊執行。build／publish 本身另有作業系統檔案鎖，避免同時寫入；不要刪除鎖檔來繞過執行中的工作。異常結束時作業系統會釋放鎖。

## 2. 蒐集與編輯

- 先讀 `content/index.json` 與近期刊期，搜尋上期成功整理後的新資訊，預設看近 48 小時；中斷多日則交代缺刊與實際涵蓋範圍，不偽造過去日報。
- 三類各自精選：AI 實用情報、AI 開發與技術、科技與產業大事。沒有最低則數；沒有值得注意的消息就略過該類。
- 優先直接閱讀官方公告、原始研究與開發文件；至少成功檢查三個不同來源並記錄檢查結果。搜尋摘要只能用來發現消息，不當作已讀原文。來源清單可從 OpenAI News、Anthropic／Claude 更新、GitHub Changelog、Google 官方部落格、NVIDIA 官方技術文章與所涉專案官方儲存庫開始，不限於這些來源。
- 每則寫清事實、重要性與適用限制，避免宣傳式效能結論。保留原始發布日期、查核時間與 HTTPS 連結。用穩定事件 ID，同事件合併，重複來源跨期刊登需寫 `update_of`（前次刊期日期）與 `update_note`（實質新變化）。
- 新增 `content/issues/YYYY-MM-DD.json`，以既有刊期為格式參考。`generated_at` 與來源 `checked_at` 必須是真實執行時間並含時區；刊期依 Asia/Taipei。不得捏造閱讀、查核、來源或發生時間。
- 若直接 HTTP 遇 403，但確實已用網頁工具讀到原文，可於該來源記錄 `verification_method: "web"` 與具體 `verification_note`。發布工具只接受 24 小時內此類替代查核，並明確輸出 HTTP 限制；不可只為通過檢查填寫虛假紀錄。404、429、5xx 等仍須解決或移除該則。
- 全部來源失敗不可當作「沒有新聞」。關鍵來源查核不足就停止本次發布，保留舊刊。只有成功查核後真的無重要消息，才可使用空 `stories`、`hero: null` 與真實 `empty_reason`。

## 3. 配圖

- 依內容選用有可用權利的官方圖、原創資訊圖或訂閱內 imagegen 概念插圖。不可假設官方網站的所有圖片都能轉載；無法確認時改用原創圖解。
- 封面存入 `assets/`，使用小型 JPEG／WebP，填寫 alt、種類及 credit；AI 圖標示為概念圖，不冒充產品或事件照片。可延用合適的既有概念封面，無須每日生成。
- 文章可選 `bars`（附數據來源網址與真實數字）、`flow` 或 `memory` 圖解；不需要圖就省略 visual。既有 schema 的條件不適用某新聞時，只用文字，不為湊圖捏造圖表。

## 4. 驗證與發布

```sh
python3 scripts/brief.py build
python3 scripts/brief.py check
python3 -m unittest discover -s tests
node --check app.js
python3 scripts/brief.py check-links
git diff --check
```

- 本機用 `python3 -m http.server 8000 --bind 127.0.0.1` 預覽；確認封面與圖表、分類、搜尋、來源展開、歷史頁。版面修改需以桌面與手機尺寸實際檢查；日常純內容更新至少檢查長標題、圖片與圖表沒有溢出。若瀏覽器工具不可用，在其餘檢查通過後可沿用已驗證模板，但回報當次未做視覺驗證，不宣稱已測。
- 驗證通過後：

```sh
python3 scripts/brief.py publish
```

publish 只允許當日日報 JSON、產生頁面、索引、feed 與圖片，不會夾帶程式或其他檔案。既有程式若需修復，另行審查、測試與明確提交，不繞過白名單。無內容變更不建立空提交。提交名稱為 `Publish daily brief YYYY-MM-DD`，正常 push 至 origin/main。

- push 與部署分開確認。GitHub Pages 更新可能需要數分鐘；publish 若回報部署未確認，不重新產生一期或重新提交，稍後執行 `verify-deploy`。最多再查三次，每次隔約 30–60 秒，持續失敗如實回報。
- 網路暫時錯誤每階段最多三次並遵守 Retry-After；認證、額度、衝突與內容品質問題不盲目重試。遇 push 被拒絕，重新 fetch 盤點，不強制推送。
- 結果交代刊期、精選數、來源限制、commit、push 與部署實際狀態，附網站網址。不要把 commit 成功或 push 成功當成網站已更新。

## 5. 環境限制

本機排程需要 Mac 保持喚醒、連網且 Codex App 運作。訂閱額度、工具與網站可用性影響成功率，不保證準時完成。不得把 token、金鑰、.env、帳務資訊、私人檔案與本機快取提交或寫進通知。既有 `.nojekyll` 保留，沿用目前 GitHub Pages 靜態根目錄部署，不另建付費服務。
