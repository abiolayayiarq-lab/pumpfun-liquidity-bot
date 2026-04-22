import os
import json
import requests
import websocket
import threading
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ENV
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise Exception("TELEGRAM_TOKEN não definido")

# SOLANA
RPC_WS = "wss://api.mainnet-beta.solana.com"
RPC_HTTP = "https://api.mainnet-beta.solana.com"

RAYDIUM_PROGRAM = "RVKd61ztZW9z7sC5cZk9j3T1j9nM1u8hXk8FZ4o8u4Z"
PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

MIN_LIQ = 7000
SOL_PRICE = 150

running = False


def get_tx(sig):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [sig, {"encoding": "jsonParsed"}]
    }
    return requests.post(RPC_HTTP, json=payload).json().get("result")


def is_pump(tx):
    try:
        for ins in tx["transaction"]["message"]["instructions"]:
            if ins.get("programId") == PUMP_PROGRAM:
                return True
    except:
        pass
    return False


def get_token(tx):
    try:
        for ins in tx["transaction"]["message"]["instructions"]:
            if "parsed" in ins:
                info = ins["parsed"].get("info", {})
                if "mint" in info:
                    return info["mint"]
    except:
        pass
    return None


def calc_liq(tx):
    try:
        pre = tx["meta"]["preTokenBalances"]
        post = tx["meta"]["postTokenBalances"]

        total = 0

        for p in post:
            mint = p["mint"]
            post_amt = float(p["uiTokenAmount"]["uiAmount"] or 0)

            pre_match = next(
                (x for x in pre if x["mint"] == mint and x["owner"] == p["owner"]),
                None
            )

            pre_amt = float(pre_match["uiTokenAmount"]["uiAmount"] or 0) if pre_match else 0

            delta = post_amt - pre_amt

            if mint == "So11111111111111111111111111111111111111112":
                total += delta * SOL_PRICE

        return total
    except:
        return 0


def start_ws(bot, chat_id):
    global running
    running = True

    def on_message(ws, message):
        global running
        if not running:
            ws.close()
            return

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
        if not token:
            return

        msg = f"""
🚀 PUMP.FUN ALERT

Token:
{token}

Liquidez: ${int(liq)}

https://solscan.io/tx/{sig}
"""
        bot.send_message(chat_id=chat_id, text=msg)

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


# TELEGRAM UI

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("▶️ Start", callback_data="start")],
        [InlineKeyboardButton("⏹ Stop", callback_data="stop")]
    ]

    await update.message.reply_text(
        "Controle do bot:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global running

    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id

    if query.data == "start":
        if running:
            await query.edit_message_text("⚠️ Já está rodando")
            return

        threading.Thread(
            target=start_ws,
            args=(context.bot, chat_id),
            daemon=True
        ).start()

        await query.edit_message_text("✅ Monitoramento iniciado")

    elif query.data == "stop":
        running = False
        await query.edit_message_text("⛔ Monitoramento parado")


def main():
    print("🚀 Iniciando bot...")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    print("✅ Bot rodando...")
    app.run_polling()


if __name__ == "__main__":
    main()
