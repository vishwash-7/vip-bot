import os
import time
import sqlite3
import threading
from datetime import datetime, timedelta
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

# ==========================================
# ⚙️ CLIENT CONFIGURATION (Har Naye Buyer ke liye bas yeh badlein)
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))          # Buyer ka Telegram Numeric ID
VIP_CHANNEL_ID = int(os.environ.get("VIP_CHANNEL_ID", "-1001234567890"))  # Private VIP Channel/Group ID (-100 se shuru hota hai)
UPI_ID = os.environ.get("UPI_ID", "merchant@upi")                # Buyer ki UPI ID
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "Premium VIP Club")

# Plans Configuration: "plan_key": {"name": "Display Name", "price": Price, "days": Validity_in_days}
PLANS = {
    "1m": {"name": "🔥 1 Month VIP", "price": 199, "days": 30},
    "3m": {"name": "💎 3 Months VIP", "price": 499, "days": 90},
    "life": {"name": "👑 Lifetime VIP", "price": 999, "days": 3650}
}
# ==========================================

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_selected_plan = {}

# ==========================================
# 🗄️ DATABASE SETUP (SQLite)
# ==========================================
def init_db():
    conn = sqlite3.connect("vip_members.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    plan_name TEXT,
                    expiry_date TEXT,
                    status TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

def save_user(user_id, username, plan_name="None", expiry_date="None", status="free"):
    conn = sqlite3.connect("vip_members.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if c.fetchone() is None:
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)", (user_id, username, plan_name, expiry_date, status))
    else:
        if status != "free":
            c.execute("UPDATE users SET plan_name=?, expiry_date=?, status=? WHERE user_id=?",
                      (plan_name, expiry_date, status, user_id))
    conn.commit()
    conn.close()

# ==========================================
# 🚀 USER COMMANDS & FLOW
# ==========================================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    save_user(user_id, username)

    markup = InlineKeyboardMarkup(row_width=1)
    for key, p in PLANS.items():
        markup.add(InlineKeyboardButton(f"{p['name']} - ₹{p['price']}", callback_data=f"buy_{key}"))
    markup.add(InlineKeyboardButton("📊 My Membership Status", callback_data="my_status"))
    markup.add(InlineKeyboardButton("💬 Contact Support", url=f"tg://user?id={ADMIN_ID}"))

    welcome_text = (
        f"👋 <b>Welcome to {CHANNEL_NAME} Official Bot!</b>\n\n"
        f"Yahan se aap hamare Private VIP Group ka instant access le sakte hain.\n\n"
        f"✅ <b>Automatic Instant Joining Link</b>\n"
        f"✅ <b>24/7 Access & Support</b>\n\n"
        f"👇 <b>Neeche diye gaye buttons se apna Plan chunein:</b>"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data

    # 1. User selects a plan
    if data.startswith("buy_"):
        plan_key = data.split("_")[1]
        plan = PLANS[plan_key]
        user_selected_plan[user_id] = plan_key

        pay_text = (
            f"🛒 <b>Selected Plan:</b> {plan['name']}\n"
            f"💰 <b>Amount to Pay:</b> ₹{plan['price']}\n"
            f"⏳ <b>Validity:</b> {plan['days']} Days\n\n"
            f"🏦 <b>Pay via UPI ID:</b> <code>{UPI_ID}</code>\n"
            f"<i>(UPI ID par tap karke copy karein aur GPay/PhonePe/Paytm se pay karein)</i>\n\n"
            f"📸 <b>Step 2:</b> Payment karne ke baad, <b>Payment ka Screenshot</b> isi chat mein direct bhej dein!"
        )
        bot.send_message(call.message.chat.id, pay_text)
        bot.answer_callback_query(call.id)

    # 2. Check membership status
    elif data == "my_status":
        conn = sqlite3.connect("vip_members.db", check_same_thread=False)
        c = conn.cursor()
        c.execute("SELECT plan_name, expiry_date, status FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()

        if row and row[2] == "active":
            bot.send_message(call.message.chat.id, f"✅ <b>Status: ACTIVE VIP</b>\n📦 <b>Plan:</b> {row[0]}\n📅 <b>Expiry Date:</b> {row[1]}")
        else:
            bot.send_message(call.message.chat.id, "❌ Aapka koi active VIP plan nahi hai. `/start` daba kar plan chunein.")
        bot.answer_callback_query(call.id)

    # 3. Admin Approves Payment
    elif data.startswith("approve_"):
        if user_id != ADMIN_ID:
            return
        parts = data.split("_")
        target_user_id = int(parts[1])
        plan_key = parts[2]
        plan = PLANS[plan_key]

        expiry_dt = (datetime.now() + timedelta(days=plan['days'])).strftime("%Y-%m-%d %H:%M:%S")
        save_user(target_user_id, "VIP_User", plan['name'], expiry_dt, "active")

        try:
            # Unban in case user was previously kicked on expiry
            bot.unban_chat_member(VIP_CHANNEL_ID, target_user_id, only_if_banned=True)
            # Generate 1-time invite link (member_limit=1)
            invite = bot.create_chat_invite_link(
                VIP_CHANNEL_ID,
                member_limit=1,
                expire_date=int(time.time()) + 86400
            )
            bot.send_message(
                target_user_id,
                f"🎉 <b>Payment Approved!</b>\n\n"
                f"📦 <b>Plan:</b> {plan['name']}\n"
                f"📅 <b>Valid Till:</b> {expiry_dt}\n\n"
                f"🔗 <b>Your Private Joining Link (Sirf 1 baar kaam karega):</b>\n{invite.invite_link}"
            )
            bot.edit_message_caption(
                caption=call.message.caption + "\n\n✅ <b>APPROVED & LINK SENT!</b>",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
        except Exception as e:
            bot.send_message(ADMIN_ID, f"⚠️ Error generating link! Make sure Bot is ADMIN in VIP Channel with 'Invite Users' permission.\nError: {e}")

    # 4. Admin Rejects Payment
    elif data.startswith("reject_"):
        if user_id != ADMIN_ID:
            return
        target_user_id = int(data.split("_")[1])
        bot.send_message(target_user_id, "❌ <b>Payment Verification Failed!</b>\nAapka screenshot valid nahi paya gaya. Kripya sahi proof bhejein ya support se baat karein.")
        bot.edit_message_caption(
            caption=call.message.caption + "\n\n❌ <b>REJECTED!</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )

# ==========================================
# 📸 HANDLE PAYMENT SCREENSHOTS FROM USER
# ==========================================
@bot.message_handler(content_types=['photo'])
def handle_screenshot(message):
    user_id = message.from_user.id
    if user_id not in user_selected_plan:
        bot.reply_to(message, "⚠️ Kripya pehle `/start` daba kar apna Plan select karein, uske baad screenshot bhejein.")
        return

    plan_key = user_selected_plan[user_id]
    plan = PLANS[plan_key]
    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}_{plan_key}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
    )

    caption = (
        f"🔔 <b>New Payment Screenshot!</b>\n\n"
        f"👤 <b>User:</b> {username} (<code>{user_id}</code>)\n"
        f"📦 <b>Plan:</b> {plan['name']} (₹{plan['price']})\n\n"
        f"👇 Verify UPI payment and click below:"
    )
    bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=caption, reply_markup=markup)
    bot.reply_to(message, "⏳ <b>Screenshot Mil Gaya Hai!</b>\nAdmin aapki payment verify kar rahe hain. Approve hote hi aapko yahin VIP Joining Link mil jayega.")

# ==========================================
# 🛠️ ADMIN PANEL (/admin & /broadcast)
# ==========================================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect("vip_members.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE status='active'")
    active = c.fetchone()[0]
    conn.close()

    text = (
        f"👑 <b>Admin Control Panel</b>\n\n"
        f"👥 <b>Total Bot Users:</b> {total}\n"
        f"💎 <b>Active VIP Members:</b> {active}\n\n"
        f"📢 <b>Sabhi users ko message bhejne ke liye likhein:</b>\n"
        f"<code>/broadcast Aapka Message Yahan</code>"
    )
    bot.send_message(ADMIN_ID, text)

@bot.message_handler(commands=['broadcast'])
def broadcast_msg(message):
    if message.from_user.id != ADMIN_ID:
        return
    msg_text = message.text.replace("/broadcast", "").strip()
    if not msg_text:
        bot.reply_to(message, "⚠️ Example: `/broadcast Aaj raat 8 baje special offer hai!`")
        return

    conn = sqlite3.connect("vip_members.db", check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    all_users = c.fetchall()
    conn.close()

    sent = 0
    for u in all_users:
        try:
            bot.send_message(u[0], f"📢 <b>Announcement:</b>\n\n{msg_text}")
            sent += 1
            time.sleep(0.05)
        except:
            pass
    bot.reply_to(message, f"✅ Broadcast successfully sent to {sent} users!")

# ==========================================
# ⏰ AUTO-EXPIRY CHECKER (Runs in Background)
# ==========================================
def check_expired_members():
    while True:
        try:
            conn = sqlite3.connect("vip_members.db", check_same_thread=False)
            c = conn.cursor()
            c.execute("SELECT user_id, expiry_date FROM users WHERE status='active'")
            rows = c.fetchall()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            for user_id, exp_date in rows:
                if now_str >= exp_date:
                    try:
                        # Remove user from VIP channel
                        bot.ban_chat_member(VIP_CHANNEL_ID, user_id)
                        bot.unban_chat_member(VIP_CHANNEL_ID, user_id)
                        bot.send_message(user_id, "⚠️ <b>Aapka VIP Plan Expire ho gaya hai!</b>\nGroup mein wapas judne ke liye `/start` daba kar plan renew karein.")
                    except:
                        pass
                    c.execute("UPDATE users SET status='expired' WHERE user_id=?", (user_id,))
                    conn.commit()
            conn.close()
        except Exception as e:
            print("Expiry Checker Error:", e)
        time.sleep(3600)  # Har 1 ghante mein check karega

threading.Thread(target=check_expired_members, daemon=True).start()

# ==========================================
# 🌐 KEEP-ALIVE WEB SERVER (For Render / Koyeb)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "VIP Membership Bot is Running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    print("Bot Started Successfully...")
    bot.infinity_polling(skip_pending=True)
