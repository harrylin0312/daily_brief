#!/usr/bin/env python3
"""Build, validate and publish the daily brief. Python standard library only."""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit, unquote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {"practical": ("AI 實用情報", "TOOLS & MODELS"),
              "development": ("AI 開發與技術", "BUILD & CREATE"),
              "industry": ("科技與產業大事", "THE BIG PICTURE")}
GENERATED = ("index.html", "archive.html", "feed.xml", "content/index.json")


def esc(value):
    return html.escape(str(value), quote=True)


def config(root=ROOT):
    return json.loads((root / "site.json").read_text())


def today():
    return dt.datetime.now(ZoneInfo("Asia/Taipei")).date()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local_asset(path, root):
    require(isinstance(path, str) and not urlsplit(path).scheme and not path.startswith("/"), "圖片必須是專案內相對路徑")
    resolved = (root / path).resolve()
    require(resolved.is_relative_to(root.resolve()) and resolved.is_file(), f"資產不存在：{path}")
    return resolved


def valid_url(url):
    u = urlsplit(url)
    require(u.scheme == "https" and u.hostname and not u.username and not u.password, f"來源須為公開 HTTPS 網址：{url}")
    require(u.hostname not in ("localhost", "127.0.0.1", "::1") and not re.match(r"^\d+\.\d+\.\d+\.\d+$", u.hostname), "來源不可為本機或 IP 網址")


def validate_issue(issue, root=ROOT):
    required = ("date", "title", "intro", "generated_at", "coverage", "editor_note", "source_checks", "stories")
    require(all(k in issue for k in required), "刊期缺少必要欄位")
    day = dt.date.fromisoformat(issue["date"])
    require(day <= today(), "不可發布未來刊期")
    stamp = dt.datetime.fromisoformat(issue["generated_at"])
    require(stamp.tzinfo is not None and stamp.astimezone(ZoneInfo("Asia/Taipei")).date() == day, "整理時間必須含時區並與刊期相符")
    require(stamp <= dt.datetime.now(dt.timezone.utc), "整理時間不可在未來")
    coverage = issue["coverage"]
    begin, end = (dt.date.fromisoformat(coverage[x]) for x in ("from", "to"))
    require(begin <= end <= day, "來源涵蓋日期無效")
    checks = issue["source_checks"]
    require(len(checks) >= 3 and len({c["name"] for c in checks}) == len(checks), "至少查核三個不同來源")
    for check in checks:
        valid_url(check["url"])
        require(check["status"] in ("checked", "failed"), "來源狀態無效")
        require(bool(check.get("note")), "來源檢查需備註")
    require(sum(c["status"] == "checked" for c in checks) >= 3, "至少三個來源成功查核才可刊登")
    require(isinstance(issue["stories"], list), "stories 須為陣列")
    ids, urls = set(), set()
    for s in issue["stories"]:
        require(all(s.get(k) for k in ("id", "category", "title", "summary", "why", "limit", "sources")), "新聞欄位不完整")
        require(re.fullmatch(r"[a-z0-9-]+", s["id"]) and s["id"] not in ids, "新聞 ID 無效或重複")
        ids.add(s["id"])
        require(s["category"] in CATEGORIES, "未知主題分類")
        require(len(s["title"]) <= 70 and len(s["summary"]) <= 400 and len(s["why"]) <= 220, "新聞過長，請精簡")
        for source in s["sources"]:
            require(all(source.get(k) for k in ("name", "url", "published", "checked_at")), "來源欄位不完整")
            valid_url(source["url"])
            published = dt.date.fromisoformat(source["published"])
            require(begin <= published <= end, "新聞日期超出刊期涵蓋範圍")
            checked = dt.datetime.fromisoformat(source["checked_at"])
            require(checked.tzinfo is not None and checked <= stamp and checked.astimezone(ZoneInfo("Asia/Taipei")).date() == day, "查核時間無效，須為刊期當日的真實查核")
        primary = s["sources"][0]["url"].rstrip("/")
        require(primary not in urls, "同一期重複刊登同一來源事件")
        urls.add(primary)
        if s.get("visual"):
            v = s["visual"]
            require(v["type"] in ("bars", "memory", "flow"), "未知圖表類型")
            require(v.get("caption"), "圖表需有說明")
            if v["type"] == "bars":
                require(v.get("source_url") in [x["url"] for x in s["sources"]], "數據圖必須引用該則來源")
                require(0 < len(v["items"]) <= 5, "比較數據數量無效")
                for item in v["items"]:
                    require(isinstance(item["value"], (int, float)) and 0 <= item["value"] <= 100 and item["label"], "百分比數據無效")
            else:
                require(1 <= len(v["items"]) <= 5 and all(v["items"]), "圖解項目無效")
    hero = issue.get("hero")
    if issue["stories"]:
        require(hero and hero["story_id"] in ids, "焦點新聞不存在")
        require(all(hero.get(k) for k in ("image", "alt", "credit", "kind")), "封面需圖片、替代文字與來源標示")
        require(hero["kind"] in ("ai", "official", "original"), "封面圖片類型無效")
        require(len(hero["credit"]) > 5, "圖片必須有出處說明")
        local_asset(hero["image"], root)
    else:
        require(bool(issue.get("empty_reason")), "零新聞刊期需寫明原因，擷取失敗不可當作無新聞")
    return issue


