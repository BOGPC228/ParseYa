import time
import json
import csv
import pyautogui
import keyboard
import pyperclip

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# === НАСТРОЙКИ ===
URL = "https://fleet.taxi.yandex.ru/contractors?segment=archive&sort_field=last_order_date&sort_direction=desc&park_id=8c387ddfc6934cf1a05a72e373b637b4"
CLICK_DELAY = 1.3
MAX_ROWS = 3000
COOKIES_FILE = "cookies.json"
CHROME_OFFSET_Y = 120  # 🧠 настрой вручную под свой экран

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
    print("🌐 Открытие страницы для загрузки cookies...")
    driver.get("https://fleet.taxi.yandex.ru")
    time.sleep(3)

    print("🔑 Загрузка cookies...")
    with open(cookies_file, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    for cookie in cookies:
        try:
            if "domain" in cookie and "yandex" not in cookie["domain"]:
                continue
            cookie.pop("sameSite", None)
            cookie.pop("expiry", None)
            driver.add_cookie(cookie)
        except Exception as e:
            print(f"⚠️ Cookie '{cookie.get('name', '')}' пропущен: {e}")

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

def parse_data(driver, eye_x, _, phone_x):
    data = []
    last_phone = ""
    idx = 0
    fail_count = 0

    log = open("log.txt", "w", encoding="utf-8")

    def log_line(text):
        print(text)
        log.write(text + "\n")

    while idx < MAX_ROWS:
        rows = driver.find_elements(By.XPATH, '//tr[@aria-rowindex]')
        if idx >= len(rows):
            log_line("🔄 Попытка обновления страницы для автоподгрузки...")
            driver.refresh()
            time.sleep(5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            rows = driver.find_elements(By.XPATH, '//tr[@aria-rowindex]')
            if idx >= len(rows):
                log_line("📉 Больше строк не найдено даже после обновления. Завершение.")
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

            # === Копирование номера: пробуем через буфер ===
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
                    log_line(f"⚠️ [{idx+1}] Буфер не обновился, повторный клик по глазу")
                    pyautogui.click(eye_x, y)
                    time.sleep(CLICK_DELAY)

            # === Если буфер всё ещё не обновился, пробуем через DOM ===
            if not phone or phone == last_phone:
                try:
                    phone_el = row_el.find_element(By.XPATH, './/a[starts-with(@href, "tel:")]/span')
                    phone = phone_el.text.strip().replace(" ", "").replace("+", "").replace("-", "")
                    log_line(f"📥 [{idx+1}] Номер получен через DOM: {phone}")
                except:
                    log_line(f"❌ [{idx+1}] Номер не получен ни из буфера, ни из DOM")
                    fail_count += 1
                    if fail_count >= 10:
                        log_line("🚨 Слишком много ошибок подряд. Завершение.")
                        break
                    idx += 1
                    continue

            last_phone = phone
            data.append((name, phone))
            log_line(f"✅ [{idx+1}] {name} — {phone}")
            fail_count = 0

        except Exception as e:
            log_line(f"⚠️ [{idx+1}] Ошибка: {str(e)}")

        idx += 1

    log.close()
    return data

def save_to_csv(data, filename="voditeli.csv"):
    with open(filename, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Имя", "Телефон"])
        writer.writerows(data)

def main():
    driver = setup_driver()
    load_cookies(driver)
    time.sleep(1)

    print("🔁 Переход на страницу водителей...")
    driver.get(URL)
    time.sleep(5)

    data = []
    start_coords = None

    while True:
        print("\n📋 Меню:")
        print("[1] Начать парсинг")
        print("[2] Сохранить в CSV")
        print("[3] Закрыть браузер и выйти")
        print("[4] Сбросить координаты мышки")
        choice = input("👉 Введите номер действия: ").strip()

        if choice == "1":
            if not start_coords:
                start_coords = wait_for_positions()

            print("🚀 Парсинг пошёл...")
            data = parse_data(driver, *start_coords)
            print(f"✅ Завершено. Собрано записей: {len(data)}")

        elif choice == "2":
            if data:
                save_to_csv(data)
                print("💾 CSV сохранён: voditeli.csv")
            else:
                print("⚠️ Сначала нужно собрать данные.")

        elif choice == "3":
            print("👋 Закрытие браузера...")
            driver.quit()
            break

        elif choice == "4":
            print("♻️ Сброс координат мышки...")
            start_coords = None

        else:
            print("❓ Неизвестная команда. Введите 1, 2, 3 или 4.")

if __name__ == "__main__":
    main()
