import os
import time
import threading
import requests
from bs4 import BeautifulSoup
from http.server import SimpleHTTPRequestHandler, HTTPServer

# ─── 【設定部分】 ───
URL = "https://toreca-ace.com"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
# ─────────────────────

LAST_PRODUCT_COUNT = 0

def get_product_count():
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(URL, headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        products = soup.find_all("a", string="詳しく見る")
        return len(products)
    except Exception as e:
        print(f"データ取得エラー: {e}")
        return None

def check_website():
    global LAST_PRODUCT_COUNT
    current_count = get_product_count()
    if current_count is None:
        return
    if LAST_PRODUCT_COUNT == 0:
        LAST_PRODUCT_COUNT = current_count
        print(f"【監視スタート】現在の掲載商品数は {current_count} 個です。")
        return
    if current_count > LAST_PRODUCT_COUNT:
        message = f"🚨 【トレカエース】新着BOXの追加（入荷）を検知しました！\n商品数が {LAST_PRODUCT_COUNT}個 から {current_count}個 に増えました！\n確認はこちら：\n{URL}"
        send_discord_notification(message)
        print("💡 新着商品を検知し、Discordへ通知しました。")
    if current_count != LAST_PRODUCT_COUNT:
        LAST_PRODUCT_COUNT = current_count

# 1.分おきの監視をバックグラウンドで回す処理
def monitor_loop():
    while True:
        check_website()
        time.sleep(60)

def send_discord_notification(message):
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)
    except Exception as e:
        print(f"Discord通知エラー: {e}")

# ─── 🚀 【Renderのエラーを消すための仮の窓口処理】 ───
def run_dummy_server():
    # 環境変数からポート（10000）を読み込み、仮のWEBサーバーを立ち上げてRenderを安心させる
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    print(f"Render対策用の仮サーバーをポート {port} で起動しました。")
    server.serve_forever()

if __name__ == "__main__":
    # 見張りプログラムを裏側でスタート
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    send_discord_notification("✅ 【テスト通知】システムは正常に稼働しています！本番の自動監視を継続します。")

    # メインで仮の窓口を起動してRenderに「ポート開いてるよ」とアピールする
    run_dummy_server()