def load_issues(root=ROOT):
    issues = []
    for path in sorted((root / "content/issues").glob("*.json"), reverse=True):
        issue = validate_issue(json.loads(path.read_text()), root)
        require(path.stem == issue["date"], "檔名與刊期日期不符")
        issues.append(issue)
    require(issues, "尚無可發布刊期")
    seen = {}
    for issue in reversed(issues):
        for s in issue["stories"]:
            key = s["sources"][0]["url"].rstrip("/")
            if key in seen:
                require(s.get("update_of") == seen[key] and s.get("update_note"), "跨期重複來源需 update_of 與實質更新說明")
            seen[key] = issue["date"]
    return issues


def page(title, description, body, prefix, canonical, cfg):
    return f'''<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}"><meta name="theme-color" content="#f5f3ed">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:type" content="website">
<meta property="og:url" content="{esc(canonical)}"><link rel="canonical" href="{esc(canonical)}">
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="{prefix}assets/site.css">
<link rel="alternate" type="application/atom+xml" title="每日科技快報" href="{prefix}feed.xml"><script src="{prefix}app.js" defer></script></head>
<body><a class="skip" href="#main">跳到內容</a><div class="shell">
<header class="masthead"><a class="brand" href="{prefix}index.html" aria-label="每日科技快報首頁"><span class="brand-mark" aria-hidden="true">d<span>•</span>b</span><span>DAILY BRIEF<small>每日科技快報</small></span></a>
<nav aria-label="主選單"><a href="{prefix}index.html">最新一期</a><a href="{prefix}archive.html">歷史日報 <span aria-hidden="true">↗</span></a><a class="nav-about" href="#approach">關於快報</a></nav></header>
{body}
<section class="approach" id="approach"><p class="eyebrow">A LITTLE LESS NOISE</p><h2>資訊很多，值得讀的就好。</h2><p>以原始來源為起點，由 Codex 蒐集、查核並整理。只挑重要的，不湊篇數；事實、解讀與限制分開呈現。內容可能有誤，重要決策請回到原文核對。</p><details><summary>我們如何選題與使用圖片</summary><p>優先官方公告、開發文件與原始研究，依實際影響與新資訊選題。同事件合併，未確認消息不當作事實。數據圖保留出處，概念圖與 AI 生成圖片明確標示，不當作事件照片。部分來源失敗會在當期揭露；關鍵查核失敗則不發布新刊。</p></details></section>
<footer><a class="footer-brand" href="{prefix}index.html">Daily Brief<span>少一點雜訊，多一點理解。</span></a><p>繁體中文 · Asia/Taipei<br>每天 05:00 開始整理，完成後更新</p><a href="{prefix}feed.xml">訂閱 RSS <span aria-hidden="true">↗</span></a><a href="https://github.com/harrylin0312/daily_brief" rel="noopener noreferrer">GitHub ↗</a></footer>
</div></body></html>'''


def visual(v):
    if not v:
        return ""
    if v["type"] == "bars":
        items = "".join(f'<div class="bar-row"><span>{esc(i["label"])}</span><div class="bar-track"><span style="width:{i["value"]}%"></span></div><strong>{i["value"]}%</strong></div>' for i in v["items"])
        inner = f'<div class="bar-chart">{items}</div>'
    else:
        cls = "memory-stack" if v["type"] == "memory" else "flow"
        items = "".join(f'<li><span class="step-number">0{i + 1}</span>{esc(item)}</li>' for i, item in enumerate(v["items"]))
        inner = f'<ol class="{cls}">{items}</ol>'
    return f'<figure class="data-visual">{inner}<figcaption>{esc(v["caption"])}</figcaption></figure>'


