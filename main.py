import os
import time
import requests
from bs4 import BeautifulSoup

# ─── 【設定部分】 ───
URL = "https://toreca-ace.com"
# 安全対策：URLを直接書かず、サーバーの秘密のポケットから読み込むように変更
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
        print(f"数据取得エラー: {e}")
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

def send_discord_notification(message):
    data = {"content": message}
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)
    except Exception as e:
        print(f"Discord通知エラー: {e}")

if __name__ == "__main__":
    while True:
        check_website()
        time.sleep(60)
