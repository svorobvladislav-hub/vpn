import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import socket
import time
from urllib.parse import parse_qs, unquote, urlparse
import requests

# Настройки твоего Gist
GIST_ID = "70d5a02e3bb23a4ffb1b8fb27912c241"
FILENAME = "verified.txt.base64"
GITHUB_TOKEN = os.getenv("GIST_PAT")

# Крупные обновляемые базы ключей
SOURCES = [
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/All_Configs_Sub.txt",
    "https://raw.githubusercontent.com/yebekhe/TVC/main/subscriptions/xray/base64",
    "https://raw.githubusercontent.com/NiREvil/vless/main/sub/link",
    "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Esub/VLESS",
    "https://raw.githubusercontent.com/peasoft/OpenNet/main/vless",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/All_Configs_Sub.txt",
]

# Фильтр популярных стран (ищем по флагам, кодам и названиям в имени узла)
POPULAR_COUNTRIES = {
    "NL": ("🇳🇱", "NL", "NETHERLANDS", "AMSTERDAM"),
    "DE": ("🇩🇪", "DE", "GERMANY", "FRANKFURT", "FALKENSTEIN"),
    "FI": ("🇫🇮", "FI", "FINLAND", "HELSINKI"),
    "CH": ("🇨🇭", "CH", "SWITZERLAND", "ZURICH"),
    "US": ("🇺🇸", "US", "USA", "UNITED STATES"),
    "GB": ("🇬🇧", "GB", "UK", "UNITED KINGDOM", "LONDON"),
    "FR": ("🇫🇷", "FR", "FRANCE", "PARIS"),
    "PL": ("🇵🇱", "PL", "POLAND", "WARSAW"),
    "TR": ("🇹🇷", "TR", "TURKEY", "ISTANBUL"),
    "SE": ("🇸🇪", "SE", "SWEDEN", "STOCKHOLM"),
}


def decode_if_base64(text):
  text = text.strip()
  if "vless://" in text or "trojan://" in text or "ss://" in text:
    return text
  try:
    pad = len(text) % 4
    if pad:
      text += "=" * (4 - pad)
    return base64.b64decode(text).decode("utf-8", errors="ignore")
  except Exception:
    return text


def detect_country(remark):
  """Определяет страну по названию ключа. Если не популярная — возвращает None."""
  remark_upper = unquote(remark).upper()
  for code, keywords in POPULAR_COUNTRIES.items():
    for kw in keywords:
      if kw in remark_upper:
        flag = keywords[0]
        return f"{flag} {code}"
  return None


def parse_and_filter(line):
  """Разбирает ссылку, проверяет протокол и страну, вытаскивает host и port."""
  line = line.strip()
  if not line.startswith(("vless://", "trojan://")):
    return None

  try:
    parsed = urlparse(line)
    if not parsed.hostname or not parsed.port:
      return None

    # Отсеиваем заведомо сломанные или локальные адреса
    if parsed.hostname in ("127.0.0.1", "localhost", "0.0.0.0"):
      return None

    country_tag = detect_country(parsed.fragment)
    if not country_tag:
      return None

    # Оставляем базовую часть ссылки без старого названия (#...)
    clean_uri = line.split("#")[0]
    return {
        "uri": clean_uri,
        "host": parsed.hostname,
        "port": int(parsed.port),
        "country": country_tag,
    }
  except Exception:
    return None


def check_node_alive(node):
  """Проверяет реальный TCP-отклик сервера с жестким таймаутом 0.8 сек."""
  start = time.time()
  try:
    with socket.create_connection((node["host"], node["port"]), timeout=0.8):
      ping = int((time.time() - start) * 1000)
      node["ping"] = ping
      return node
  except Exception:
    return None


def gather_candidates():
  raw_lines = []
  for url in SOURCES:
    try:
      resp = requests.get(url, timeout=10)
      if resp.status_code == 200:
        content = decode_if_base64(resp.text)
        raw_lines.extend(content.splitlines())
    except Exception as e:
      print(f"Пропуск источника {url}: {e}")

  candidates = {}
  for line in raw_lines:
    item = parse_and_filter(line)
    if item:
      # Убираем дубликаты по связке хост:порт
      key = f"{item['host']}:{item['port']}"
      if key not in candidates:
        candidates[key] = item

  return list(candidates.values())


def update_gist(b64_content):
  if not GITHUB_TOKEN:
    print("Ошибка: не задан GIST_PAT в Secrets!")
    return
  url = f"https://api.github.com/gists/{GIST_ID}"
  headers = {
      "Authorization": f"token {GITHUB_TOKEN}",
      "Accept": "application/vnd.github+json",
  }
  payload = {"files": {FILENAME: {"content": b64_content}}}
  r = requests.patch(url, json=payload, headers=headers, timeout=15)
  if r.status_code == 200:
    print(">>> Gist успешно обновлен! Все серверы живые и готовы к бою.")
  else:
    print(f"Ошибка API Gist ({r.status_code}): {r.text}")


if __name__ == "__main__":
  print("1. Сбор и фильтрация по популярным странам...")
  nodes = gather_candidates()
  print(f"Найдено кандидатов нужных стран: {len(nodes)}")

  # Ограничиваем пул для быстрой проверки (до 600 свежих кандидатов за раз)
  nodes = nodes[:600]

  print("2. Запуск параллельного TCP-теста на живучесть (50 потоков)...")
  alive_nodes = []
  with ThreadPoolExecutor(max_workers=50) as executor:
    futures = [executor.submit(check_node_alive, n) for n in nodes]
    for f in as_completed(futures):
      res = f.result()
      if res:
        alive_nodes.append(res)

  print(f"Прошли жесткий отбор (живые): {len(alive_nodes)}")

  if alive_nodes:
    # Сортируем по пингу (самые быстрые в самом верху списка)
    alive_nodes.sort(key=lambda x: x["ping"])

    # Берем ТОП-80 самых быстрых серверов, чтобы не перегружать клиент
    top_nodes = alive_nodes[:80]

    final_links = []
    for idx, n in enumerate(top_nodes, 1):
      # Формируем красивое имя: 🇩🇪 DE | Next VPN #1 ⚡ 35ms
      name = f"{n['country']} | Next VPN #{idx} ⚡ {n['ping']}ms"
      final_links.append(f"{n['uri']}#{name}")

    raw_sub = "\n".join(final_links)
    b64_sub = base64.b64encode(raw_sub.encode("utf-8")).decode("utf-8")
    update_gist(b64_sub)
  else:
    print("Ни один сервер не прошел проверку, оставляем старый список.")