def story_card(s, number):
    category, english = CATEGORIES[s["category"]]
    sources = "".join(f'<li><a href="{esc(x["url"])}" target="_blank" rel="noopener noreferrer">{esc(x["name"])} <span aria-hidden="true">↗</span></a><span>發布 {esc(x["published"])} · 查核 {esc(x["checked_at"])}</span></li>' for x in s["sources"])
    update = f'<p class="limitation">後續更新：{esc(s["update_note"])}</p>' if s.get("update_note") else ""
    return f'''<article class="story" id="{esc(s["id"])}" data-story data-category="{esc(s["category"])}">
<div class="card-top"><span class="category {s["category"]}">{category}</span><span class="story-no">{number:02d} / {english}</span></div>
<h3>{esc(s["title"])}</h3><p class="summary">{esc(s["summary"])}</p>{visual(s.get("visual"))}
<p class="why"><span>值得注意</span>{esc(s["why"])}</p><p class="limitation">{esc(s["limit"])}</p>{update}
<div class="card-bottom"><span>{esc(s["sources"][0]["name"])} · {esc(s["sources"][0]["published"])}</span><a href="{esc(s["sources"][0]["url"])}" target="_blank" rel="noopener noreferrer">閱讀原文 ↗</a></div>
<details class="sources"><summary>來源與查核紀錄</summary><ul>{sources}</ul></details></article>'''


