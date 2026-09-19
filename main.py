import time
import requests
from bs4 import BeautifulSoup

# ─── 【設定部分】 ───
URL = "https://toreca-ace.com"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1550863709293903904/Tb-NM-6vtReZaX3HcSPoxrTVyGESzs3FbRrXKd946UGYSYV7udb-vYzYFRDePU6FKCY4"
# ─────────────────────

# 前回確認したときの商品数を保存する変数
LAST_PRODUCT_COUNT = 0

def get_product_count():
    """トレカエースのページから現在の掲載商品数を数える関数"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(URL, headers=headers, timeout=15)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, "html.parser")
        
        # トレカエースの検索結果から、各商品の詳細リンク（詳しく見るボタン等）の数をカウント
        products = soup.find_all("a", string="詳しく見る")
        return len(products)
        
    except Exception as e:
        print(f"データ取得エラー: {e}")
        return None

def check_website():
    global LAST_PRODUCT_COUNT
    
    current_count = get_product_count()
    
    # サイトが一時的に重いなどでデータが取れなかった場合は何もしない
    if current_count is None:
        return

    # 初回実行時は、現在の数を記録して監視をスタートする
    if LAST_PRODUCT_COUNT == 0:
        LAST_PRODUCT_COUNT = current_count
        print(f"【監視スタート】現在の掲載商品数は {current_count} 個です。")
        return

    # 前回と比べて商品数が増えていたら、新商品が追加されたと判断してDiscordに通知
    if current_count > LAST_PRODUCT_COUNT:
        message = f"🚨 【トレカエース】新着BOXの追加（入荷）を検知しました！\n商品数が {LAST_PRODUCT_COUNT}個 から {current_count}個 に増えました！\n確認はこちら：\n{URL}"
        send_discord_notification(message)
        print("💡 新着商品を検知し、Discordへ通知しました。")
    
    # 商品数が変わった（減った場合も含め）場合は、基準の数を更新
    if current_count != LAST_PRODUCT_COUNT:
        LAST_PRODUCT_COUNT = current_count

def send_discord_notification(message):
    """Discordにメッセージを送信する関数"""
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)
    except Exception as e:
        print(f"Discord通知エラー: {e}")

# ─── メインループ（1分＝60秒おきに実行） ───
if __name__ == "__main__":
    while True:
        check_website()
        time.sleep(60)
