import os
import time
import json
import random
import threading
import hashlib
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urljoin
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import requests
from bs4 import BeautifulSoup

# ============================================================
# 設定
# ============================================================

TARGETS = [
    {
        "label": "ポケモンカード",
        "url": "https://www.toreca-ace.com/view/category/pokemon-pickup",
    },
    {
        "label": "ワンピース",
        "url": "https://www.toreca-ace.com/view/category/onepiece-pickup",
    },
    {
        "label": "遊戯王",
        "url": "https://www.toreca-ace.com/view/category/yugioh-pickup",
    },
]

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()

CHECK_INTERVAL_SECONDS = 60
REQUEST_GAP_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 20

MIN_PRODUCTS_FOR_VALID_PAGE = 1
SUSPICIOUS_DROP_RATIO = 0.50

DATA_DIR = os.environ.get("DISK_PATH", ".")
STATE_FILE = os.path.join(DATA_DIR, "toreca_monitor_state.json")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

# ============================================================
# 共通処理
# ============================================================

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
})

state_lock = threading.Lock()
monitor_state = {}


def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def send_discord_notification(message):
    if not DISCORD_WEBHOOK_URL:
        log("Discord Webhook URLが未設定のため通知できません。")
        return False

    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": message[:1900]},
            timeout=15,
        )

        if 200 <= response.status_code < 300:
            log(f"Discord通知成功: HTTP {response.status_code}")
            return True

        log(
            f"Discord通知失敗: HTTP {response.status_code} "
            f"本文={response.text[:300]}"
        )
        return False

    except requests.RequestException as exc:
        log(f"Discord通知エラー: {exc}")
        return False


def build_cache_busted_url(url):
    parts = urlsplit(url)
    params = parse_qsl(parts.query, keep_blank_values=True)
    params.append((
        "_monitor_ts",
        str(int(time.time())) + str(random.randint(100, 999))
    ))

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(params),
        parts.fragment,
    ))


def get_page_source(url):
    target_url = build_cache_busted_url(url)

    try:
        response = session.get(
            target_url,
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")

        if "text/html" not in content_type.lower():
            log(f"警告: HTML以外のContent-Typeです: {content_type} ({url})")

        html = response.text

        if not html or len(html.strip()) < 200:
            log(f"取得データが短すぎます。今回の結果は使用しません: {url}")
            return None

        log(
            f"取得成功: HTTP {response.status_code}, "
            f"{len(html)}文字, {url}"
        )

        return html

    except requests.RequestException as exc:
        log(f"ページ取得エラー [{url}]: {exc}")
        return None


def load_state():
    global monitor_state

    try:
        os.makedirs(DATA_DIR, exist_ok=True)

        if not os.path.exists(STATE_FILE):
            monitor_state = {}
            log(f"保存済み監視状態なし。初回起動として開始します: {STATE_FILE}")
            return

        with open(STATE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        monitor_state = data if isinstance(data, dict) else {}
        log(f"監視状態を読み込みました: {STATE_FILE}")

    except Exception as exc:
        monitor_state = {}
        log(f"監視状態の読み込みエラー。初回起動扱いにします: {exc}")


def save_state():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)

        temp_file = STATE_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(
                monitor_state,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(temp_file, STATE_FILE)

    except Exception as exc:
        log(
            f"監視状態の保存エラー: {exc}。"
            "Renderの永続ディスク設定と保存先を確認してください。"
        )


def normalize_text(text):
    return " ".join((text or "").split())


def is_sold_out(text):
    text_upper = (text or "").upper()

    sold_out_terms = [
        "在庫なし",
        "売り切れ",
        "売切れ",
        "SOLD OUT",
        "SOLDOUT",
        "品切れ",
        "在庫切れ",
    ]

    return any(term.upper() in text_upper for term in sold_out_terms)


def extract_products(html, category_url):
    soup = BeautifulSoup(html, "html.parser")
    products = {}

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()

        if "/view/item/" not in href:
            continue

        product_url = urljoin(category_url, href).split("#", 1)[0]

        parts = urlsplit(product_url)
        product_url = urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path.rstrip("/"),
            "",
            ""
        ))

        pieces = []
        current = anchor

        for _ in range(3):
            if current is None:
                break

            text = normalize_text(current.get_text(" ", strip=True))

            if text and text not in pieces:
                pieces.append(text)

            current = current.parent

        combined_text = " | ".join(pieces)

        if not combined_text:
            combined_text = normalize_text(
                anchor.get("aria-label", "")
            )

        if (
            product_url not in products
            or len(combined_text) > len(products[product_url]["text"])
        ):
            products[product_url] = {
                "text": combined_text[:1000],
                "available": not is_sold_out(combined_text),
            }

    page_text = normalize_text(soup.get_text(" ", strip=True))
    page_hash = hashlib.sha256(
        page_text.encode("utf-8")
    ).hexdigest()

    return products, page_hash, len(html), page_text[:300]


