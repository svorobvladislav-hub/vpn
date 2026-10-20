import base64
import os
import re
import requests

# ID твоего Gist и имя файла
GIST_ID = "70d5a02e3bb23a4ffb1b8fb27912c241"
FILENAME = "verified.txt.base64"
GITHUB_TOKEN = os.getenv("GIST_PAT")

# Список топовых публичных агрегаторов (ALL VPN источники)
SOURCES = [
    # Чистые VLESS / V2Ray ноды
    "https://raw.githubusercontent.com/peasoft/OpenNet/main/vless",
    "https://raw.githubusercontent.com/mahdibland/ShadowsocksAggregator/master/Esub/VLESS",
    "https://raw.githubusercontent.com/freefq/free/master/vless",
    "https://raw.githubusercontent.com/NiREvil/vless/main/sub/link",
    "https://raw.githubusercontent.com/barry-far/V2ray-Configs/main/All_Configs_Sub.txt",
    # Мощные Base64-подписки (автоматически декодируются ниже)
    "https://raw.githubusercontent.com/yebekhe/TVC/main/subscriptions/xray/base64",
    "https://raw.githubusercontent.com/MrMohebi/xray-proxy-grabber/main/sub/base64",
]

# Разрешенные протоколы
VALID_PROTOCOLS = ("vless://", "vmess://", "trojan://", "ss://")


def decode_base64_content(text):
  """Декодирует текст, если источник отдает данные в Base64."""
  text = text.strip()
  try:
    # Добавляем недостающий padding если нужно
    missing_padding = len(text) % 4
    if missing_padding:
      text += "=" * (4 - missing_padding)
    decoded = base64.b64decode(text).decode("utf-8", errors="ignore")
    return decoded
  except Exception:
    return text


def fetch_nodes():
  """Сбирает и фильтрует все доступные ноды из источников."""
  nodes = []

  for url in SOURCES:
    try:
      print(f"Скачиваем источники из: {url}")
      resp = requests.get(url, timeout=12)
      if resp.status_code == 200:
        content = resp.text

        # Если содержимое закодировано в Base64 — пробуем расшифровать
        if not any(proto in content for proto in VALID_PROTOCOLS):
          content = decode_base64_content(content)

        # Парсим каждую строчку
        lines = content.splitlines()
        for line in lines:
          line = line.strip()
          if line.startswith(VALID_PROTOCOLS):
            nodes.append(line)
    except Exception as e:
      print(f"Ошибка при обработке {url}: {e}")

  # Удаляем дубликаты с сохранением порядка
  unique_nodes = list(dict.fromkeys(nodes))
  return unique_nodes


def update_gist(content_base64):
  """Отправляет обновленный Base64 файл в GitHub Gist по API."""
  if not GITHUB_TOKEN:
    print(" Ошибка: Переменная GIST_PAT не найдена в Secrets репозитория!")
    return

  headers = {
      "Authorization": f"token {GITHUB_TOKEN}",
      "Accept": "application/vnd.github+json",
  }
  data = {"files": {FILENAME: {"content": content_base64}}}
  url = f"https://api.github.com/gists/{GIST_ID}"

  res = requests.patch(url, json=data, headers=headers)
  if res.status_code == 200:
    print(" Gist успешно обновлен свежими нодами ALL VPN!")
  else:
    print(f" Ошибка обновления Gist ({res.status_code}): {res.text}")


if __name__ == "__main__":
  print("=== Запуск автосборщика ALL VPN ===")
  all_nodes = fetch_nodes()
  print(f"\n Всего найдено уникальных рабочих нод: {len(all_nodes)}")

  if all_nodes:
    # Объединяем ноды переводом строки
    raw_text = "\n".join(all_nodes)

    # Кодируем весь итоговый список обратно в единый Base64
    b64_encoded = base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")

    # Обновляем файл в Gist
    update_gist(b64_encoded)
  else:
    print(" Не удалось собрать ноды из указанных источников.")
