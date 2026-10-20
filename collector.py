import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import socket
import time
from urllib.parse import unquote, urlparse
import requests

GIST_ID = "70d5a02e3bb23a4ffb1b8fb27912c241"
FILENAME = "verified.txt.base64"
GITHUB_TOKEN = os.getenv("GIST_PAT")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# Проверенные стабильные источники с прямыми нодами
SOURCES = [
    "https://raw.githubusercontent.com/vless-nodes/vless/main/sub",
    "https://raw.githubusercontent.com/peasoft/OpenNet/main/vless",
    "https://raw.githubusercontent.com/freefq/free/master/vless",
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/All_Configs_Sub.txt",
    "https://raw.githubusercontent.com/aiboboxx/v2rayfree/main/v2",
]

POPULAR_COUNTRIES = {
    "NL": ("🇳🇱", "NL", "NETHERLANDS", "AMSTERDAM"),
    "DE": ("🇩🇪", "DE", "GERMANY", "FRANKFURT"),
    "FI": ("🇫🇮", "FI", "FINLAND", "HELSINKI"),
    "CH": ("🇨🇭", "CH", "SWITZERLAND", "ZURICH"),
    "US": ("🇺🇸", "US", "USA", "UNITED STATES"),
    "GB": ("🇬🇧", "GB", "UK", "UNITED KINGDOM", "LONDON"),
    "FR": ("🇫🇷", "FR", "FRANCE", "PARIS"),
    "PL": ("🇵🇱", "PL", "POLAND"),
    "SE": ("🇸🇪", "SE", "SWEDEN"),
    "TR": ("🇹🇷", "TR", "TURKEY"),
}


def decode_data(text):
  text = text.strip()
  if "vless://" in text or "trojan://" in text:
    return text
  try:
    pad = len(text) % 4
    if pad:
      text += "=" * (4 - pad)
    return base64.b64decode(text).decode("utf-8", errors="ignore")
  except Exception:
    return text


def detect_country(remark):
  remark_upper = unquote(remark).upper()
  for code, keywords in POPULAR_COUNTRIES.items():
    for kw in keywords:
      if kw in remark_upper:
        return f"{keywords[0]} {code}"
  return None


def parse_line(line):
  line = line.strip()
  if not line.startswith(("vless://", "trojan://")):
    return None

  try:
    parsed = urlparse(line)
    if (
        not parsed.hostname
        or not parsed.port
        or parsed.hostname in ("127.0.0.1", "localhost")
    ):
      return None

    country_tag = detect_country(parsed.fragment) or "🌍 Global"
    clean_uri = line.split("#")[0]

    return {
        "uri": clean_uri,
        "host": parsed.hostname,
        "port": int(parsed.port),
        "country": country_tag,
    }
  except Exception:
    return None


def check_node(node):
  start = time.time()
  try:
    with socket.create_connection((node["host"], node["port"]), timeout=1.0):
      node["ping"] = int((time.time() - start) * 1000)
      return node
  except Exception:
    return None


def collect_nodes():
  raw_lines = []
  for url in SOURCES:
    try:
      resp = requests.get(url, headers=HEADERS, timeout=12)
      if resp.status_code == 200 and resp.text.strip():
        content = decode_data(resp.text)
        raw_lines.extend(content.splitlines())
        print(f"Успешно получен источник: {url}")
      else:
        print(f"Источник вернул код {resp.status_code}: {url}")
    except Exception as e:
      print(f"Ошибка источника {url}: {e}")

  parsed_nodes = {}
  for line in raw_lines:
    item = parse_line(line)
    if item:
      key = f"{item['host']}:{item['port']}"
      if key not in parsed_nodes:
        parsed_nodes[key] = item

  return list(parsed_nodes.values())


def update_gist(content):
  if not GITHUB_TOKEN:
    print("Ошибка: GIST_PAT пустой! Проверь Secrets репозитория.")
    return

  url = f"https://api.github.com/gists/{GIST_ID}"
  headers = {
      "Authorization": f"token {GITHUB_TOKEN}",
      "Accept": "application/vnd.github+json",
  }
  payload = {"files": {FILENAME: {"content": content}}}

  r = requests.patch(url, json=payload, headers=headers, timeout=15)
  if r.status_code == 200:
    print(">>> Gist успешно обновлен проверенными нодами!")
  else:
    print(f"Ошибка Gist API ({r.status_code}): {r.text}")


if __name__ == "__main__":
  nodes = collect_nodes()
  print(f"Всего спарсено уникальных кандидатов: {len(nodes)}")

  if not nodes:
    print("Кандидаты не найдены.")
    exit(0)

  # Проверяем первые 300 серверов в 40 потоков
  alive = []
  with ThreadPoolExecutor(max_workers=40) as executor:
    futures = [executor.submit(check_node, n) for n in nodes[:300]]
    for f in as_completed(futures):
      res = f.result()
      if res:
        alive.append(res)

  print(f"Живых серверов после проверки отклика: {len(alive)}")

  if alive:
    alive.sort(key=lambda x: x["ping"])
    top = alive[:60]

    out_lines = [
        f"{n['uri']}#{n['country']} | Next VPN #{i} ⚡ {n['ping']}ms"
        for i, n in enumerate(top, 1)
    ]

    raw_text = "\n".join(out_lines)
    b64_res = base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")
    update_gist(b64_res)