def issue_page(issue, all_issues, cfg, archived=False):
    prefix = "../" if archived else "./"
    day = dt.date.fromisoformat(issue["date"])
    weekday = "一二三四五六日"[day.weekday()]
    count = len(issue["stories"])
    number = next(i for i, x in enumerate(reversed(all_issues), 1) if x["date"] == issue["date"])
    timestamp = dt.datetime.fromisoformat(issue["generated_at"]).astimezone(ZoneInfo("Asia/Taipei"))
    freshness = "" if archived else f'<p class="freshness" data-freshness="{issue["date"]}" hidden>目前顯示最近一期（{issue["date"]}）。新刊尚未更新，請稍後再看。</p>'
    archived_banner = f'<p class="archive-banner">你正在閱讀歷史日報。<a href="../index.html">查看最新一期 →</a></p>' if archived else ""
    header = f'''<main id="main">{archived_banner}{freshness}<div class="issue-line"><span><span class="live-dot" aria-hidden="true"></span>{day:%Y.%m.%d} <span class="muted">星期{weekday}</span></span><span>VOL. {number:03d} <span class="line-separator">/</span> {count} 則精選 · 約 {max(1, round(count * .7))} 分鐘</span></div>'''
    if count:
        hero = issue["hero"]
        focus = next(x for x in issue["stories"] if x["id"] == hero["story_id"])
        kind = {"ai": "AI 生成概念圖，非事件照片", "official": "官方圖片", "original": "原創圖解"}[hero["kind"]]
        lead = f'''<section class="hero" aria-labelledby="issue-title"><div class="hero-copy"><p class="eyebrow"><span>今日焦點</span> / THE DAILY SIGNAL</p><h1 id="issue-title">{esc(issue["title"])}</h1><p class="hero-dek">{esc(issue["intro"])}</p><a class="read-focus" href="#{esc(focus["id"])}">讀懂這件事 <span aria-hidden="true">↘</span></a><p class="hero-meta">{esc(focus["sources"][0]["name"])} · {esc(CATEGORIES[focus["category"]][0])}</p></div><figure class="hero-art"><img src="{prefix}{esc(hero["image"])}" alt="{esc(hero["alt"])}" width="1536" height="1024" fetchpriority="high"><figcaption><span>{esc(kind)}</span><span>DAILY BRIEF / {number:03d}</span></figcaption></figure></section>'''
    else:
        lead = f'<section class="empty-issue"><p class="eyebrow">TODAY, LESS IS MORE</p><h1 id="issue-title">{esc(issue["title"])}</h1><p>{esc(issue["empty_reason"])}</p></section>'
    items = "".join(story_card(s, i) for i, s in enumerate(issue["stories"], 1))
    filters = "".join(f'<button type="button" data-category="{k}" aria-pressed="false">{v[0]}</button>' for k, v in CATEGORIES.items())
    skipped = [v[0] for k, v in CATEGORIES.items() if not any(s["category"] == k for s in issue["stories"])]
    omitted = f'<p class="muted category-note">本期未收錄：{esc("、".join(skipped))}。沒有值得補充的消息，就不湊數。</p>' if skipped else ""
    coverage = issue["coverage"]
    checked = "".join(f'<li><a href="{esc(c["url"])}" target="_blank" rel="noopener noreferrer">{esc(c["name"])} ↗</a><span>{"已查閱" if c["status"] == "checked" else "查閱失敗"} · {esc(c["note"])}</span></li>' for c in issue["source_checks"])
    previous = next((x for x in all_issues if x["date"] < issue["date"]), None)
    previous_link = f'<a href="{prefix}issues/{previous["date"]}.html">← 上一期 · {previous["date"]}</a>' if previous else '<span>這是第一期，從今天開始。</span>'
    rest = f'''<div class="editor-strip"><span class="strip-label">編輯手記</span><p>{esc(issue["editor_note"])}</p><span class="edition-tag">NO FILLER.<br>JUST SIGNAL.</span></div>
<section class="briefs" aria-labelledby="briefs-title"><div class="section-title"><div><p class="eyebrow">YOUR DAILY READING LIST</p><h2 id="briefs-title">今天，值得知道的事<span class="tiny-count">{count:02d}</span></h2></div><span class="muted">精簡重點 · 保留脈絡</span></div>
<div data-interactive hidden class="reading-tools"><div class="filters" data-filters role="group" aria-label="篩選新聞主題"><button type="button" data-category="all" aria-pressed="true">全部</button>{filters}</div><label class="search"><span class="sr-only">搜尋本期新聞</span><input id="story-search" type="search" placeholder="搜尋本期關鍵字" autocomplete="off"><span aria-hidden="true">⌕</span></label></div>
<p class="result-count" data-result-count aria-live="polite">顯示 {count} 則精選</p><div class="story-grid">{items}</div><p class="empty-results" data-empty hidden>沒有符合的新聞，試試其他關鍵字或分類。</p>{omitted}</section>
<aside class="edition-notes"><div><p class="eyebrow">ABOUT THIS EDITION</p><h2>每一則，都能回到來源。</h2></div><div><p>整理於 <time datetime="{esc(issue["generated_at"])}">{timestamp:%Y-%m-%d %H:%M}（臺灣時間）</time><br>本期來源發布日期：{coverage["from"]} — {coverage["to"]}</p><details><summary>本期來源檢查與圖片出處</summary><ul class="check-list">{checked}</ul><p>{esc((issue.get("hero") or {}).get("credit", "本期無封面圖片。"))}</p></details></div></aside>
<nav class="issue-pager" aria-label="期數導覽">{previous_link}<a href="{prefix}archive.html">所有歷史日報 ↗</a></nav></main>'''
    canonical = cfg["url"] + (f'issues/{issue["date"]}.html' if archived else "")
    return page(f'{issue["date"]}｜{issue["title"]} — Daily Brief', issue["intro"], header + lead + rest, prefix, canonical, cfg)


def render(root=ROOT):
    issues = load_issues(root)
    cfg = config(root)
    outputs = {"index.html": issue_page(issues[0], issues, cfg)}
    for issue in issues:
        outputs[f'issues/{issue["date"]}.html'] = issue_page(issue, issues, cfg, True)
    rows = "".join(f'''<a class="archive-row" href="./issues/{i["date"]}.html"><span class="archive-date">{esc(i["date"])}</span><div><h2>{esc(i["title"])}</h2><p>{esc(i["intro"])}</p></div><span class="archive-count">{len(i["stories"])} 則精選 <span aria-hidden="true">↗</span></span></a>''' for i in issues)
    body = f'<main id="main" class="archive-main"><p class="eyebrow">THE READING ROOM</p><h1>每天一點，<br>慢慢讀懂世界。</h1><p class="archive-intro">所有已刊出的科技快報，保留當時的重點與來源。</p><div class="section-title"><h2>歷史日報</h2><span class="muted">共 {len(issues)} 期</span></div><div class="archive-list">{rows}</div></main>'
    outputs["archive.html"] = page("歷史日報 — Daily Brief", "回顧每一期每日科技快報。", body, "./", cfg["url"] + "archive.html", cfg)
    outputs["content/index.json"] = json.dumps([{"date": i["date"], "title": i["title"], "count": len(i["stories"])} for i in issues], ensure_ascii=False, indent=2) + "\n"
    entries = "".join(f'<entry><title>{esc(i["title"])}</title><id>{cfg["url"]}issues/{i["date"]}.html</id><link href="{cfg["url"]}issues/{i["date"]}.html"/><updated>{esc(i["generated_at"])}</updated><summary>{esc(i["intro"])}</summary></entry>' for i in issues)
    outputs["feed.xml"] = f'<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Daily Brief 每日科技快報</title><id>{cfg["url"]}</id><link href="{cfg["url"]}feed.xml" rel="self"/><link href="{cfg["url"]}"/><updated>{issues[0]["generated_at"]}</updated><author><name>Daily Brief</name></author>{entries}</feed>\n'
    return outputs


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            require(a["id"] not in self.ids, f'重複 HTML ID：{a["id"]}')
            self.ids.add(a["id"])
        for field in ("src", "href"):
            if field in a:
                self.refs.append(a[field])
        if tag == "img":
            require(bool(a.get("alt")), "圖片缺少替代文字")


