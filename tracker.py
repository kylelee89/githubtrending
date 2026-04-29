import os, json, requests
from bs4 import BeautifulSoup
from datetime import datetime

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
STATE_FILE = "previous_repos.json"

def fetch_trendshift():
    url = "https://trendshift.io/github-trending-repositories?trending-range=30&trending-limit=50"
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    repos, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip().rstrip("/")
        if "github.com/" in href:
            path = href.split("github.com/")[-1]
            parts = [p for p in path.split("/") if p]
            if len(parts) >= 2:
                key = f"{parts[0]}/{parts[1]}"
                if key not in seen:
                    seen.add(key)
                    repos.append(key)
    return repos

def get_repo_info(repo):
    r = requests.get(
        f"https://api.github.com/repos/{repo}",
        headers={"Accept": "application/vnd.github.v3+json"},
        timeout=10
    )
    if r.status_code == 200:
        d = r.json()
        return d.get("description") or "", d.get("language") or "N/A", d.get("stargazers_count", 0), d.get("topics", [])
    return "", "N/A", 0, []

def get_readme(repo):
    try:
        r = requests.get(f"https://raw.githubusercontent.com/{repo}/HEAD/README.md", timeout=10)
        return r.text[:1500] if r.status_code == 200 else ""
    except:
        return ""

def send_telegram(text):
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": chunk},
            timeout=10
        )
        print("Telegram:", r.status_code)

# Load previous state
prev = []
if os.path.exists(STATE_FILE):
    with open(STATE_FILE) as f:
        prev = json.load(f)
print(f"Previous repos: {len(prev)}")

# Fetch today
today = fetch_trendshift()
print(f"Today repos: {len(today)}")

# Find new ones (first run = send all)
new_repos = today if not prev else [r for r in today if r not in prev]
print(f"New repos: {len(new_repos)}")

if not new_repos:
    send_telegram("📊 오늘은 새로운 트렌딩 레포가 없습니다.")
else:
    lines = [
        f"🔥 새 깃허브 트렌딩 {datetime.now().strftime('%Y-%m-%d')}",
        f"총 {len(new_repos)}개 신규 등장\n"
    ]
    for i, repo in enumerate(new_repos[:15], 1):
        desc, lang, stars, topics = get_repo_info(repo)
        if not desc:
            readme = get_readme(repo)
            desc = readme[:120].replace("\n", " ") if readme else "설명 없음"
        lines.append(f"{i}. {repo} (⭐{stars:,} | {lang})")
        lines.append(f"• {desc[:120]}")
        if topics:
            lines.append(f"• 태그: {', '.join(topics[:4])}")
        else:
            lines.append(f"• 주요 언어: {lang}")
        lines.append(f"• 스타: {stars:,}개")
        lines.append(f"https://github.com/{repo}\n")
    send_telegram("\n".join(lines))

# Save state
with open(STATE_FILE, "w") as f:
    json.dump(today, f)
print("State saved.")
