import telebot
import sqlite3
import time
import schedule
import re


API_TOKEN = '8109337541:AAE7qJVLEwiyTXTfRM2W2AFZQl8waR_1AE8'
ADMIN_CHAT_ID = 380028150
ADMIN_CHAT_IDD = 138953897

bot = telebot.TeleBot(API_TOKEN)

conn = sqlite3.connect('parsdb.sqlite3', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS cadastral_numbers (id INTEGER PRIMARY KEY, number TEXT UNIQUE)')
cursor.execute('CREATE TABLE IF NOT EXISTS seen_links (kn TEXT, link TEXT, PRIMARY KEY (kn, link))')
conn.commit()

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if user_id == ADMIN_CHAT_ID or user_id == ADMIN_CHAT_IDD:
        bot.send_message(message.chat.id, "Введите кн")
    else:
        pass

@bot.message_handler(commands=['delete'])
def delete_kn(message):
    user_id = message.from_user.id
    if user_id == ADMIN_CHAT_ID or user_id == ADMIN_CHAT_IDD:
        cursor.execute("SELECT id, number FROM cadastral_numbers")
        rows = cursor.fetchall()
        if not rows:
            bot.send_message(message.chat.id, "Список пуст.")
            return
        markup = telebot.types.InlineKeyboardMarkup()
        for row in rows:
            btn = telebot.types.InlineKeyboardButton(text=row[1], callback_data=f"delete_{row[0]}")
            markup.add(btn)
        bot.send_message(message.chat.id, "Выберите КН для удаления:", reply_markup=markup)
    else:
        pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def handle_delete(call):
    id_to_delete = call.data.split("_")[1]
    cursor.execute("DELETE FROM cadastral_numbers WHERE id = ?", (id_to_delete,))
    conn.commit()
    bot.edit_message_text("Удалено.", chat_id=call.message.chat.id, message_id=call.message.message_id)

@bot.message_handler(commands=['list'])
def show_list(message):
    user_id = message.from_user.id
    if user_id == ADMIN_CHAT_ID or user_id == ADMIN_CHAT_IDD:
        cursor.execute("SELECT number FROM cadastral_numbers ORDER BY number")
        rows = cursor.fetchall()
        if not rows:
            bot.send_message(message.chat.id, "Список КН пуст.")
        else:
            text = "Отслеживаемые КН:\n" + "\n".join(f"• {row[0]}" for row in rows)
            bot.send_message(message.chat.id, text)
    else:
        pass

@bot.message_handler(func=lambda m: True)
def add_cadastral_number(message):
    user_id = message.from_user.id
    if user_id == ADMIN_CHAT_ID or user_id == ADMIN_CHAT_IDD:
        kn = message.text.strip()
        if ':' in kn:
            kn_list = message.text.strip().split('\n')  # разбиваем по строкам
    
            added = []
            skipped = []
    
            for kn in kn_list:
                kn = kn.strip()
                if not kn:
                    continue
                try:
                    cursor.execute("INSERT INTO cadastral_numbers (number) VALUES (?)", (kn,))
                    conn.commit()
                    added.append(kn)
                except sqlite3.IntegrityError:
                    skipped.append(kn)
    
            msg = ""
            if added:
                msg += "✅ Добавлены КН:\n" + "\n".join(added) + "\n"
            if skipped:
                msg += "⚠️ Уже были в базе:\n" + "\n".join(skipped)
    
            bot.send_message(message.chat.id, msg.strip())
        else:
            bot.send_message(message.chat.id, "Неверный формат. Пример: 54:35:091455")
    else:
        pass


import asyncio
from playwright.sync_api import sync_playwright

def parse_kn(kn):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://torgi.gov.ru/new/public/lots/reg", timeout=60000)

            page.locator('app-category-filter div').filter(has_text='Категория').nth(1).click()
            page.get_by_role("main").get_by_text("Земельные участки").click()
            page.get_by_role("textbox", name="Введите фразу для поиска").click()
            page.get_by_role("textbox", name="Введите фразу для поиска").fill(kn)
            page.locator("app-checkbox").filter(has_text="Точное совпадение").locator("div").nth(1).click()

            page.wait_for_timeout(5000)

            results = []
            links = page.locator("a").all()
            for link in links:
                href = link.get_attribute("href")
                if href and re.match(r"^/new/public/lots/lot/\d+_\d+/\(lotInfo:info\)\?fromRec=false$", href):
                    full_link = f"https://torgi.gov.ru{href}"
                    cursor.execute("SELECT 1 FROM seen_links WHERE kn = ? AND link = ?", (kn, full_link))
                    if not cursor.fetchone():
                        mark = "Л" if "/lot/" in href else "И"
                        results.append(f"{mark}: {full_link}")
                        cursor.execute("INSERT INTO seen_links (kn, link) VALUES (?, ?)", (kn, full_link))
                        conn.commit()

            browser.close()
            return results or [f"Ничего нового не найдено по КН {kn}"]
    except Exception as e:
        return [f"❌ Ошибка при проверке КН {kn}: {str(e)}"]



def check_all_kns():
    cursor.execute("SELECT number FROM cadastral_numbers")
    rows = cursor.fetchall()
    for row in rows:
        kn = row[0]
        results = parse_kn(kn)
        for res in results:
            bot.send_message(ADMIN_CHAT_ID, f"🔎 КН {kn}:\n{res}")
            bot.send_message(ADMIN_CHAT_IDD, f"🔎 КН {kn}:\n{res}")

schedule.every().day.at("12:00").do(check_all_kns)

import threading
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=run_scheduler).start()

check_all_kns()

bot.infinity_polling()