def is_suspicious_result(previous_products, current_products, html_length):
    if len(current_products) < MIN_PRODUCTS_FOR_VALID_PAGE:
        return True, (
            f"商品リンクが {len(current_products)} 件のため、"
            "誤取得の可能性を考えて監視状態を更新しません"
        )

    previous_count = len(previous_products)
    current_count = len(current_products)

    if (
        previous_count >= 4
        and current_count < previous_count * SUSPICIOUS_DROP_RATIO
    ):
        return True, (
            f"商品リンク数が {previous_count} 件から {current_count} 件に急減。"
            "誤取得の可能性を考えて監視状態を更新しません"
        )

    return False, ""


def make_alert_message(label, reason, product_url, product_text=""):
    details = (
        f"\n商品情報: {product_text[:500]}"
        if product_text else ""
    )

    return (
        f"🚨 **トレカエース商品監視通知：{label}**\n"
        f"検知内容: {reason}\n"
        f"商品URL: {product_url}"
        f"{details}"
    )


# ============================================================
# 監視処理
# ============================================================

def check_single_target(target):
    label = target["label"]
    category_url = target["url"]
    key = category_url

    html = get_page_source(category_url)

    if html is None:
        return

    (
        current_products,
        page_hash,
        html_length,
        preview
    ) = extract_products(html, category_url)

    log(f"[{label}] 商品リンク {len(current_products)} 件を抽出")

    with state_lock:
        previous = monitor_state.get(key)

        # 初回は基準データを保存し、初回の誤通知を防ぐ
        if not previous:
            monitor_state[key] = {
                "label": label,
                "products": current_products,
                "page_hash": page_hash,
                "updated_at": time.time(),
            }

            save_state()

            log(
                f"[{label}] 初回基準を保存しました。"
                f"商品 {len(current_products)} 件。"
                "初回は商品通知を行いません。"
            )
            return

        previous_products = previous.get("products", {})

        suspicious, reason = is_suspicious_result(
            previous_products,
            current_products,
            html_length
        )

        if suspicious:
            log(f"[{label}] 取得結果を保留: {reason}")

            send_discord_notification(
                f"⚠️ **トレカエース監視の取得異常：{label}**\n"
                f"{reason}\n"
                f"カテゴリ: {category_url}\n"
                f"HTML文字数: {html_length}\n"
                "誤通知防止のため、前回の監視状態は保持しました。"
            )
            return

        old_urls = set(previous_products.keys())
        new_urls = set(current_products.keys())

        added_urls = new_urls - old_urls

        reappeared_urls = {
            url for url in (new_urls & old_urls)
            if current_products[url].get("available", False)
            and not previous_products[url].get("available", False)
        }

        changed_urls = {
            url for url in (new_urls & old_urls)
            if current_products[url].get("text", "")
            != previous_products[url].get("text", "")
        }

        notifications = []

        for product_url in sorted(added_urls):
            product = current_products[product_url]

            notifications.append(make_alert_message(
                label,
                "🆕 新しい商品URLを検知しました",
                product_url,
                product.get("text", ""),
            ))

        for product_url in sorted(reappeared_urls):
  
            product = current_products[product_url]
            notifications.append(make_alert_message(
                label,
                "♻️ 商品の再入荷を検知しました",
                product_url,
                product.get("text", ""),
            ))

        for product_url in sorted(changed_urls):
            product = current_products[product_url]
            notifications.append(make_alert_message(
                label,
                "🔄 商品情報の変更を検知しました",
                product_url,
                product.get("text", ""),
            ))

        for message in notifications:
            sent = send_discord_notification(message)
            if sent:
                log(f"[{label}] Discord通知を送信しました")
            else:
                log(f"[{label}] Discord通知に失敗しました")

        with state_lock:
            monitor_state[key] = {
                "label": label,
                "products": current_products,
                "page_hash": page_hash,
                "updated_at": time.time(),
            }
            save_state()

        log(
            f"[{label}] 監視完了。"
            f"商品数={len(current_products)}、"
            f"新規={len(added_urls)}、"
            f"再入荷={len(reappeared_urls)}、"
            f"変更={len(changed_urls)}"
        )


def monitor_loop():
    log("トレカ監視を開始します")

    while True:
        try:
            for target in TARGETS:
                try:
                    check_single_target(target)
                except Exception as exc:
                    log(f"監視エラー: {exc}")

                time.sleep(2)

        except Exception as exc:
            log(f"監視ループエラー: {exc}")

        time.sleep(CHECK_INTERVAL_SECONDS)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    log(f"ヘルスチェックサーバーを起動しました。port={port}")
    server.serve_forever()


if __name__ == "__main__":
    health_thread = threading.Thread(
        target=start_health_server,
        daemon=True,
    )
    health_thread.start()

    monitor_loop()
