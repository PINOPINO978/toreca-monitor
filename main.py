import os
import time
import threading
import requests
from bs4 import BeautifulSoup
from http.server import SimpleHTTPRequestHandler, HTTPServer

# ─── 【設定部分】 ───
TARGET_SITES = {
    "ポケカBOX一覧": "https://toreca-ace.com",
    "ワンピースBOX一覧": "https://toreca-ace.com",
    "遊戯王BOX一覧": "https://toreca-ace.com"
}
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
# ─────────────────────

LAST_TEXTS = {name: "" for name in TARGET_SITES.keys()}

def get_page_text(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        main_content = soup.find("main")
        if not main_content:
            main_content = soup.find("body")
            
        return " ".join(main_content.get_text().split())
    except Exception as e:
        print(f"❌ データ取得エラー ({url}): {e}")
        return None

def check_websites():
    global LAST_TEXTS
    
    for name, url in TARGET_SITES.items():
        current_text = get_page_text(url)
        
        if not current_text:
            print(f"⚠️ 【{name}】のページデータの取得に失敗したため、この回はスキップします。")
            continue
            
        # 初回起動時
        if LAST_TEXTS[name] == "":
            LAST_TEXTS[name] = current_text
            print(f"🚀 【{name}】の文字書き換え監視をスタートしました。")
            send_discord_notification(f"✅ 【監視スタート】{name} の文字監視（在庫復活チェック）を開始しました！\nURL: {url}")
            continue
            
        # 1分前と比べてページ内の文字が書き換えられた場合（バグ修正済）
        if current_text != LAST_TEXTS[name]:
            message = (
                f"🚨 【トレカエース】{name} のページが書き換えられました（入荷・在庫復活の可能性大）！\n"
                f"売り切れ表示が消えてカートに入れられる状態になった可能性があります！\n"
                f"大至急、ページを確認してください：\n{url}"
            )
            send_discord_notification(message)
            print(f"💡 【{name}】のページ書き換え（変更）を検知し、Discordへ通知を飛ばしました！")
            LAST_TEXTS[name] = current_text
        else:
            print(f"⏰ 【定期チェック】{name}: 変化なし（ページ書き換えなし）")

def monitor_loop():
    while True:
        check_websites()
        time.sleep(60)

def send_discord_notification(message):
    if not DISCORD_WEBHOOK_URL:
        print("❌ DiscordのWebhook URLが環境変数に設定されていません。")
        return
    data = {"content": message}
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)
        print(f"📮 Discord送信ステータス: {res.status_code}")
    except Exception as e:
        print(f"❌ Discord通知エラー: {e}")

def keep_alive_loop(port):
    time.sleep(20)
    while True:
        try:
            requests.get(f"http://127.0.0.1:{port}", timeout=5)
        except Exception:
            pass
        time.sleep(180)

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    ka_thread = threading.Thread(target=keep_alive_loop, args=(port,), daemon=True)
    ka_thread.start()
    
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    print(f"💻 Render用ダミーサーバー起動（ポート: {port}）")
    server.serve_forever()

if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    run_dummy_server()
