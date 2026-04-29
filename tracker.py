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
    """최근 30일 내 생성된 레포 중 스타 기준 상위 50개"""
    since = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    url = f"https://api.github.com/search/repositories?q=created:>{since}&sort=stars&order=desc&per_page=50"
    r = requests.get(url, headers=GH_HEADERS, timeout=30)
    r.raise_for_status()
    items = r.json().get("items", [])
    return [item["full_name"] for item in items], {item["full_name"]: item for item in items}

def get_readme_intro(full_name):
    """README에서 첫 번째 의미있는 단락 추출"""
    try:
        r = requests.get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers=GH_HEADERS, timeout=10
        )
        if r.status_code != 200:
            return ""
        content = base64.b64decode(r.json()["content"]).decode("utf-8", errors="ignore")
        # 마크다운 제거 후 첫 단락
        content = re.sub(r"#+\s.*\n", "", content)          # 헤더 제거
        content = re.sub(r"!\[.*?\]\(.*?\)", "", content)    # 이미지 제거
        content = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", content)  # 링크 텍스트만
        content = re.sub(r"`{1,3}[^`]*`{1,3}", "", content)  # 코드 제거
        content = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", content)   # 볼드/이탤릭
        lines = [l.strip() for l in content.split("\n") if l.strip() and len(l.strip()) > 30]
        return " ".join(lines[:3])[:300] if lines else ""
    except:
        return ""

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        r = requests.post(url, json={"chat_id": CHAT_ID, "text": chunk}, timeout=15)
        print(f"Telegram: {r.status_code} ok={r.json().get('ok')}")

# ── 이전 상태 로드 ──────────────────────────────
prev = []
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        prev = json.load(f)
print(f"이전 TOP50: {len(prev)}개")

# ── 오늘 TOP50 가져오기 ─────────────────────────
today_list, today_info = fetch_trending_top50()
print(f"오늘 TOP50: {len(today_list)}개")

# ── 새로 진입한 레포만 추출 ─────────────────────
prev_set = set(prev)
new_repos = [r for r in today_list if r not in prev_set]
print(f"신규 진입: {len(new_repos)}개")

# ── 텔레그램 메시지 ────────────────────────────
if not new_repos:
    send_telegram("📊 오늘은 30일 TOP50에 새로 진입한 레포가 없습니다.")
else:
    today_str = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"🔥 깃허브 30일 트렌딩 신규 진입 {today_str}",
        f"TOP50 중 오늘 새로 들어온 {len(new_repos)}개\n"
    ]

    for i, repo in enumerate(new_repos[:20], 1):
        info = today_info.get(repo, {})
        name = repo.split("/")[1]
        stars = info.get("stargazers_count", 0)
        forks = info.get("forks_count", 0)
        lang = info.get("language") or "N/A"
        desc = info.get("description") or ""
        topics = info.get("topics", [])
        created = info.get("created_at", "")[:10]

        # README 인트로 (설명 없을 때)
        readme = get_readme_intro(repo) if not desc else ""
        summary = desc if desc else readme if readme else "설명 없음"

        lines.append(f"{'─'*30}")
        lines.append(f"{i}. {repo}")
        lines.append(f"⭐ {stars:,}  |  🍴 {forks:,}  |  {lang}  |  생성: {created}")
        if topics:
            lines.append(f"🏷 {' · '.join(topics[:5])}")
        lines.append(f"")
        lines.append(f"📌 {summary[:200]}")
        lines.append(f"🔗 https://github.com/{repo}\n")

    send_telegram("\n".join(lines))

# ── 상태 저장 ─────────────────────────────────
with open(STATE_FILE, "w") as f:
    json.dump(today_list, f, indent=2)
print("상태 저장 완료.")