def validate_outputs(outputs, root=ROOT):
    for name, text in outputs.items():
        if not name.endswith(".html"):
            continue
        p = LinkParser()
        p.feed(text)
        require('lang="zh-Hant"' in text and 'name="viewport"' in text, "頁面缺少語言或行動裝置設定")
        for ref in p.refs:
            u = urlsplit(ref)
            if u.scheme or u.netloc:
                require(u.scheme == "https", "頁面含不安全外部網址")
                continue
            target = (root / name).parent / unquote(u.path) if u.path else root / name
            target = target.resolve()
            require(target.is_relative_to(root.resolve()), "資產路徑超出專案")
            relative = str(target.relative_to(root.resolve()))
            require(relative in outputs or target.is_file(), f"頁面連結不存在：{name} → {ref}")
            if u.fragment and (not u.path or relative == name):
                require(u.fragment in p.ids, f"錨點不存在：{name} → {ref}")


def build(root=ROOT, check=False):
    outputs = render(root)
    validate_outputs(outputs, root)
    if check:
        mismatch = [p for p, text in outputs.items() if not (root / p).is_file() or (root / p).read_text() != text]
        require(not mismatch, "產出未更新，請先 build：" + ", ".join(mismatch))
        print(f"PASS：{len(load_issues(root))} 期，{len(outputs)} 個產出與所有本機連結有效")
        return
    # Validate the whole build before writing. Publish makes the Git commit atomic.
    with tempfile.TemporaryDirectory(prefix=".build-", dir=root) as staging:
        for name, text in outputs.items():
            path = Path(staging) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for name in sorted(outputs, key=lambda n: n == "index.html"):
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            os.replace(Path(staging) / name, root / name)
    print(f"已產生 {len(outputs)} 個檔案，最新刊期 {load_issues(root)[0]['date']}")


