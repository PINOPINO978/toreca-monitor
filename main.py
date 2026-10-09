import os
import time
import threading
import requests
import hashlib
import random
from bs4 import BeautifulSoup
from http.server import SimpleHTTPRequestHandler, HTTPServer

# ─── 【設定部分】 ───
TARGET_URLS = [
    "https://toreca-ace.com",
    "https://toreca-ace.com",
    "https://toreca-ace.com"
]
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
# ─────────────────────

LAST_PRODUCT_URLS = {url: set() for url in TARGET_URLS}
LAST_AVAILABLE_URLS = {url: set() for url in TARGET_URLS}
LAST_PAGE_HASH = {url: "" for url in TARGET_URLS}
LAST_PRODUCT_DETAILS = {url: {} for url in TARGET_URLS}

def get_page_source(base_url):
    try:
        cache_buster = f"&t={random.randint(100000, 999999)}"
        target_url = base_url + cache_buster
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "ja,jp;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache"
        }
        res = requests.get(target_url, headers=headers, timeout=15)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print(f"ネットワーク取得エラー: {e}")
        return None

def check_single_url(url, label):
    global LAST_PRODUCT_URLS, LAST_AVAILABLE_URLS, LAST_PAGE_HASH, LAST_PRODUCT_DETAILS
    
    html_content = get_page_source(url)
    if not html_content:
        return

    soup = BeautifulSoup(html_content, "html.parser")
    
    current_text = soup.get_text()
    current_hash = hashlib.md5(current_text.encode('utf-8')).hexdigest()
    
    current_product_urls = set()
    current_available_urls = set()
    current_product_details = {}
    
    for item in soup.find_all("a", href=True):
        href = item["href"]
        if "/view/item/" in href:
            full_url = f"https://toreca-ace.com{href}" if href.startswith("/") else href
            current_product_urls.add(full_url)
            
            item_text = item.get_text()
            parent = item.parent
            parent_text = parent.get_text() if parent else ""
            combined_text = (item_text + parent_text).replace("\n", "").replace(" ", "")
            
            current_product_details[full_url] = combined_text
            
            if "在庫なし" in combined_text.upper() or "売り切れ" in combined_text.upper() or "SOLD" in combined_text.upper():
                continue
                
            current_available_urls.add(full_url)

    if not LAST_PAGE_HASH[url]:
        LAST_PRODUCT_URLS[url] = current_product_urls
        LAST_AVAILABLE_URLS[url] = current_available_urls
        LAST_PRODUCT_DETAILS[url] = current_product_details
        LAST_PAGE_HASH[url] = current_hash
        print(f"【超精密監視開始: {label}】全 {len(current_product_urls)} 件、即購入可能: {len(current_available_urls)} 件", flush=True)
        return

    alert_triggered = False
    reasons = []
    alert_urls = set()
    
    if current_product_urls - LAST_PRODUCT_URLS[url]:
        alert_triggered = True
        reasons.append("📦 完全新規の商品URLが検索結果に追加されました！")
        alert_urls.update(current_product_urls - LAST_PRODUCT_URLS[url])

    if current_available_urls - LAST_AVAILABLE_URLS[url]:
        alert_triggered = True
        reasons.append("🔥 在庫切れだったBOXのカートボタンが復活しました！")
        alert_urls.update(current_available_urls - LAST_AVAILABLE_URLS[url])

    for p_url, p_text in current_product_details.items():
        if p_url in LAST_PRODUCT_DETAILS[url] and p_text != LAST_PRODUCT_DETAILS[url][p_url]:
            alert_triggered = True
            reasons.append("⚡ 既存ページの内容・価格の書き換えを検知しました！")
            alert_urls.add(p_url)

    if current_hash != LAST_PAGE_HASH[url] and not alert_triggered:
        alert_triggered = True
        reasons.append("⚠️ 警告：ページ内の表示データ全体に変革を検知しました！")
        alert_urls.add(url)

    if alert_triggered:
        print(f"💡 [{label}] で変更検知：{', '.join(reasons)}", flush=True)
        for link in alert_urls:
            message = (
                f"🚨 ── 【トレカエース・ゲリラ更新検知（{label}）】 ── 🚨\n"
                f"理由: { ' / '.join(list(set(reasons))) }\n\n"
                f"確認はこちら：\n👉 {link}"
            )
            send_discord_notification(message)
            
        LAST_PRODUCT_URLS[url] = current_product_urls
        LAST_AVAILABLE_URLS[url] = current_available_urls
        LAST_PRODUCT_DETAILS[url] = current_product_details
        LAST_PAGE_HASH[url] = current_hash
    else:
        LAST_PRODUCT_DETAILS[url] = current_product_details
        LAST_PAGE_HASH[url] = current_hash

def monitor_loop():
    labels = ["ポケモンカード", "遊戯王", "ワンピース"]
    
    # 🚀【新規追加】起動時に1回だけ、Discordへ「正しく繋がったよ」とテスト通知を送る
    test_message = "✅ 【トレカエース監視システム】RenderとDiscordの連携に成功しました！24時間フル監視を開始します。"
    send_discord_notification(test_message)
    print("💡 Discordへテスト起動通知を送信しました。", flush=True)

    while True:
        for url, label in zip(TARGET_URLS, labels):
            check_single_url(url, label)
            time.sleep(2)
        time.sleep(50)

def send_discord_notification(message):
    if not DISCORD_WEBHOOK_URL:
        print("Discord Webhook URLが未設定です。", flush=True)
        return
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)
    except Exception as e:
        print(f"Discord通知エラー: {e}", flush=True)

def keep_alive_loop(port):
    time.sleep(20)
    while True:
        try:
            requests.get(f"http://127.0.0.1:{port}", timeout=5)
        except Exception:
            pass
        time.sleep(210)

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    ka_thread = threading.Thread(target=keep_alive_loop, args=(port,), daemon=True)
    ka_thread.start()
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    print(f"Render用仮サーバー（ポート {port}）を起動しました。", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    run_dummy_server()
