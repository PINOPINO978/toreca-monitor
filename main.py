import os
import time
import threading
import requests
import hashlib
import random
from bs4 import BeautifulSoup
from http.server import SimpleHTTPRequestHandler, HTTPServer

# ─── 【設定部分】 ───
# あなたが指定した、ポケモン・遊戯王・ワンピースの「box」検索結果URLです
TARGET_URLS = [
    "https://toreca-ace.com",
    "https://toreca-ace.com",
    "https://toreca-ace.com"
]
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
# ─────────────────────

# 各種状態をURLごとに独立して記憶する領域
LAST_PRODUCT_URLS = {url: set() for url in TARGET_URLS}
LAST_AVAILABLE_URLS = {url: set() for url in TARGET_URLS}
LAST_PAGE_HASH = {url: "" for url in TARGET_URLS}
LAST_PRODUCT_DETAILS = {url: {} for url in TARGET_URLS}

def get_page_source(base_url):
    """ショップ側の『古いデータを掴ませるキャッシュ処理』を強制打破する関数"""
    try:
        # 手法④対策：URLの末尾に毎回ランダムな数値を付与し、常に最新の生データを強制取得
        cache_buster = f"&t={random.randint(100000, 999999)}"
        target_url = base_url + cache_buster
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "ja,jp;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        res = requests.get(target_url, headers=headers, timeout=15)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print(f"ネットワーク取得エラー ({base_url[:40]}...): {e}")
        return None

def check_single_url(url, label):
    """1つずつのURLに対し、ミリ秒単位の変更すら逃さない5重センサー検査ロジック"""
    global LAST_PRODUCT_URLS, LAST_AVAILABLE_URLS, LAST_PAGE_HASH, LAST_PRODUCT_DETAILS
    
    html_content = get_page_source(url)
    if not html_content:
        return

    soup = BeautifulSoup(html_content, "html.parser")
    
    # 手法⑤対策：ページ全体の文字列をハッシュ化し、デザイン変更や文字のわずかな改ざんを検知
    current_text = soup.get_text()
    current_hash = hashlib.md5(current_text.encode('utf-8')).hexdigest()
    
    current_product_urls = set()
    current_available_urls = set()
    current_product_details = {} # 今回のページ内にある { 商品URL: "名前や価格" }
    
    # 検索結果の商品ブロック（各aタグ）を徹底走査
    for item in soup.find_all("a", href=True):
        href = item["href"]
        if "/view/item/" in href:
            full_url = f"https://toreca-ace.com{href}" if href.startswith("/") else href
            current_product_urls.add(full_url)
            
            # 商品名、価格、親要素（ボタン周り）のテキストをすべて結合して空白を排除
            item_text = item.get_text()
            parent = item.parent
            parent_text = parent.get_text() if parent else ""
            combined_text = (item_text + parent_text).replace("\n", "").replace(" ", "")
            
            # 今の個別商品の状態（名前や価格）を保存
            current_product_details[full_url] = combined_text
            
            # 手法②対策：在庫切れサイン（売切れ）のチェック
            if "在庫なし" in combined_text.upper() or "売り切れ" in combined_text.upper() or "SOLD" in combined_text.upper():
                continue
                
            # 「在庫なし」の文字がない＝購入可能なURLを保存
            current_available_urls.add(full_url)

    # ── 初回起動時のデータ記憶（ここを基準に差分を測る） ──
    if not LAST_PAGE_HASH[url]:
        LAST_PRODUCT_URLS[url] = current_product_urls
        LAST_AVAILABLE_URLS[url] = current_available_urls
        LAST_PRODUCT_DETAILS[url] = current_product_details
        LAST_PAGE_HASH[url] = current_hash
        print(f"【超精密監視開始: {label}】全 {len(current_product_urls)} 件中、即購入可能: {len(current_available_urls)} 件")
        return

    # ── 🚨 判定ロジック（多重自動センサー群） ──
    alert_triggered = False
    reasons = []
    alert_urls = set()
    
    # センサー①: 新しいURLが増えた（通常の新BOX登場）
    new_urls = current_product_urls - LAST_PRODUCT_URLS[url]
    if new_urls:
        alert_triggered = True
        reasons.append(f"📦 完全新規の商品URLが検索結果に追加されました！")
        alert_urls.update(new_urls)

    # センサー②: 在庫ありURLが増えた（売切れからカートが復活）
    new_instock = current_available_urls - LAST_AVAILABLE_URLS[url]
    if new_instock:
        alert_triggered = True
        reasons.append(f"🔥 在庫切れだったBOXのカートボタンが復活しました！")
        alert_urls.update(new_instock)

    # センサー③: 手法③（フランキーすり替え）対策！既存のページの文字（名前や価格）が書き換わったか？
    for p_url, p_text in current_product_details.items():
        if p_url in LAST_PRODUCT_DETAILS[url]:
            if p_text != LAST_PRODUCT_DETAILS[url][p_url]:
                alert_triggered = True
                reasons.append(f"⚡ 既存の商品ページ（カモフラージュ等）の内容・価格の書き換えを検知しました！")
                alert_urls.add(p_url)

    # センサー④: その他、ページ全体の文字データ改ざん対策
    if current_hash != LAST_PAGE_HASH[url] and not alert_triggered:
        alert_triggered = True
        reasons.append(f"⚠️ 警告：詳細不明ですが、ページ内の表示データ全体に変革を検知しました！")
        alert_urls.add(url)

    # ── 📢 Discord通知処理 ──
    if alert_triggered:
        print(f"💡 [{label}] で変更検知：{', '.join(reasons)}")
        
        # 理由の重複を除去
        unique_reasons = list(set(reasons))
        
        for link in alert_urls:
            message = (
                f"🚨 ── 【トレカエース・全手法突破検知（{label}）】 ── 🚨\n"
                f"検知理由: { ' / '.join(unique_reasons) }\n\n"
                f"大至急、こちらから確認してください！中身がBOXに化けているか、再販が始まっています！\n"
                f"👉 {link}"
            )
            send_discord_notification(message)
            
        # 状態を完全同期して次回に備える
        LAST_PRODUCT_URLS[url] = current_product_urls
        LAST_AVAILABLE_URLS[url] = current_available_urls
        LAST_PRODUCT_DETAILS[url] = current_product_details
        LAST_PAGE_HASH[url] = current_hash
    else:
        # 変動がなくても最新の状態を常に同期（微細なズレを防ぐため）
        LAST_PRODUCT_DETAILS[url] = current_product_details
        LAST_PAGE_HASH[url] = current_hash

def monitor_loop():
    """3つのURLを順番に、かつ安全にスキャンするメインループ（全体で約1分周期）"""
    labels = ["ポケモンカード", "遊戯王", "ワンピース"]
    while True:
        for url, label in zip(TARGET_URLS, labels):
            check_single_url(url, label)
            time.sleep(2) # サイトへの過度な負荷（アクセス拒否）を防ぐために2秒の休憩
        
        # 次の全体定期スキャンまで50秒待機
        time.sleep(50)

def send_discord_notification(message):
    if not DISCORD_WEBHOOK_URL:
        print("Discord Webhook URLが未設定です。")
        return
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)
    except Exception as e:
        print(f"Discord通知エラー: {e}")

# ─── 🚀 Render無料プラン専用：スリープ（休止）強制解除システム ───
def keep_alive_loop(port):
    """5分間アクセスがないとサーバーごと眠るRenderの仕様を、3分半ごとのセルフノックで防ぐ"""
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
    print(f"Render用マルチ完全防御監視サーバー（ポート {port}）を起動しました。")
    server.serve_forever()

if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    run_dummy_server()
