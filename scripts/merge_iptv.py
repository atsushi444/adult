import urllib.request
import concurrent.futures
import time
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ========== 配置 ==========
SOURCES_FILE = "sources.txt"
OUTPUT_FILE = "playlist.m3u"
DEAD_FILE = "dead.m3u"
README_FILE = "README.md"

TIMEOUT = 10
MAX_WORKERS = 30
# =========================

def download(url: str) -> str:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; IPTV-Merger/1.2)"}
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[WARN] Download failed: {url} -> {e}")
        return ""

def parse_m3u(content: str):
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    channels = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF"):
            extinf = lines[i]
            i += 1
            if i < len(lines) and not lines[i].startswith("#"):
                url = lines[i]
                channels.append((extinf, url))
        i += 1
    return channels

def is_alive(url: str) -> bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; IPTV-Checker/1.2)",
        "Accept": "*/*",
        "Connection": "close",
    }
    try:
        req = urllib.request.Request(url, method="HEAD", headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if 200 <= resp.getcode() < 400:
                return True
    except Exception:
        pass

    try:
        req = urllib.request.Request(url, method="GET", headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if 200 <= resp.getcode() < 400:
                data = resp.read(1024)
                return len(data) > 0
    except Exception:
        return False
    return False

def main():
    all_channels = []
    seen_urls = set()

    # 1. 从 sources.txt 下载
    if Path(SOURCES_FILE).exists():
        with open(SOURCES_FILE, encoding="utf-8") as f:
            sources = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    else:
        sources = []

    for src in sources:
        print(f"Downloading source: {src}")
        content = download(src)
        if not content:
            continue
        for extinf, stream_url in parse_m3u(content):
            if stream_url not in seen_urls:
                seen_urls.add(stream_url)
                all_channels.append((extinf, stream_url))

    print(f"\nTotal unique channels before check: {len(all_channels)}")

    # 2. 死链检测
    print(f"Starting dead-link check (timeout={TIMEOUT}s, workers={MAX_WORKERS})...")
    start = time.time()

    alive_channels = []
    dead_channels = []

    def check(item):
        extinf, url = item
        return (extinf, url, is_alive(url))

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        results = list(executor.map(check, all_channels))

    for extinf, url, alive in results:
        if alive:
            alive_channels.append((extinf, url))
        else:
            dead_channels.append((extinf, url))

    elapsed = time.time() - start
    print(f"Check finished in {elapsed:.1f}s")
    print(f"Alive: {len(alive_channels)} | Dead: {len(dead_channels)}")

    # 3. 写出文件
    header = "#EXTM3U\n"
    Path(OUTPUT_FILE).write_text(
        header + "\n".join(f"{e}\n{u}" for e, u in alive_channels) + "\n",
        encoding="utf-8"
    )
    print(f"Saved {len(alive_channels)} alive channels → {OUTPUT_FILE}")

    Path(DEAD_FILE).write_text(
        header + "\n".join(f"{e}\n{u}" for e, u in dead_channels) + "\n",
        encoding="utf-8"
    )
    print(f"Saved {len(dead_channels)} dead channels → {DEAD_FILE}")

    # 4. 更新 README
    beijing_tz = timezone(timedelta(hours=8))
    now_beijing = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")

    status_block = f"""<!-- IPTV-STATUS-START -->
## 📊 更新状态

- **最后更新时间**：{now_beijing}（北京时间）
- **存活频道**：{len(alive_channels)}
- **死亡频道**：{len(dead_channels)}
- **播放列表**：[{OUTPUT_FILE}]({OUTPUT_FILE})
- **死链列表**：[{DEAD_FILE}]({DEAD_FILE})
<!-- IPTV-STATUS-END -->
"""

    readme_path = Path(README_FILE)
    if readme_path.exists():
        content = readme_path.read_text(encoding="utf-8")
        pattern = r"<!-- IPTV-STATUS-START -->.*?<!-- IPTV-STATUS-END -->"
        if re.search(pattern, content, flags=re.DOTALL):
            new_content = re.sub(pattern, status_block.strip(), content, flags=re.DOTALL)
        else:
            new_content = status_block + "\n" + content
    else:
        new_content = f"# IPTV Playlist Merger\n\n{status_block}"

    readme_path.write_text(new_content, encoding="utf-8")
    print(f"Updated {README_FILE} with latest status")

if __name__ == "__main__":
    main()
