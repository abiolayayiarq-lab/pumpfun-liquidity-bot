import websocket
import json
import requests
import os
import threading

RPC_WS = "wss://api.mainnet-beta.solana.com"
RPC_HTTP = "https://api.mainnet-beta.solana.com"

RAYDIUM_PROGRAM = "RVKd61ztZW9z7sC5cZk9j3T1j9nM1u8hXk8FZ4o8u4Z"
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

MIN_LIQ = 7000
SOL_PRICE = 150

running = False

def send(msg):
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": msg})


def get_tx(sig):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed"}]
    }
    return requests.post(RPC_HTTP, json=payload).json().get("result")


def is_pump(tx):
    for ins in tx["transaction"]["message"]["instructions"]:
        if ins.get("programId") == PUMP_PROGRAM:
            return True
    return False


def get_token(tx):
    for ins in tx["transaction"]["message"]["instructions"]:
        if "parsed" in ins:
            info = ins["parsed"].get("info", {})
            if "mint" in info:
                return info["mint"]
    return None


def calc_liq(tx):
    try:
        pre = tx["meta"]["preTokenBalances"]
        post = tx["meta"]["postTokenBalances"]

        total = 0

        for p in post:
            mint = p["mint"]
            post_amt = float(p["uiTokenAmount"]["uiAmount"] or 0)

            pre_match = next((x for x in pre if x["mint"] == mint and x["owner"] == p["owner"]), None)
            pre_amt = float(pre_match["uiTokenAmount"]["uiAmount"] or 0) if pre_match else 0

            delta = post_amt - pre_amt

            if mint == "So11111111111111111111111111111111111111112":
                total += delta * SOL_PRICE

        return total
    except:
        return 0


def monitor():
    def on_message(ws, message):
        data = json.loads(message)

        if "params" not in data:
            return

        sig = data["params"]["result"]["value"]["signature"]
        tx = get_tx(sig)

        if not tx:
            return

        liq = calc_liq(tx)
        if liq < MIN_LIQ:
            return

        if not is_pump(tx):
            return

        token = get_token(tx)

        msg = f"""
🚀 PUMP FUN ALERT

Token: {token}
Liquidez: ${int(liq)}

https://solscan.io/tx/{sig}
"""
        send(msg)

    def on_open(ws):
        ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [RAYDIUM_PROGRAM]},
                {"commitment": "confirmed"}
            ]
        }))

    ws = websocket.WebSocketApp(RPC_WS, on_message=on_message)
    ws.on_open = on_open
    ws.run_forever()


if __name__ == "__main__":
    monitor()
