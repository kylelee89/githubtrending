import os, json, requests, re, base64
from datetime import datetime, timedelta

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
GH_TOKEN = os.environ.get("GH_TOKEN", "")
STATE_FILE = "previous_repos.json"

GH_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"token {GH_TOKEN}" if GH_TOKEN else ""
}

def fetch_trending_top50():
    since = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    url = f"https://api.github.com/search/repositories?q=created:>{since}&sort=stars&order=desc&per_page=50"
    r = requests.get(url, headers=GH_HEADERS, timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    return [item["full_name"] for item in items], {item["full_name"]: item for item in items}

def clean_md(text):
    text = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", text)   # 배지 링크
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)                # 이미지
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)     # 링크→텍스트
    text = re.sub(r"```[\s\S]*?```", "", text)                 # 코드블록
    text = re.sub(r"`[^`]+`", "", text)                        # 인라인 코드
    text = re.sub(r"#{1,6}\s*", "", text)                      # 헤더 기호
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)      # 볼드/이탤릭
    text = re.sub(r"^\s*[-*>|]\s*", "", text, flags=re.MULTILINE)  # 리스트/블록
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_readme_summary(full_name):
    try:
        r = requests.get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers=GH_HEADERS, timeout=10
        )
        if r.status_code != 200:
            return []
        raw = base64.b64decode(r.json()["content"]).decode("utf-8", errors="ignore")
        text = clean_md(raw)

        # 의미있는 문장만 추출 (30자 이상, URL 아닌 것)
        sentences = []
        for line in text.split("\n"):
            line = line.strip()
            if len(line) < 30:
                continue
            if re.search(r"https?://|copyright|license|install|npm|pip|cargo|brew|<|>", line, re.I):
                continue
            sentences.append(line)
            if len(sentences) >= 4:
                break
        return sentences
    except:
        return []

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": chunk}, timeout=15)
        print(f"Telegram: {r.status_code}")

# ── 이전 상태 로드 ──────────────────────────────
prev = []
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        prev = json.load(f)
print(f"이전 TOP50: {len(prev)}개")

# ── 오늘 TOP50 ──────────────────────────────────
today_list, today_info = fetch_trending_top50()
print(f"오늘 TOP50: {len(today_list)}개")

# ── 신규 진입 레포 ──────────────────────────────
prev_set = set(prev)
new_repos = today_list if not prev else [r for r in today_list if r not in prev_set]
print(f"신규 진입: {len(new_repos)}개")

if not new_repos:
    send_telegram("📊 오늘은 30일 TOP50에 새로 진입한 레포가 없습니다.")
else:
    today_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"🔥 깃허브 30일 트렌딩 신규 진입 {today_str}",
        f"TOP50 중 오늘 새로 들어온 {len(new_repos)}개\n"
    ]

    for i, repo in enumerate(new_repos, 1):
        info = today_info.get(repo, {})
        stars = info.get("stargazers_count", 0)
        forks = info.get("forks_count", 0)
        lang = info.get("language") or "N/A"
        desc = info.get("description") or ""
        topics = info.get("topics", [])
        created = info.get("created_at", "")[:10]

        print(f"[{i}/{len(new_repos)}] {repo}")
        readme_lines = extract_readme_summary(repo)

        lines.append(f"{'─'*28}")
        lines.append(f"{i}. {repo}")
        lines.append(f"⭐ {stars:,}  🍴 {forks:,}  {lang}  📅 {created}")
        if topics:
            lines.append(f"🏷 {' · '.join(topics[:5])}")
        lines.append("")
        if desc:
            lines.append(f"📌 {desc}")
        if readme_lines:
            for rl in readme_lines[:3]:
                lines.append(f"• {rl[:120]}")
        elif not desc:
            lines.append("• (README 없음)")
        lines.append(f"🔗 https://github.com/{repo}\n")

    send_telegram("\n".join(lines))

# ── 상태 저장 ─────────────────────────────────
with open(STATE_FILE, "w") as f:
    json.dump(today_list, f, indent=2)
print("완료.")
