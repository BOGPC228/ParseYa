import time
import json
import csv
import os
import pyautogui
import keyboard
import pyperclip
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# === НАСТРОЙКИ ===
URL = "https://fleet.taxi.yandex.ru/contractors?segment=archive&sort_field=last_order_date&sort_direction=desc&park_id=8c387ddfc6934cf1a05a72e373b637b4"
CLICK_DELAY = 1.3
MAX_ROWS = 3000
COOKIES_FILE = "cookies.json"
CHROME_OFFSET_Y = 120
SCROLL_STEP = 300

def setup_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver

def load_cookies(driver, cookies_file=COOKIES_FILE):
    print("🌐 Загружаем куки...")
    with open(cookies_file, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    for cookie in cookies:
        try:
            if "domain" in cookie and "yandex" not in cookie["domain"]:
                continue
            cookie.pop("sameSite", None)
            cookie.pop("expiry", None)
            driver.add_cookie(cookie)
        except:
            continue

def wait_for_positions():
    print("⏳ Наведи мышку на 'глаз' и нажми [Enter]...")
    while True:
        if keyboard.is_pressed('enter'):
            eye_pos = pyautogui.position()
            print(f"✅ 'Глаз' зафиксирован: {eye_pos}")
            break
        time.sleep(0.1)

    print("⏳ Теперь наведи мышку на номер и нажми [P]...")
    while True:
        if keyboard.is_pressed('p'):
            phone_pos = pyautogui.position()
            print(f"✅ 'Номер' зафиксирован: {phone_pos}")
            break
        time.sleep(0.1)

    return eye_pos[0], eye_pos[1], phone_pos[0]

def save_to_csv(name, phone, filename="voditeli.csv"):
    mode = 'a' if os.path.exists(filename) else 'w'
    header = not os.path.exists(filename)

    with open(filename, mode, newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(["Имя", "Телефон"])
        writer.writerow([name, phone])

def scroll_to_start(driver, target_row):
    print(f"🔄 Скроллим страницу до {target_row} строки...")
    for _ in range(1000):
        rows = driver.find_elements(By.XPATH, '//tr[@aria-rowindex]')
        if len(rows) >= target_row:
            print(f"✅ Достигли {len(rows)} строк. Можно начинать парсинг.")
            return
        driver.execute_script(f"window.scrollBy(0, {SCROLL_STEP});")
        time.sleep(0.5)
    print("⚠️ Не удалось подгрузить нужное количество строк. Парсим что есть.")

def parse_data(driver, eye_x, _, phone_x, start_idx):
    last_phone = ""
    idx = start_idx
    fail_count = 0

    log = open("log.txt", "a", encoding="utf-8")

    def log_line(text):
        print(text)
        log.write(text + "\n")

    while idx < MAX_ROWS:
        rows = driver.find_elements(By.XPATH, '//tr[@aria-rowindex]')
        if idx >= len(rows):
            log_line("📉 Строк больше нет. Завершаем.")
            break

        row_el = rows[idx]

        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row_el)
            time.sleep(0.8)

            rect = driver.execute_script("return arguments[0].getBoundingClientRect()", row_el)
            y = rect["top"] + CHROME_OFFSET_Y

            pyautogui.moveTo(eye_x, y, duration=0.5)
            pyautogui.click()
            time.sleep(CLICK_DELAY)

            try:
                name_el = row_el.find_element(By.XPATH, './/td[@aria-colindex="1"]//span')
                name = name_el.text.strip()
            except:
                log_line(f"❌ [{idx+1}] Имя не найдено")
                idx += 1
                continue

            phone = None
            for attempt in range(2):
                pyperclip.copy('')
                pyautogui.moveTo(phone_x, y, duration=0.4)
                pyautogui.click(clicks=2, interval=0.1)
                time.sleep(0.5)
                phone = pyperclip.paste().strip().replace(" ", "").replace("+", "").replace("-", "")
                if phone and phone != last_phone:
                    break
                if attempt == 0:
                    log_line(f"⚠️ [{idx+1}] Повторный клик по глазу")
                    pyautogui.click(eye_x, y)
                    time.sleep(CLICK_DELAY)

            if not phone or phone == last_phone:
                try:
                    phone_el = row_el.find_element(By.XPATH, './/a[starts-with(@href, "tel:")]/span')
                    phone = phone_el.text.strip().replace(" ", "").replace("+", "").replace("-", "")
                    log_line(f"📥 [{idx+1}] Номер получен через DOM: {phone}")
                except:
                    log_line(f"❌ [{idx+1}] Номер не получен")
                    fail_count += 1
                    if fail_count >= 10:
                        log_line("🚨 Слишком много ошибок подряд. Завершаем.")
                        break
                    idx += 1
                    continue

            last_phone = phone
            save_to_csv(name, phone)
            log_line(f"✅ [{idx+1}] {name} — {phone}")
            fail_count = 0

        except Exception as e:
            log_line(f"⚠️ [{idx+1}] Ошибка: {str(e)}")

        idx += 1

    log.close()

def main():
    if os.path.exists("voditeli.csv"):
        try:
            df = pd.read_csv("voditeli.csv")
            start_idx = len(df)
            print(f"🔄 Найдено {start_idx} строк в CSV. Продолжаем с {start_idx+1}.")
        except:
            print("⚠️ Ошибка чтения CSV. Начинаем с 0.")
            start_idx = 0
    else:
        start_idx = 0

    driver = setup_driver()
    driver.get("https://fleet.taxi.yandex.ru")
    time.sleep(3)
    load_cookies(driver)
    driver.get(URL)
    time.sleep(5)

    scroll_to_start(driver, start_idx)

    start_coords = wait_for_positions()
    if not start_coords:
        print("⚠️ Позиции мышки не заданы. Выход.")
        driver.quit()
        return

    parse_data(driver, *start_coords, start_idx)
    driver.quit()

if __name__ == "__main__":
    main()