@contextlib.contextmanager
def lock(root=ROOT):
    with (root / ".brief.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("另一次建置或發布正在執行，本次停止")
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def run(*args, root=ROOT):
    result = subprocess.run(args, cwd=root, text=True, capture_output=True)
    if result.returncode:
        raise ValueError(f"指令失敗：{' '.join(args[:3])}\n{result.stderr.strip()}")
    return result.stdout.strip()


def check_links(root=ROOT):
    issue = load_issues(root)[0]
    sources = {s["url"]: s for story in issue["stories"] for s in story["sources"]}
    # Live fetch is an availability check; editorial fact verification is still required.
    for url, source in sorted(sources.items()):
        code = run("curl", "--location", "--silent", "--show-error", "--max-time", "25", "--retry", "2", "--retry-max-time", "65", "--output", os.devnull, "--write-out", "%{http_code}", url, root=root)
        if code.startswith("2"):
            print(f"OK {url}")
        else:
            # Some publishers block automated requests. Only a real, recent alternate
            # reading recorded by the editor may substitute; never treat 403 as 200.
            checked = dt.datetime.fromisoformat(source["checked_at"])
            age = dt.datetime.now(dt.timezone.utc) - checked
            verified = source.get("verification_method") == "web" and bool(source.get("verification_note"))
            require(code == "403" and verified and dt.timedelta(0) <= age <= dt.timedelta(hours=24), f"來源 HTTP {code} 且沒有當日替代查核證據：{url}")
            print(f"NOTICE HTTP 403；已記錄當日網頁工具查核（非 HTTP 成功）：{url}")


def verify_deploy(root=ROOT):
    expected = hashlib.sha256((root / "index.html").read_bytes()).hexdigest()
    url = config(root)["url"] + "?v=" + run("git", "rev-parse", "--short", "HEAD", root=root)
    result = run("curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "25", url, root=root)
    # run strips the final newline, so compare normalized text.
    require(result == (root / "index.html").read_text().strip(), "GitHub Pages 尚未提供本次版本；push 可能成功，但部署未確認。請稍後重跑 verify-deploy")
    latest = load_issues(root)[0]
    assets = ["assets/site.css", "app.js", "archive.html", f'issues/{latest["date"]}.html', "content/index.json"]
    if latest.get("hero"):
        assets.append(latest["hero"]["image"])
    for asset in assets:
        response = subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error", "--max-time", "25", cfg_url(root, asset)], capture_output=True)
        require(response.returncode == 0 and response.stdout == (root / asset).read_bytes(), f"部署資產尚未一致：{asset}")
    print(f"部署已驗證：{config(root)['url']}（本機內容 SHA256 {expected[:12]}）")


def cfg_url(root, asset):
    return config(root)["url"] + asset + "?v=" + run("git", "rev-parse", "--short", "HEAD", root=root)


def publish(root=ROOT):
    cfg = config(root)
    require(run("git", "rev-parse", "--show-toplevel", root=root) == str(root.resolve()), "不是正式專案根目錄")
    require(run("git", "remote", "get-url", "origin", root=root) == cfg["repository"], "origin 不符，停止")
    require(run("git", "branch", "--show-current", root=root) == cfg["branch"], "目前不是指定發布分支")
    require(not run("git", "diff", "--cached", "--name-only", root=root), "已有暫存變更，停止以保留使用者工作")
    run("git", "fetch", "--prune", "origin", root=root)
    ahead, behind = map(int, run("git", "rev-list", "--left-right", "--count", "HEAD...origin/main", root=root).split())
    require(not behind, "本機落後遠端或分歧；先保留修改並人工檢查，不自動合併")
    require(ahead <= 1, "有多個未推送提交，停止以免夾帶其他工作")
    if ahead:
        subject = run("git", "log", "-1", "--format=%s", root=root)
        require(subject.startswith("Publish daily brief "), "有非日報未推送提交，停止")
    issue = load_issues(root)[0]
    require(issue["date"] == today().isoformat(), "只允許自動發布臺灣當日刊期")
    paths = run("git", "ls-files", "--modified", "--others", "--exclude-standard", root=root).splitlines()
    allowed = lambda p: p in GENERATED or p == f'content/issues/{issue["date"]}.json' or bool(re.fullmatch(r"issues/\d{4}-\d{2}-\d{2}\.html", p)) or (p.startswith("assets/") and Path(p).suffix.lower() in (".png", ".jpg", ".webp", ".svg"))
    require(all(allowed(p) for p in paths), "存在非每日內容修改，停止；程式變更需另外驗證與提交")
    require(not run("git", "ls-files", "--deleted", root=root), "存在檔案刪除，停止")
    build(root)
    check_links(root)
    build(root, check=True)
    run("git", "diff", "--check", root=root)
    paths = run("git", "ls-files", "--modified", "--others", "--exclude-standard", root=root).splitlines()
    require(all(allowed(p) for p in paths), "建置後出現非內容檔案，停止")
    for path in paths:
        if path.endswith(".json"):
            raw = (root / path).read_text()
            require(not re.search(r"(?:sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{25,}|gh[pousr]_[A-Za-z0-9]{20,})", raw), "內容可能包含金鑰，停止")
    if paths:
        run("git", "add", "--", *paths, root=root)
        run("git", "commit", "-m", "Publish daily brief " + issue["date"], root=root)
    else:
        print("內容無變更，不建立空提交；檢查是否有尚未推送版本")
    run("git", "push", "origin", cfg["branch"], root=root)
    print("push 成功：" + run("git", "rev-parse", "HEAD", root=root))
    verify_deploy(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "check", "check-links", "publish", "verify-deploy"))
    args = parser.parse_args()
    try:
        if args.command in ("build", "publish"):
            with lock():
                build() if args.command == "build" else publish()
        elif args.command == "check":
            build(check=True)
        elif args.command == "check-links":
            check_links()
        else:
            verify_deploy()
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        print(f"停止：{error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
