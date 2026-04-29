import os, json, requests, re, base64
from datetime import datetime, timedelta
from urllib.parse import quote

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
GH_TOKEN = os.environ.get("GH_TOKEN", "")
STATE_FILE = "previous_repos.json"

GH_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"token {GH_TOKEN}" if GH_TOKEN else ""
}

def translate_ko(text):
    if not text or not text.strip():
        return text
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": text[:500]}
        r = requests.get(url, params=params, timeout=10)
        result = r.json()
        return "".join(part[0] for part in result[0] if part[0])
    except:
        return text

def fetch_trending_top50():
    since = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    url = f"https://api.github.com/search/repositories?q=created:>{since}&sort=stars&order=desc&per_page=50"
    r = requests.get(url, headers=GH_HEADERS, timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    return [item["full_name"] for item in items], {item["full_name"]: item for item in items}

def clean_md(text):
    text = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
    text = re.sub(r"^\s*[-*>|]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def get_readme_sentences(full_name):
    try:
        r = requests.get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers=GH_HEADERS, timeout=10
        )
        if r.status_code != 200:
            return []
        raw = base64.b64decode(r.json()["content"]).decode("utf-8", errors="ignore")
        text = clean_md(raw)
        sentences = []
        for line in text.split("\n"):
            line = line.strip()
            if len(line) < 30:
                continue
            if re.search(r"https?://|copyright|license|install|npm |pip |cargo |brew |<[a-z]", line, re.I):
                continue
            sentences.append(line)
            if len(sentences) >= 5:
                break
        return sentences
    except:
        return []

def make_summary(desc, readme_lines):
    """설명 + README에서 3줄 핵심 추출 후 번역"""
    sources = []
    if desc:
        sources.append(desc)
    for line in readme_lines:
        if line not in sources:
            sources.append(line)
    # 3줄 뽑기
    result = []
    for src in sources[:3]:
        ko = translate_ko(src[:300])
        result.append(ko[:100])
    # 3줄 못 채우면 채우기
    while len(result) < 3:
        result.append("(정보 없음)")
    return result

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": chunk}, timeout=15)
        print(f"Telegram: {r.status_code}")

# ── 이전 상태 로드 ──
prev = []
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        prev = json.load(f)
print(f"이전 TOP50: {len(prev)}개")

# ── 오늘 TOP50 ──
today_list, today_info = fetch_trending_top50()
print(f"오늘 TOP50: {len(today_list)}개")

# ── 신규 진입 ──
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
        readme_lines = get_readme_sentences(repo)
        summary = make_summary(desc, readme_lines)

        lines.append(f"{'─'*28}")
        lines.append(f"{i}. {repo}")
        lines.append(f"⭐ {stars:,}  🍴 {forks:,}  {lang}  📅 {created}")
        if topics:
            lines.append(f"🏷 {' · '.join(topics[:5])}")
        lines.append("")
        for j, s in enumerate(summary, 1):
            lines.append(f"{j}) {s}")
        lines.append(f"🔗 https://github.com/{repo}\n")

    send_telegram("\n".join(lines))

# ── 상태 저장 ──
with open(STATE_FILE, "w") as f:
    json.dump(today_list, f, indent=2)
print("완료.")
