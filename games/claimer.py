import os
import shutil
import sys
import time
import re
import json
import getpass
import random
import subprocess
from PIL import Image
from pyzbar.pyzbar import decode
import qrcode_terminal
import fcntl
from fcntl import flock, LOCK_EX, LOCK_UN, LOCK_NB
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, ElementClickInterceptedException, UnexpectedAlertPresentException, MoveTargetOutOfBoundsException
from datetime import datetime, timedelta
from selenium.webdriver.chrome.service import Service as ChromeService
import requests

class Claimer:

    def __init__(self):
        self.initialize_settings()
        self.load_settings()
        self.random_offset = random.randint(self.settings['lowestClaimOffset'], self.settings['highestClaimOffset'])
        print(f"Инициализация скрипта автоматического клэйма кошелька {self.prefix} на Python - Удачи!")

        self.imported_seedphrase = None

        # Обновить настройки на основе ввода пользователя
        if len(sys.argv) > 1:
            user_input = sys.argv[1]  # Получить ID сессии из аргумента командной строки
            self.wallet_id = user_input
            self.output(f"ID сессии предоставлен: {user_input}", 2)
            
            # Безопасно проверить второй аргумент
            if len(sys.argv) > 2 and sys.argv[2] == "reset":
                self.settings['forceNewSession'] = True

            # Проверить флаг --seed-phrase и валидировать его
            if '--seed-phrase' in sys.argv:
                seed_index = sys.argv.index('--seed-phrase') + 1
                if seed_index < len(sys.argv):
                    self.seed_phrase = ' '.join(sys.argv[seed_index:])
                    seed_words = self.seed_phrase.split()
                    if len(seed_words) == 12:
                        self.output(f"Фраза восстановления принята:", 2)
                        self.imported_seedphrase = self.seed_phrase
                    else:
                        self.output("Неверная фраза восстановления. Игнорируется.", 2)
                else:
                    self.output("Фраза восстановления не предоставлена после флага --seed-phrase. Игнорируется.", 2)
        else:
            self.output("\nТекущие настройки:", 1)
            for key, value in self.settings.items():
                self.output(f"{key}: {value}", 1)
            user_input = input("\nОбновить настройки? (По умолчанию:<enter> / Да = y): ").strip().lower()
            if user_input == "y":
                self.update_settings()
            user_input = self.get_session_id()
            self.wallet_id = user_input

        self.session_path = f"./selenium/{self.wallet_id}"
        os.makedirs(self.session_path, exist_ok=True)
        self.screenshots_path = f"./screenshots/{self.wallet_id}"
        os.makedirs(self.screenshots_path, exist_ok=True)
        self.backup_path = f"./backups/{self.wallet_id}"
        os.makedirs(self.backup_path, exist_ok=True)
        self.step = "01"

        # Определяем базовый путь для отладочных скриншотов
        self.screenshot_base = os.path.join(self.screenshots_path, "screenshot")

        if self.settings["useProxy"] and self.settings["proxyAddress"] == "http://127.0.0.1:8080":
            self.run_http_proxy()
        elif self.forceLocalProxy:
            self.run_http_proxy()
            self.output("Использование встроенного прокси принудительно включено для этой игры.", 2)
        else:
            self.output("Прокси отключен в настройках.", 2)

    def initialize_settings(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.start_app_xpath = None
        self.settings = {}
        self.driver = None
        self.target_element = None
        self.random_offset = 0
        self.seed_phrase = None
        self.wallet_id = ""
        self.script = "default_script.py"
        self.prefix = "Default:"
        self.allow_early_claim = True
        self.default_platform = "web"

    def run(self):
        if not self.settings["forceNewSession"]:
            self.load_settings()
        cookies_path = os.path.join(self.session_path, 'cookies.json')
        if os.path.exists(cookies_path) and not self.settings['forceNewSession']:
            self.output("Возобновление предыдущей сессии...", 2)
        else:
            telegram_backup_dirs = [d for d in os.listdir(os.path.dirname(self.session_path)) if d.startswith("Telegram")]
            if telegram_backup_dirs:
                print("Найдены предыдущие сессии входа в Telegram. Нажатие <enter> выберет аккаунт под номером '1':")
                for i, dir_name in enumerate(telegram_backup_dirs):
                    print(f"{i + 1}. {dir_name}")

                user_input = input("Введите номер сессии для восстановления или 'n' для создания новой сессии: ").strip().lower()

                if user_input == 'n':
                    self.log_into_telegram(self.wallet_id)
                    self.quit_driver()
                    self.backup_telegram()
                elif user_input.isdigit() and 0 < int(user_input) <= len(telegram_backup_dirs):
                    self.restore_from_backup(os.path.join(os.path.dirname(self.session_path), telegram_backup_dirs[int(user_input) - 1]))
                else:
                    self.restore_from_backup(os.path.join(os.path.dirname(self.session_path), telegram_backup_dirs[0]))  # По умолчанию первая сессия

            else:
                self.log_into_telegram(self.wallet_id)
                self.quit_driver()
                self.backup_telegram()

            self.next_steps()
            self.quit_driver()

            try:
                shutil.copytree(self.session_path, self.backup_path, dirs_exist_ok=True)
                self.output("Мы сделали резервную копию данных сессии на случай сбоя!", 3)
            except Exception as e:
                self.output(f"Упс, не удалось сделать резервную копию данных сессии! Ошибка: {e}", 1)

            pm2_session = self.session_path.replace("./selenium/", "")
            self.output(f"Вы можете добавить новую/обновленную сессию в PM с помощью: pm2 start {self.script} --interpreter venv/bin/python3 --name {pm2_session} -- {pm2_session}", 1)
            user_choice = input("Введите 'y' для продолжения к функции 'claim', 'e' для выхода, 'a' или <enter> для автоматического добавления в PM2: ").lower()

            if user_choice == "e":
                self.output("Выход из скрипта. Вы можете возобновить процесс позже.", 1)
                sys.exit()
            elif user_choice == "a" or not user_choice:
                self.start_pm2_app(self.script, pm2_session, pm2_session)
                user_choice = input("Сохранить ваши процессы PM2? (Y/n): ").lower()
                if user_choice == "y" or not user_choice:
                    self.save_pm2()
                self.output(f"Теперь вы можете просматривать лог сессии в PM2 с помощью: pm2 logs {pm2_session}", 2)
                sys.exit()

        while True:
            self.manage_session()
            wait_time = self.full_claim()

            if os.path.exists(self.status_file_path):
                with open(self.status_file_path, "r+") as file:
                    status = json.load(file)
                    if self.session_path in status:
                        del status[self.session_path]
                        file.seek(0)
                        json.dump(status, file)
                        file.truncate()
                        self.output(f"Сессия освобождена: {self.session_path}", 3)

            self.quit_driver()

            now = datetime.now()
            # Проверка, что wait_time число, иначе 30
            if not isinstance(wait_time, (int, float)):
                wait_time = 30
            next_claim_time = now + timedelta(minutes=wait_time)
            this_claim_str = now.strftime("%d %B - %H:%M")
            next_claim_time_str = next_claim_time.strftime("%d %B - %H:%M")
            self.output(f"{this_claim_str} | Нужно ждать до {next_claim_time_str} перед следующей попыткой клэйма. Примерно {wait_time} минут.", 1)
            if self.settings["forceClaim"]:
                self.settings["forceClaim"] = False

            while wait_time > 0:
                this_wait = min(wait_time, 15)
                now = datetime.now()
                timestamp = now.strftime("%H:%M")
                self.output(f"[{timestamp}] Ожидание еще {this_wait} минут...", 3)
                time.sleep(this_wait * 60)  # Перевод минут в секунды
                wait_time -= this_wait
                if wait_time > 0:
                    self.output(f"Обновленное время ожидания: осталось {wait_time} минут.", 3)

    def load_settings(self):
        default_settings = {
            "forceClaim": False,
            "debugIsOn": True,
            "hideSensitiveInput": True,
            "screenshotQRCode": True,
            "maxSessions": 1,
            "verboseLevel": 2,
            "telegramVerboseLevel": 0,
            "lowestClaimOffset": 0,
            "highestClaimOffset": 15,
            "forceNewSession": False,
            "useProxy": False,
            "proxyAddress": "http://127.0.0.1:8080",
            "requestUserAgent": False,
            "telegramBotToken": "", 
            "telegramBotChatId": "",
            "enableCache": True  # Новая настройка
        }

        if os.path.exists(self.settings_file):
            with open(self.settings_file, "r") as f:
                loaded_settings = json.load(f)
            # Фильтрация неиспользуемых настроек из предыдущих версий
            self.settings = {k: loaded_settings.get(k, v) for k, v in default_settings.items()}
            self.output("Настройки успешно загружены.", 3)
        else:
            self.settings = default_settings
            self.save_settings()

    def save_settings(self):
        with open(self.settings_file, "w") as f:
            json.dump(self.settings, f)
        self.output("Настройки успешно сохранены.", 3)

    def update_settings(self):
        
        def update_setting(setting_key, message):
            current_value = self.settings.get(setting_key)
            response = input(f"\n{message} (Y/N, нажмите Enter чтобы оставить текущее [{current_value}]): ").strip().lower()
            if response == "y":
                self.settings[setting_key] = True
            elif response == "n":
                self.settings[setting_key] = False
            else:
                print(f"Текущая настройка сохранена: {current_value}")

        update_setting("forceClaim", "Принудительно выполнить клэйм при первом запуске? Не ждать заполнения таймера")
        update_setting("debugIsOn", "Включить отладку? Будут сохраняться скриншоты на локальном диске")
        update_setting("hideSensitiveInput", "Скрывать чувствительный ввод? Ваш номер телефона и фраза восстановления не будут видны на экране")
        update_setting("screenshotQRCode", "Разрешить вход по QR-коду? Альтернатива - по номеру телефона и одноразовому паролю")

        try:
            new_max_sessions = int(input(f"\nВведите максимальное количество одновременных сессий клэйма. Дополнительные будут в очереди до освобождения слота.\n(текущее: {self.settings['maxSessions']}): "))
            self.settings["maxSessions"] = new_max_sessions
        except ValueError:
            self.output("Количество сессий осталось без изменений.", 1)

        try:
            new_verbose_level = int(input("\nВведите уровень подробности вывода в консоль.\n 3 = все сообщения, 2 = шаги клэйма, 1 = минимальные шаги\n(текущее: {}): ".format(self.settings['verboseLevel'])))
            if 1 <= new_verbose_level <= 3:
                self.settings["verboseLevel"] = new_verbose_level
                self.output("Уровень подробности успешно обновлен.", 2)
            else:
                self.output("Уровень подробности остался без изменений.", 2)
        except ValueError:
            self.output("Уровень подробности остался без изменений.", 2)

        try:
            new_telegram_verbose_level = int(input("\nВведите уровень подробности Telegram (3 = все сообщения, 2 = шаги клэйма, 1 = минимальные шаги)\n(текущее: {}): ".format(self.settings['telegramVerboseLevel'])))
            if 0 <= new_telegram_verbose_level <= 3:
                self.settings["telegramVerboseLevel"] = new_telegram_verbose_level
                self.output("Уровень подробности Telegram успешно обновлен.", 2)
            else:
                self.output("Уровень подробности Telegram остался без изменений.", 2)
        except ValueError:
            self.output("Уровень подробности Telegram остался без изменений.", 2)

        try:
            new_lowest_offset = int(input("\nВведите минимальное смещение таймера клэйма (допустимые значения от -30 до +30 минут)\n(текущее: {}): ".format(self.settings['lowestClaimOffset'])))
            if -30 <= new_lowest_offset <= 30:
                self.settings["lowestClaimOffset"] = new_lowest_offset
                self.output("Минимальное смещение клэйма успешно обновлено.", 2)
            else:
                self.output("Недопустимый диапазон для минимального смещения клэйма. Введите значение от -30 до +30.", 2)
        except ValueError:
            self.output("Минимальное смещение клэйма осталось без изменений.", 2)

        try:
            new_highest_offset = int(input("\nВведите максимальное смещение таймера клэйма (допустимые значения от 0 до 60 минут)\n(текущее: {}): ".format(self.settings['highestClaimOffset'])))
            if 0 <= new_highest_offset <= 60:
                self.settings["highestClaimOffset"] = new_highest_offset
                self.output("Максимальное смещение клэйма успешно обновлено.", 2)
            else:
                self.output("Недопустимый диапазон для максимального смещения клэйма. Введите значение от 0 до 60.", 2)
        except ValueError:
            self.output("Максимальное смещение клэйма осталось без изменений.", 2)

        if self.settings["lowestClaimOffset"] > self.settings["highestClaimOffset"]:
            self.settings["lowestClaimOffset"] = self.settings["highestClaimOffset"]
            self.output("Минимальное смещение клэйма скорректировано до максимального, так как было больше.", 2)

        update_setting("useProxy", "Использовать прокси?")
        update_setting("requestUserAgent", "Собрать User Agent во время настройки?")
        
        # Ввод токена Telegram бота
        new_telegram_bot_token = input(f"\nВведите токен Telegram бота (текущее: {self.settings['telegramBotToken']}): ").strip()
        if new_telegram_bot_token:
            self.settings["telegramBotToken"] = new_telegram_bot_token

        update_setting("enableCache", "Включить кэш приложения?")

        self.save_settings()

        update_setting("forceNewSession", "Перезаписать существующую сессию и принудительно войти заново? Используйте, если сохраненная сессия сломалась\nОдноразово (настройка не сохраняется): ")

        self.output("\nОбновленные настройки:", 1)
        for key, value in self.settings.items():
            self.output(f"{key}: {value}", 1)
        self.output("", 1)

    def output(self, string, level=2):
        if self.settings['verboseLevel'] >= level:
            print(string)
        if self.settings['telegramBotToken'] and not self.settings['telegramBotChatId']:
            try:
                self.settings['telegramBotChatId'] = self.get_telegram_bot_chat_id()
                self.save_settings()  # Сохраняем настройки после получения chat ID
            except ValueError as e:
                pass
                # print(f"Ошибка при получении Telegram chat ID: {e}")
        if self.settings['telegramBotChatId'] and self.wallet_id and self.settings['telegramVerboseLevel'] >= level:
            self.send_message(string)

    import requests

    def get_telegram_bot_chat_id(self):
        """
        Получает последний апдейт и возвращает chat_id и message_id.
        Выбрасывает исключение, если апдейтов или сообщений нет.
        """
        url = f"https://api.telegram.org/bot{self.settings['telegramBotToken']}/getUpdates"
        params = {
            "limit": 1,    # только последний апдейт
            "timeout": 0,  # без долгого опроса
        }
        data = requests.get(url, params=params).json()
        updates = data.get("result", [])
        if not updates:
            raise ValueError("Обновления не найдены. Убедитесь, что бот получил хотя бы одно сообщение.")
        
        latest = updates[-1]
        msg = latest.get("message") or latest.get("edited_message")
        if not msg:
            raise ValueError("Последний апдейт не содержит объект сообщения.")
        
        chat_id = msg["chat"]["id"]
        message_id = msg["message_id"]
        return chat_id

    def send_message(self, string):
        try:
            if self.settings['telegramBotChatId'] == "":
                self.settings['telegramBotChatId'] = self.get_telegram_bot_chat_id()

            message = f"{self.wallet_id}: {string}"
            url = f"https://api.telegram.org/bot{self.settings['telegramBotToken']}/sendMessage?chat_id={self.settings['telegramBotChatId']}&text={message}"
            response = requests.get(url).json()
            # print(response)  # Отправляет сообщение и выводит ответ (закомментировано для чистоты вывода)
            if not response.get("ok"):
                raise ValueError(f"Не удалось отправить сообщение: {response}")
        except ValueError as e:
            print(f"Ошибка: {e}")

    def increase_step(self):
        step_int = int(self.step) + 1
        self.step = f"{step_int:02}"

    def get_session_id(self):
        """Запрашивает у пользователя ID сессии или определяет следующий последовательный ID с префиксом 'Wallet'.

        Возвращает:
            str: Введенный ID сессии или автоматически сгенерированный последовательный ID.
        """
        self.output(f"Ваш префикс сессии будет: {self.prefix}", 1)
        user_input = input("Введите уникальное имя сессии или нажмите <enter> для следующего последовательного кошелька: ").strip()

        # Устанавливаем директорию с папками сессий
        screenshots_dir = "./screenshots/"

        # Убедимся, что директория существует, чтобы избежать ошибки FileNotFoundError
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)

        # Список содержимого директории
        try:
            dir_contents = os.listdir(screenshots_dir)
        except Exception as e:
            self.output(f"Ошибка доступа к директории: {e}", 1)
            return None  # или обработать ошибку иначе

        # Фильтруем директории с префиксом 'Wallet' и извлекаем числовые части
        wallet_dirs = [int(dir_name.replace(self.prefix + 'Wallet', ''))
                    for dir_name in dir_contents
                    if dir_name.startswith(self.prefix + 'Wallet') and dir_name[len(self.prefix) + 6:].isdigit()]

        # Вычисляем следующий ID кошелька
        next_wallet_id = max(wallet_dirs) + 1 if wallet_dirs else 1

        # Используем следующий последовательный ID, если пользователь не ввел свой
        if not user_input:
            user_input = f"Wallet{next_wallet_id}"  # Обеспечиваем правильный префикс

        return self.prefix+user_input

    def prompt_user_agent(self):
        print (f"Шаг {self.step} - Пожалуйста, введите строку User-Agent или нажмите Enter для значения по умолчанию.")
        user_agent = input(f"Шаг {self.step} - User-Agent: ").strip()
        return user_agent

    def set_cookies(self):
        if not (self.forceRequestUserAgent or self.settings["requestUserAgent"]):
            cookies_path = f"{self.session_path}/cookies.json"
            cookies = self.driver.get_cookies()
            with open(cookies_path, 'w') as file:
                json.dump(cookies, file)
        else:
            user_agent = self.prompt_user_agent()
            cookies_path = f"{self.session_path}/cookies.json"
            cookies = self.driver.get_cookies()
            cookies.append({"name": "user_agent", "value": user_agent})  # Сохраняем user agent в cookies
            with open(cookies_path, 'w') as file:
                json.dump(cookies, file)

    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument(f"user-data-dir={self.session_path}")
        chrome_options.add_argument("--profile-directory=Default")
        chrome_options.add_argument("--headless=new")  # Включаем headless
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--enable-automation")

        # Пытаемся загрузить user agent из cookies
        try:
            cookies_path = f"{self.session_path}/cookies.json"
            with open(cookies_path, 'r') as file:
                cookies = json.load(file)
                user_agent_cookie = next((cookie for cookie in cookies if cookie["name"] == "user_agent"), None)
                if user_agent_cookie and user_agent_cookie["value"]:
                    user_agent = user_agent_cookie["value"]
                    self.output(f"Используется сохраненный user agent: {user_agent}", 2)
                else:
                    user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/124.0.2478.50 Version/17.0 Mobile/15E148 Safari/604.1"
                    self.output("User agent не найден, используется значение по умолчанию.", 2)
        except FileNotFoundError:
            user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/124.0.2478.50 Version/17.0 Mobile/15E148 Safari/604.1"
            self.output("Файл cookies не найден, используется user agent по умолчанию.", 2)

        # Корректируем платформу на основе user agent
        if any(keyword in user_agent for keyword in ['iPhone', 'iPad', 'iOS', 'iPhone OS']):
            self.default_platform = "ios"
            self.output("Обнаружена платформа iOS по user agent. tgWebAppPlatform будет изменен на 'ios' позже.", 2)
        elif 'Android' in user_agent:
            self.default_platform = "android"
            self.output("Обнаружена платформа Android по user agent. Установлен tgWebAppPlatform в 'android'.", 2)
        else:
            self.default_platform = "web"
            self.output("Платформа по умолчанию установлена в 'web'.", 3)

        chrome_options.add_argument(f"user-agent={user_agent}")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        if not self.settings.get("enableCache", True) and int(self.step) >= 100:
            chrome_options.add_argument("--disable-application-cache")

        if self.settings["useProxy"] or self.forceLocalProxy:
            proxy_server = self.settings["proxyAddress"]
            chrome_options.add_argument(f"--proxy-server={proxy_server}")

        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--test-type")

        chromedriver_path = shutil.which("chromedriver")
        if chromedriver_path is None:
            self.output("ChromeDriver не найден в PATH. Пожалуйста, убедитесь, что он установлен.", 1)
            exit(1)

        try:
            service = Service(chromedriver_path)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            return self.driver
        except Exception as e:
            self.output(f"Начальная настройка ChromeDriver могла не удаться: {e}", 1)
            self.output("Пожалуйста, убедитесь, что у вас правильная версия ChromeDriver для вашей системы.", 1)
            exit(1)

    def run_http_proxy(self):
        proxy_lock_file = "./start_proxy.txt"
        max_wait_time = 15 * 60  # 15 минут
        wait_interval = 5  # 5 секунд
        start_time = time.time()
        message_displayed = False

        while os.path.exists(proxy_lock_file) and (time.time() - start_time) < max_wait_time:
            if not message_displayed:
                self.output("Прокси уже запущен. Ожидание освобождения...", 2)
                message_displayed = True
            time.sleep(wait_interval)

        if os.path.exists(proxy_lock_file):
            self.output("Максимальное время ожидания истекло. Продолжаем запуск прокси.", 2)

        with open(proxy_lock_file, "w") as lock_file:
            lock_file.write(f"Прокси запущен в: {time.ctime()}\n")

        try:
            subprocess.run(['./launch.sh', 'enable-proxy'], check=True)
            self.output("http-прокси успешно запущен.", 2)
        except subprocess.CalledProcessError as e:
            self.output(f"Не удалось запустить http-прокси: {e}", 1)
        finally:
            os.remove(proxy_lock_file)

    def get_driver(self):
        if self.driver is None:  # Проверяем, нужно ли инициализировать драйвер
            self.manage_session()  # Убедимся, что можем начать сессию
            self.driver = self.setup_driver()
            self.output("\nCHROME DRIVER ИНИЦИАЛИЗИРОВАН: Не выходите из скрипта до отсоединения.",2)
        return self.driver

    def quit_driver(self):
        if self.driver:
            self.driver.quit()
            self.output("\nCHROME DRIVER ОТСОЕДИНЕН: Теперь безопасно выйти из скрипта.",2)
            self.driver = None
            self.release_session()  # Отмечаем сессию как закрытую

    def manage_session(self):
        current_session = self.session_path
        current_timestamp = int(time.time())
        session_started = False
        new_message = True
        output_priority = 2

        while True:
            try:
                with open(self.status_file_path, "r+") as file:
                    flock(file, LOCK_EX)
                    status = json.load(file)

                    # Очистка просроченных сессий
                    for session_id, timestamp in list(status.items()):
                        if current_timestamp - timestamp > 300:  # 5 минут
                            del status[session_id]
                            self.output(f"Удалена просроченная сессия: {session_id}", 3)

                    # Проверка доступных слотов, исключая текущую сессию
                    active_sessions = {k: v for k, v in status.items() if k != current_session}
                    if len(active_sessions) < self.settings['maxSessions']:
                        status[current_session] = current_timestamp
                        file.seek(0)
                        json.dump(status, file)
                        file.truncate()
                        self.output(f"Сессия запущена: {current_session} в {self.status_file_path}", 3)
                        flock(file, LOCK_UN)
                        session_started = True
                        break
                    flock(file, LOCK_UN)

                if not session_started:
                    self.output(f"Ожидание свободного слота. Текущие сессии: {len(active_sessions)}/{self.settings['maxSessions']}", output_priority)
                    if new_message:
                        new_message = False
                        output_priority = 3
                    time.sleep(random.randint(5, 15))
                else:
                    break

            except FileNotFoundError:
                # Создаем файл, если его нет
                with open(self.status_file_path, "w") as file:
                    flock(file, LOCK_EX)
                    json.dump({}, file)
                    flock(file, LOCK_UN)
            except json.decoder.JSONDecodeError:
                # Обработка пустого или поврежденного JSON
                with open(self.status_file_path, "w") as file:
                    flock(file, LOCK_EX)
                    self.output("Файл статуса поврежден. Сброс...", 3)
                    json.dump({}, file)
                    flock(file, LOCK_UN)

    def release_session(self):
        current_session = self.session_path
        current_timestamp = int(time.time())

        with open(self.status_file_path, "r+") as file:
            flock(file, LOCK_EX)
            status = json.load(file)
            if current_session in status:
                del status[current_session]
                file.seek(0)
                json.dump(status, file)
                file.truncate()
            flock(file, LOCK_UN)
            self.output(f"Сессия освобождена: {current_session}", 3)
    
    def log_into_telegram(self, user_input=None):

        self.step = "01"

        # Проверка и создание директорий
        self.session_path = f"./selenium/{user_input}"
        if os.path.exists(self.session_path):
            shutil.rmtree(self.session_path)
        os.makedirs(self.session_path, exist_ok=True)

        self.screenshots_path = f"./screenshots/{user_input}"
        if os.path.exists(self.screenshots_path):
            shutil.rmtree(self.screenshots_path)
        os.makedirs(self.screenshots_path, exist_ok=True)

        self.backup_path = f"./backups/{user_input}"
        if os.path.exists(self.backup_path):
            shutil.rmtree(self.backup_path)
        os.makedirs(self.backup_path, exist_ok=True)

        def visible_QR_code():
            max_attempts = 5
            attempt_count = 0
            last_url = "not a url"  # Заглушка для последнего обнаруженного URL QR-кода

            xpath = "//canvas[@class='qr-canvas']"
            self.driver.get(self.url)
            wait = WebDriverWait(self.driver, 20)
            QR_code = wait.until(EC.visibility_of_element_located((By.XPATH, xpath)))
            wait = WebDriverWait(self.driver, 3)
            self.output(f"Шаг {self.step} - Ожидание первого QR-кода - может занять до 30 секунд.", 1)
            self.increase_step()

            while attempt_count < max_attempts:
                try:
                    # Пытаемся найти элемент QR-кода
                    QR_code = wait.until(EC.visibility_of_element_located((By.XPATH, xpath)))
                    try:
                        # Пытаемся сделать скриншот QR-кода
                        QR_code.screenshot(f"{self.screenshots_path}/Шаг {self.step} - Начальный QR код.png")
                    except StaleElementReferenceException:
                        self.output(f"Шаг {self.step} - Элемент QR-кода устарел, ищем заново...", 1)
                        continue  # Повторяем, найдя элемент заново

                    image = Image.open(f"{self.screenshots_path}/Шаг {self.step} - Начальный QR код.png")
                    decoded_objects = decode(image)
                    if decoded_objects:
                        this_url = decoded_objects[0].data.decode('utf-8')
                        if this_url != last_url:
                            last_url = this_url  # Обновляем последний URL
                            attempt_count += 1
                            self.output("*** Важно: Открытый GUI в вашем Telegram может помешать входу скрипта! ***\n", 2)
                            self.output(f"Шаг {self.step} - Путь к скриншотам: {self.screenshots_path}\n", 1)
                            self.output(f"Шаг {self.step} - Генерация скриншота {attempt_count} из {max_attempts}\n", 2)
                            qrcode_terminal.draw(this_url)
                        if attempt_count >= max_attempts:
                            self.output(f"Шаг {self.step} - Достигнуто максимальное количество попыток без нового QR-кода.", 1)
                            return False
                        time.sleep(0.5)  # Ждем перед следующей проверкой
                    else:
                        time.sleep(0.5)  # QR-код не распознан, ждем перед повтором
                except (TimeoutException, NoSuchElementException):
                    self.output(f"Шаг {self.step} - QR-код больше не виден.", 2)
                    return True  # QR-код отсканирован или исчез

            self.output(f"Шаг {self.step} - Не удалось получить валидный QR-код после нескольких попыток.", 1)
            return False  # Если цикл завершился без успеха

        self.driver = self.get_driver()
    
        # Метод с QR-кодом
        if self.settings['screenshotQRCode']:
            try:
                while True:
                    if visible_QR_code():  # QR-код не найден
                        self.test_for_2fa()
                        return  # Выход из функции

                    # Если дошли сюда, QR-код все еще есть:
                    choice = input(f"\nШаг {self.step} - QR-код все еще отображается. Повторить (r) с новым QR-кодом или перейти к методу OTP (нажмите Enter): ")
                    print("")
                    if choice.lower() == 'r':
                        visible_QR_code()
                    else:
                        break

            except TimeoutException:
                self.output(f"Шаг {self.step} - Canvas не найден: Перезапустите скрипт и попробуйте QR-код или переключитесь на метод OTP.", 1)

        # Метод входа по одноразовому паролю (OTP)
        self.increase_step()
        self.output(f"Шаг {self.step} - Инициация метода одноразового пароля (OTP)...\n",1)
        self.driver.get(self.url)
        xpath = "//button[contains(@class, 'btn-primary') and contains(., 'Log in by phone Number')]"
        self.move_and_click(xpath, 30, True, "переключение на вход по номеру телефона", self.step, "visible")
        self.increase_step()

        # Выбор кода страны
        xpath = "//div[contains(@class, 'input-field-input')]"
        self.target_element = self.move_and_click(xpath, 30, True, "обновление страны пользователя", self.step, "visible")
        if not self.target_element:
            self.output(f"Шаг {self.step} - Не удалось найти поле ввода страны.", 1)
            return

        user_input = input(f"Шаг {self.step} - Пожалуйста, введите название вашей страны, как в списке Telegram: ").strip()
        self.target_element.send_keys(user_input)
        self.target_element.send_keys(Keys.RETURN)
        self.increase_step()

        # Ввод номера телефона
        xpath = "//div[contains(@class, 'input-field-input') and @inputmode='decimal']"
        self.target_element = self.move_and_click(xpath, 30, True, "запрос номера телефона пользователя", self.step, "visible")
        if not self.target_element:
            self.output(f"Шаг {self.step} - Не удалось найти поле ввода номера телефона.", 1)
            return
    
        def validate_phone_number(phone):
            # Регулярное выражение для проверки международного номера без ведущего 0, длиной от 7 до 15 цифр
            pattern = re.compile(r"^[1-9][0-9]{6,14}$")
            return pattern.match(phone)

        while True:
            if self.settings['hideSensitiveInput']:
                user_phone = getpass.getpass(f"Шаг {self.step} - Введите номер телефона без ведущего 0 (ввод скрыт): ")
            else:
                user_phone = input(f"Шаг {self.step} - Введите номер телефона без ведущего 0 (видимый ввод): ")
    
            if validate_phone_number(user_phone):
                self.output(f"Шаг {self.step} - Введен корректный номер телефона.",3)
                break
            else:
                self.output(f"Шаг {self.step} - Некорректный номер телефона, должно быть от 7 до 15 цифр без ведущего 0.",1)
        self.target_element.send_keys(user_phone)
        self.increase_step()

        # Ожидание кнопки "Далее" и клик по ней    
        xpath = "//button//span[contains(text(), 'Next')]"
        self.move_and_click(xpath, 15, True, "нажать далее для перехода к вводу OTP", self.step, "visible")
        self.increase_step()

        try:
            # Пытаемся найти и взаимодействовать с полем OTP
            wait = WebDriverWait(self.driver, 20)
            if self.settings['debugIsOn']:
                self.debug_information("подготовка к вводу OTP Telegram","check")
            password = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@type='tel']")))
            otp = input(f"Шаг {self.step} - Введите OTP Telegram из приложения: ")
            password.click()
            password.send_keys(otp)
            self.output(f"Шаг {self.step} - Пытаемся войти с вашим OTP Telegram.\n",3)
            self.increase_step()

        except TimeoutException:
            # Проверка на Storage Offline
            xpath = "//button[contains(text(), 'STORAGE_OFFLINE')]"
            self.move_and_click(xpath, 10, True, "проверка на 'STORAGE_OFFLINE'", self.step, "visible")
            if self.target_element:
                self.output(f"Шаг {self.step} - ***Прогресс заблокирован кнопкой 'STORAGE_OFFLINE'",1)
                self.output(f"Шаг {self.step} - Если вы используете старую сессию Wallet; попробуйте удалить или создать новую.",1)
                found_error = True
            # Проверка на flood wait
            xpath = "//button[contains(text(), 'FLOOD_WAIT')]"
            self.move_and_click(xpath, 10, True, "проверка на 'FLOOD_WAIT'", self.step, "visible")
            if self.target_element:
                self.output(f"Шаг {self.step} - ***Прогресс заблокирован кнопкой 'FLOOD_WAIT'", 1)
                self.output(f"Шаг {self.step} - Нужно подождать указанное количество секунд перед повтором.", 1)
                self.output(f"Шаг {self.step} - {self.target_element.text}")
                found_error = True
            if not found_error:
                self.output(f"Шаг {self.step} - Selenium не смог взаимодействовать с экраном OTP по неизвестной причине.")

        except Exception as e:  # Другие неожиданные ошибки
            self.output(f"Шаг {self.step} - Вход не удался. Ошибка: {e}", 1) 
            if self.settings['debugIsOn']:
                self.debug_information("неудачный вход в telegram","error")

        self.increase_step()
        self.test_for_2fa()

        if self.settings['debugIsOn']:
            self.debug_information("OTP Telegram успешно введен","check")

    def test_for_2fa(self):
        try:
            self.increase_step()
            WebDriverWait(self.driver, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
            xpath = "//input[@type='password' and contains(@class, 'input-field-input')]"
            fa_input = self.move_and_click(xpath, 15, False, "проверка необходимости 2FA (таймаут, если 2FA нет)", self.step, "present")
        
            if fa_input:
                if self.settings['hideSensitiveInput']:
                    tg_password = getpass.getpass(f"Шаг {self.step} - Введите пароль 2FA Telegram: ")
                else:
                    tg_password = input(f"Шаг {self.step} - Введите пароль 2FA Telegram: ")
                fa_input.send_keys(tg_password + Keys.RETURN)
                self.output(f"Шаг {self.step} - Пароль 2FA отправлен.\n", 3)
                self.output(f"Шаг {self.step} - Проверка правильности пароля 2FA.\n", 2)
            
                xpath = "//*[contains(text(), 'Incorrect password')]"
                try:
                    incorrect_password = WebDriverWait(self.driver, 8).until(EC.visibility_of_element_located((By.XPATH, xpath)))
                    self.output(f"Шаг {self.step} - Пароль 2FA отмечен как неверный Telegram - проверьте скриншоты отладки, если включены.", 1)
                    if self.settings['debugIsOn']:
                        self.debug_information("введен неверный пароль 2FA telegram","error")
                    self.quit_driver()
                    sys.exit()  # Выход при неверном пароле
                except TimeoutException:
                    pass

                self.output(f"Шаг {self.step} - Ошибок пароля не найдено.", 3)
                xpath = "//input[@type='password' and contains(@class, 'input-field-input')]"
                fa_input = self.move_and_click(xpath, 5, False, "финальная проверка успешного входа", self.step, "present")
                if fa_input:
                    self.output(f"Шаг {self.step} - Поле ввода 2FA все еще отображается, проверьте скриншоты отладки.\n", 1)
                    sys.exit()
                self.output(f"Шаг {self.step} - Проверка пароля 2FA пройдена успешно.\n", 3)
            else:
                self.output(f"Шаг {self.step} - Поле ввода 2FA не найдено.\n", 1)

        except TimeoutException:
            # Поле 2FA не найдено
            self.output(f"Шаг {self.step} - Двухфакторная авторизация не требуется.\n", 3)

        except Exception as e:  # Другие неожиданные ошибки
            self.output(f"Шаг {self.step} - Ошибка входа. 2FA ошибка - вероятно, нужно перезапустить скрипт: {e}", 1)
            if self.settings['debugIsOn']:
                self.debug_information("неуказанная ошибка при 2FA telegram","error")

    def next_steps(self):
        # Должна быть ПЕРЕОПРЕДЕЛЕНА в дочернем классе
        self.output("Функция 'next-steps' не определена (требуется переопределение в дочернем классе) \n", 1)

    def launch_iframe(self):
        def wait_ready(driver, timeout=30):
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
    
        self.driver = self.get_driver()
        self.driver.set_window_size(1920, 1080)
    
        # Очистка папки скриншотов (один раз за сессию)
        if int(self.step) < 101:
            if os.path.exists(self.screenshots_path):
                shutil.rmtree(self.screenshots_path)
            os.makedirs(self.screenshots_path)
    
        # --- Начальная проверка и проверка QR (нефатальная) ---
        try:
            self.driver.get("https://www.google.com/")
            wait_ready(self.driver)
            self.driver.get(self.url)  # ваша deep-ссылка, например https://web.telegram.org/k/#@IcebergAppBot
            wait_ready(self.driver)
            time.sleep(5)  # даем TG подгрузиться
    
            self.output(f"Шаг {self.step} - Проверка наличия QR (ожидается отсутствие).", 2)
            if self.settings.get('debugIsOn'):
                self.debug_information("проверка QR кода при старте сессии", "check")
    
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.visibility_of_element_located((By.XPATH, "//canvas[@class='qr-canvas']"))
                )
                self.output(
                    f"Шаг {self.step} - QR виден (вероятно, вышли из системы). Возможны ошибки ввода.",
                    2
                )
            except TimeoutException:
                self.output(f"Шаг {self.step} - QR не обнаружен; продолжаем.", 3)
    
        except Exception as e:
            self.output(f"Шаг {self.step} - Ошибка начальной загрузки: {e}", 1)
    
        self.increase_step()
    
        # --- Проверка заголовка чата (до 3 попыток), с промежуточным переходом на Google ---
        title_xpath = "(//div[@class='user-title']//span[contains(@class,'peer-title')])[1]"
        verified = False
        for attempt in range(1, 4):
            try:
                WebDriverWait(self.driver, 30).until(
                    EC.visibility_of_element_located((By.XPATH, title_xpath))
                )
                title = (self.monitor_element(title_xpath, 8, "Получение заголовка страницы") or "").strip()
                if title:
                    self.output(f"Шаг {self.step} - Текущий заголовок страницы: {title}", 3)
                    verified = True
                    break
                else:
                    self.output(f"Шаг {self.step} - Попытка {attempt}: элемент заголовка есть, но пустой.", 3)
            except TimeoutException:
                self.output(f"Шаг {self.step} - Попытка {attempt}: заголовок еще не виден.", 3)
                if self.settings.get('debugIsOn'):
                    self.debug_information("проверка заголовка приложения при загрузке telegram", "check")
    
            # Повторный переход для принудительного обновления deep link
            try:
                self.driver.get("https://www.google.com/")
                wait_ready(self.driver)
                self.driver.get(self.url)
                wait_ready(self.driver)
                time.sleep(3)
            except Exception as e:
                self.output(f"Шаг {self.step} - Ошибка повторного перехода перед попыткой {attempt+1}: {e}", 2)
    
        if not verified:
            self.output(
                "СТАТУС: Не удалось достичь игры после 3 попыток. "
                "Возможно, нужно вручную поднять игру в списке чатов Telegram.",
                1
            )
    
        # --- Продолжаем текущий поток ---
        self.increase_step()
    
        # Нажать START, если есть (некоторые чаты требуют для раскрытия темы)
        self.move_and_click("//button[contains(., 'START')]", 8, True,
                            "проверка кнопки старт (может отсутствовать)", self.step, "clickable")
        self.increase_step()
    
        # Найти или отправить рабочую deep-ссылку
        if self.find_working_link(self.step):
            self.increase_step()
        else:
            self.send_start(self.step)
            self.increase_step()
            self.find_working_link(self.step)
            self.increase_step()
    
        # Нажать 'Launch' в всплывающем окне, если есть
        self.move_and_click(
            "//button[contains(@class,'popup-button') and contains(.,'Launch')]",
            8, True, "нажать кнопку 'Launch' (вероятно отсутствует)", self.step, "clickable"
        )
        self.increase_step()
    
        # Патчим платформу и переключаемся в iframe игры
        self.replace_platform()
        self.select_iframe(self.step)
        self.increase_step()
    
        self.output(f"Шаг {self.step} - Подготовительные шаги завершены, передаем управление основному потоку…", 2)
        time.sleep(2)

    def replace_platform(self):
        # Вставьте код замены платформы здесь
        self.output(f"Шаг {self.step} - Пытаемся заменить платформу в URL iframe при необходимости...", 2)
        try:
            wait = WebDriverWait(self.driver, 20)
            # Находим контейнер div с указанным классом
            container = wait.until(EC.presence_of_element_located((By.CLASS_NAME, 'web-app-body')))
            # Находим iframe внутри контейнера
            iframe = container.find_element(By.TAG_NAME, "iframe")
            # Получаем src iframe
            iframe_url = iframe.get_attribute("src")

            if "tgWebAppPlatform=web" in iframe_url:
                # Заменяем 'tgWebAppPlatform=web' на нужную платформу
                iframe_url = iframe_url.replace("tgWebAppPlatform=web", f"tgWebAppPlatform={self.default_platform}")
                self.output(f"Шаг {self.step} - Параметр 'web' найден в URL iframe и заменен на '{self.default_platform}'.", 2)
                # Обновляем src iframe для перезагрузки
                self.driver.execute_script("arguments[0].src = arguments[1];", iframe, iframe_url)
            else:
                self.output("Шаг {self.step} - Параметр 'tgWebAppPlatform=web' не найден в URL iframe.", 2)
        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти iframe внутри контейнера 'web-app-body'.", 3)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка при попытке изменить URL iframe: {e}", 3)
        self.increase_step()

        # Ждем несколько секунд для перезагрузки
        time.sleep(5)


    def full_claim(self):
        # Должна быть ПЕРЕОПРЕДЕЛЕНА в дочернем классе
        self.output("Функция 'full_claim' не определена (требуется переопределение в дочернем классе) \n", 1)

    def select_iframe(self, old_step, iframe_id=None, iframe_container_class="web-app-body"):
        self.output(f"Шаг {self.step} - Пытаемся переключиться на iFrame приложения с id '{iframe_id}' или внутри '{iframe_container_class}'...", 2)

        try:
            wait = WebDriverWait(self.driver, 20)
            
            if iframe_id:
                # Пытаемся найти iframe по ID
                iframe = wait.until(EC.presence_of_element_located((By.ID, iframe_id)))
                self.driver.switch_to.frame(iframe)
                self.output(f"Шаг {self.step} - Успешно переключились на iframe с id '{iframe_id}'.", 3)
                if self.settings['debugIsOn']:
                    self.debug_information("успешно переключились на iFrame по id", "success")
            else:
                # Находим контейнер div с указанным классом
                container = wait.until(EC.presence_of_element_located((By.CLASS_NAME, iframe_container_class)))
                # Находим iframe внутри контейнера
                iframe = container.find_element(By.TAG_NAME, "iframe")
                # Переключаемся на iframe
                self.driver.switch_to.frame(iframe)
                self.output(f"Шаг {self.step} - Успешно переключились на iFrame приложения внутри '{iframe_container_class}'.", 3)
                if self.settings['debugIsOn']:
                    self.debug_information("успешно переключились на iFrame внутри контейнера", "success")

        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe с id '{iframe_id}' или внутри '{iframe_container_class}' за отведенное время.", 3)
            if self.settings['debugIsOn']:
                self.debug_information("таймаут при попытке переключения на iFrame", "error")
        except Exception:
            self.output(f"Шаг {self.step} - Произошла ошибка при попытке переключения на iframe с id '{iframe_id}' или внутри '{iframe_container_class}'.", 3)
            if self.settings['debugIsOn']:
                self.debug_information("неуказанная ошибка при переключении на iFrame", "error")

    def send_start(self, old_step):
        xpath = "//div[contains(@class, 'input-message-container')]/div[contains(@class, 'input-message-input')][1]"
        
        def attempt_send_start():
            chat_input = self.move_and_click(xpath, 5, False, "найти поле ввода сообщений чата", self.step, "present")
            if chat_input:
                self.increase_step()
                self.output(f"Шаг {self.step} - Пытаемся отправить команду '/start'...",2)
                chat_input.send_keys("/start")
                chat_input.send_keys(Keys.RETURN)
                self.output(f"Шаг {self.step} - Команда '/start' успешно отправлена.\n",3)
                if self.settings['debugIsOn']:
                    self.debug_information("отправлена команда start в окно чата","success")
                return True
            else:
                self.output(f"Шаг {self.step} - Не удалось найти поле ввода сообщений.\n",1)
                return False

        if not attempt_send_start():
            # Попытка не удалась, пробуем восстановить из резервной копии и повторить
            self.output(f"Шаг {self.step} - Пытаемся восстановить из резервной копии и повторить.\n",2)
            if self.restore_from_backup(self.backup_path):
                if not attempt_send_start():  # Повтор после восстановления
                    self.output(f"Шаг {self.step} - Повтор после восстановления не удался, не удалось отправить команду '/start'.\n",1)
            else:
                self.output(f"Шаг {self.step} - Восстановление из резервной копии не удалось или директория не существует.\n",1)

    def restore_from_backup(self, path):
        if os.path.exists(path):
            try:
                self.quit_driver()
                shutil.rmtree(self.session_path)
                shutil.copytree(path, self.session_path, dirs_exist_ok=True)
                self.driver = self.get_driver()
                self.driver.get(self.url)
                WebDriverWait(self.driver, 10).until(lambda d: d.execute_script('return document.readyState') == 'complete')
                self.output(f"Шаг {self.step} - Резервная копия успешно восстановлена.",2)
                return True
            except Exception as e:
                self.output(f"Шаг {self.step} - Ошибка при восстановлении резервной копии: {e}\n",1)
                return False
        else:
            self.output(f"Шаг {self.step} - Директория резервной копии не существует.\n",1)
            return False

    def move_and_click(self, xpath, wait_time, click, action_description, old_step, expectedCondition, attempts=5):
        """
        Ожидание элемента с общим таймаутом, повтор без вывода ошибок.
        При успехе возвращает WebElement (или None, если не кликает). При неудаче - None.
        """
        def timer():
            return random.randint(1, 3) / 10.0
    
        self.output(f"Шаг {self.step} - Пытаемся {action_description}...", 2)
    
        deadline = time.time() + float(wait_time)
        target_element = None
    
        # Помощник: получить элемент согласно ожидаемому условию с fallback (без логов).
        def wait_for_element(remaining):
            wait = WebDriverWait(self.driver, max(0.5, remaining))
            if expectedCondition == "visible":
                return wait.until(EC.visibility_of_element_located((By.XPATH, xpath)))
            elif expectedCondition == "present":
                return wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            elif expectedCondition == "invisible":
                wait.until(EC.invisibility_of_element_located((By.XPATH, xpath)))
                if self.settings.get('debugIsOn'):
                    self.debug_information(f"{action_description} оказался невидимым", "check")
                return None
            elif expectedCondition == "clickable":
                try:
                    return wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                except TimeoutException:
                    try:
                        return wait.until(EC.visibility_of_element_located((By.XPATH, xpath)))
                    except TimeoutException:
                        return wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
            else:
                return wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
    
        for attempt in range(1, attempts + 1):
            remaining = deadline - time.time()
            if remaining <= 0:
                break
    
            try:
                target_element = wait_for_element(remaining)
                if target_element is None:
                    # Путь 'invisible' успешен (нет клика/действия)
                    return None
    
                # Убедиться, что элемент в поле зрения; логируем один раз при скролле
                in_view = self.driver.execute_script("""
                    var elem = arguments[0], box = elem.getBoundingClientRect();
                    if (!(box.top >= 0 && box.left >= 0 &&
                          box.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
                          box.right  <= (window.innerWidth  || document.documentElement.clientWidth))) {
                        elem.scrollIntoView({block: 'center', inline: 'center'});
                        return false;
                    }
                    return true;
                """, target_element)
                if not in_view:
                    # низкий уровень шума
                    if self.settings.get('debugIsOn'):
                        self.debug_information(f"{action_description} был вне поля зрения и проскроллен", "info")
    
                # Защита от устаревания
                try:
                    _ = target_element.tag_name
                except StaleElementReferenceException:
                    try:
                        target_element = self.driver.find_element(By.XPATH, xpath)
                    except Exception:
                        # Повторить в пределах бюджета времени
                        time.sleep(0.1 + timer())
                        continue
    
                if click:
                    self.clear_overlays(target_element, self.step)
                    result = self._safe_click_webelement(target_element, action_description=action_description)
                    if result is not None:
                        if self.settings.get('debugIsOn'):
                            self.debug_information(f"Переместились и кликнули {action_description}", "success")
                        return target_element
                    # клик не удался; небольшой откат и повтор в пределах бюджета
                    time.sleep(0.2 + timer())
                    continue
                else:
                    if self.settings.get('debugIsOn'):
                        self.debug_information(f"Переместились к {action_description} без клика", "no click")
                    return target_element
    
            except TimeoutException:
                # тихий повтор в пределах общего бюджета
                continue
            except StaleElementReferenceException:
                # тихий повтор
                continue
            except Exception as e:
                if "has no size and location" in str(e):
                    self.output(f"Шаг {self.step} - Проблема с элементом при {action_description}: элемент некорректно расположен или размер равен нулю.", 1)
                    if self.settings.get('debugIsOn'):
                        self.debug_information(f"Фатальная ошибка при {action_description}: {str(e)}", "error")
                    return None
                # Нефатальная: повтор в пределах бюджета
                time.sleep(0.1 + timer())
                continue
    
        # Итоговый провал (одна строка)
        self.output(f"Шаг {self.step} - {action_description} не найден/не кликабелен после {attempts} попыток (~{wait_time}s).", 2)
        if self.settings.get('debugIsOn'):
            self.debug_information(f"{action_description} не найден после {attempts} попыток", "error")
        return None
    
    def _safe_click_webelement(self, elem, action_description=""):
        try:
            # Центрируем в области прокрутки
            self._center_in_scroll_parent(elem)
    
            # Ждем видимости, доступности и ненулевого размера
            WebDriverWait(self.driver, 5).until(EC.visibility_of(elem))
            WebDriverWait(self.driver, 5).until(lambda d: elem.is_enabled())
            WebDriverWait(self.driver, 5).until(
                lambda d: self.driver.execute_script(
                    "var r = arguments[0].getBoundingClientRect(); return (r.width>0 && r.height>0);", elem
                )
            )
    
            # Пробуем клик через ActionChains
            try:
                ActionChains(self.driver).move_to_element(elem).pause(0.05).click(elem).perform()
                if self.settings['debugIsOn']:
                    self.debug_information(f"ClickElem {action_description} - Клик ActionChains выполнен", "success")
                return elem
            except (MoveTargetOutOfBoundsException, ElementClickInterceptedException) as e1:
                self.output(f"Шаг {self.step} - Клик ActionChains не удался ({type(e1).__name__}). Пробуем JS…", 3)
                if self.settings['debugIsOn']:
                    self.debug_information(f"ClickElem {action_description} - AC неудача: {type(e1).__name__}", "warning")
    
            # Временно отключаем блокировщики над центром и пробуем JS клики
            blockers = self._temporarily_disable_blockers(elem)
            try:
                if self._js_click_variants(elem):
                    self.output(f"Шаг {self.step} - Использован JS клик для {action_description}.", 3)
                    if self.settings['debugIsOn']:
                        self.debug_information(f"ClickElem {action_description} - JS fallback успешен", "success")
                    return elem
            finally:
                self._restore_blockers(blockers)
    
            # Последняя попытка: центрируем и пробуем JS снова
            self._center_in_scroll_parent(elem)
            if self._js_click_variants(elem):
                self.output(f"Шаг {self.step} - JS клик fallback (вторая попытка) для {action_description}.", 3)
                if self.settings['debugIsOn']:
                    self.debug_information(f"ClickElem {action_description} - JS fallback #2 успешен", "success")
                return elem
    
            self.output(f"Шаг {self.step} - Все стратегии клика не удались для {action_description}.", 2)
            if self.settings['debugIsOn']:
                self.debug_information(f"ClickElem {action_description} - все стратегии неудачны", "error")
            return None
    
        except StaleElementReferenceException:
            self.output(f"Шаг {self.step} - Элемент устарел во время клика для {action_description}.", 2)
            if self.settings['debugIsOn']:
                self.debug_information(f"ClickElem {action_description} - устаревший элемент", "error")
            return None
        except Exception as e:
            self.output(f"Шаг {self.step} - Клик не удался: {type(e).__name__}: {e}", 2)
            if self.settings['debugIsOn']:
                self.debug_information(f"ClickElem {action_description} фатальная ошибка: {type(e).__name__}: {e}", "error")
            return None

    def click_element(self, xpath, timeout=30, action_description=""):
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            if self.settings['debugIsOn']:
                self.debug_information(f"ClickElem {action_description} - Элемент найден", "info")
            res = self._safe_click_webelement(element, action_description=action_description)
            return res is not None
        except TimeoutException:
            self.output(f"Шаг {self.step} - Элемент не найден за время ожидания: {xpath}. Пропускаем клик.", 2)
            if self.settings['debugIsOn']:
                self.debug_information(f"ClickElem {action_description} таймаут ожидания элемента", "error")
            return False
        except Exception as e:
            self.output(f"Шаг {self.step} - Ошибка во время {action_description}: {type(e).__name__}: {e}", 3)
            if self.settings['debugIsOn']:
                self.debug_information(f"ClickElem {action_description} фатальная ошибка: {str(e)}", "error")
            return False
    
        except (StaleElementReferenceException, Exception) as e:
            if "has no size and location" in str(e):
                self.output(f"Шаг {self.step} - Проблема с элементом при {action_description}: элемент некорректно расположен или размер равен нулю.", 1)
                if self.settings['debugIsOn']:
                    self.debug_information(f"ClickElem {action_description} фатальная ошибка: {str(e)}", "error")
                return False
            self.output(f"Шаг {self.step} - Ошибка во время {action_description}.", 3)
            if self.settings['debugIsOn']:
                self.debug_information(f"ClickElem {action_description} фатальная ошибка: {str(e)}", "error")
            return False

    def brute_click(self, xpath, timeout=30, action_description="", state_check=None, post_click_wait=0.6):
        """
        Брутфорс клик:
          1) Убедиться, что элемент присутствует и в поле зрения (пока без клика).
          2) Пробовать клик через ActionChains -> JS варианты -> временно отключить блокировщики и повторить ->
             кликнуть ближайшую кнопку -> финальный клик по координатам.
          3) После каждой попытки считать успешным, если:
               A) элемент исчез,
               B) state_check() возвращает True,
               C) изменился DOM-«подпись» элемента (outerHTML/id).
        Возвращает True при вероятном успехе, иначе False.
        """
    
        # ---- 0) Убедиться, что элемент присутствует и в поле зрения (без клика)
        if not self.move_and_click(
            xpath, 10, False,
            f"найти элемент для Brute Click ({action_description})",
            self.step, "clickable"
        ):
            self.output(f"Шаг {self.step} - Элемент не найден или не прокручивается: {xpath}", 2)
            if self.settings.get('debugIsOn'):
                self.debug_information(f"BruteClick locate failed: {action_description}", "error")
            return False
    
        end = time.time() + timeout
    
        def html_sig(el):
            """Легковесная подпись элемента для обнаружения изменений."""
            try:
                outer = self.driver.execute_script("return arguments[0].outerHTML.slice(0, 200);", el) or ""
                return (el.get_attribute("id") or "", outer)
            except Exception:
                return None
    
        def js_click_variants(el) -> bool:
            """Постепенно более реалистичные JS клики."""
            # a) Нативный element.click()
            try:
                self.driver.execute_script("arguments[0].click();", el)
                return True
            except Exception:
                pass
    
            # b) MouseEvent с всплытием
            try:
                self.driver.execute_script("""
                    const e = new MouseEvent('click', {bubbles:true, cancelable:true, composed:true, view:window});
                    arguments[0].dispatchEvent(e);
                """, el)
                return True
            except Exception:
                pass
    
            # c) Последовательность Pointer + mouse
            try:
                self.driver.execute_script("""
                    const el = arguments[0];
                    const hasPE = typeof window.PointerEvent === 'function';
                    function fireMouse(type, tgt){ tgt.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window})); }
                    if (hasPE) el.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, cancelable:true}));
                    fireMouse('mousedown', el);
                    if (hasPE) el.dispatchEvent(new PointerEvent('pointerup',   {bubbles:true, cancelable:true}));
                    fireMouse('mouseup', el);
                    fireMouse('click', el);
                """, el)
                return True
            except Exception:
                pass
    
            # d) Клик по центру через elementFromPoint
            try:
                self.driver.execute_script("""
                  const el = arguments[0];
                  const r  = el.getBoundingClientRect();
                  const x  = r.left + r.width/2;
                  const y  = r.top  + r.height/2;
                  const t  = document.elementFromPoint(x,y);
                  if (t) {
                    const e = new MouseEvent('click', {bubbles:true, cancelable:true, composed:true, view:window, clientX:x, clientY:y});
                    t.dispatchEvent(e);
                  } else if (el && el.click) {
                    el.click();
                  }
                """, el)
                return True
            except Exception:
                pass
    
            return False
    
        while time.time() < end:
            # ---- 1) (Пере)находим текущий элемент
            try:
                el = self.driver.find_element(By.XPATH, xpath)
            except Exception:
                # Если не найден в начале цикла, значит предыдущая попытка скорее всего удалась
                self.output(f"Шаг {self.step} - Клик успешен: элемент не найден перед попыткой.", 2)
                return True
    
            # ---- 2) Перед кликом: скролл, очистка оверлеев, запись подписи
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", el)
            except Exception:
                pass
            try:
                self.clear_overlays(el, self.step)
            except Exception:
                pass
    
            pre_sig = html_sig(el)
    
            # ---- 3) Цепочка попыток
            clicked = False
    
            # 3.1 Нативный клик (ActionChains)
            try:
                ActionChains(self.driver).move_to_element(el).pause(0.05).click(el).perform()
                clicked = True
            except Exception:
                # 3.2 JS варианты
                clicked = js_click_variants(el)
    
                # 3.3 Временно отключаем блокировщики и повторяем JS
                if not clicked:
                    blockers = None
                    try:
                        blockers = self._temporarily_disable_blockers(el)
                        clicked = js_click_variants(el)
    
                        # 3.4 Клик по ближайшему предку button
                        if not clicked:
                            try:
                                self.driver.execute_script("const b = arguments[0].closest('button'); if (b) b.click();", el)
                                clicked = True
                            except Exception:
                                pass
    
                        # 3.5 Финальный клик по координатам
                        if not clicked:
                            try:
                                self.driver.execute_script("""
                                    const el = arguments[0];
                                    const r  = el.getBoundingClientRect();
                                    const x  = r.left + r.width/2;
                                    const y  = r.top  + r.height/2;
                                    const t  = document.elementFromPoint(x,y) || el;
                                    function fire(type, tgt){
                                      tgt.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, clientX:x, clientY:y}));
                                    }
                                    if (typeof window.PointerEvent === 'function') {
                                      t.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, cancelable:true, clientX:x, clientY:y}));
                                    }
                                    fire('mousedown', t);
                                    if (typeof window.PointerEvent === 'function') {
                                      t.dispatchEvent(new PointerEvent('pointerup',   {bubbles:true, cancelable:true, clientX:x, clientY:y}));
                                    }
                                    fire('mouseup', t); fire('click', t);
                                """, el)
                                clicked = True
                            except Exception:
                                pass
                    finally:
                        try:
                            self._restore_blockers(blockers)
                        except Exception:
                            pass
    
            # ---- 4) Ждем реакцию UI
            time.sleep(post_click_wait)
    
            # ---- 5) Проверки успеха
            # A) Исчез ли элемент?
            try:
                self.driver.find_element(By.XPATH, xpath)
                still_there = True
            except NoSuchElementException:
                still_there = False
    
            if not still_there:
                self.output(f"Шаг {self.step} - BruteClick успешен: элемент исчез.", 3)
                return True
    
            # B) Проверка состояния через state_check?
            if callable(state_check):
                try:
                    if state_check():
                        self.output(f"Шаг {self.step} - BruteClick успешен: проверка состояния пройдена.", 3)
                        return True
                except Exception:
                    pass
    
            # C) Изменилась подпись DOM?
            try:
                el2 = self.driver.find_element(By.XPATH, xpath)
                post_sig = html_sig(el2)
            except Exception:
                self.output(f"Шаг {self.step} - BruteClick вероятный успех: элемент заменен и затем отсутствует.", 3)
                return True
    
            if pre_sig is not None and post_sig is not None and post_sig != pre_sig:
                self.output(f"Шаг {self.step} - BruteClick вероятный успех: изменился DOM.", 3)
                return True
    
            # Иначе небольшой откат и повтор
            time.sleep(0.1)
    
        self.output(f"Шаг {self.step} - Brute click превысил время ожидания без явного успеха. ({action_description})", 2)
        if self.settings.get('debugIsOn'):
            self.debug_information(f"BruteClick таймаут: {action_description}", "error")
        return False

    def clear_overlays(self, target_element, step):
        try:
            element_location = target_element.location_once_scrolled_into_view
            overlays = self.driver.find_elements(
                By.XPATH,
                "//*[contains(@style,'position: absolute') or contains(@style,'position: fixed')]"
            )
            overlays_cleared = 0
            for overlay in overlays:
                overlay_rect = overlay.rect
                if (overlay_rect['x'] <= element_location['x'] <= overlay_rect['x'] + overlay_rect['width'] and
                    overlay_rect['y'] <= element_location['y'] <= overlay_rect['y'] + overlay_rect['height']):
                    self.driver.execute_script("arguments[0].style.display = 'none';", overlay)
                    overlays_cleared += 1
            if overlays_cleared > 0:
                self.output(f"Шаг {step} - Удалено {overlays_cleared} перекрывающих элементов.", 3)
            return overlays_cleared
        except Exception as e:
            self.output(f"Шаг {step} - Ошибка при попытке очистить перекрытия: {e}", 1)
            return 0

    def _center_in_scroll_parent(self, elem):
        # Скроллит ближайшего прокручиваемого родителя или окно, чтобы центрировать элемент
        self.driver.execute_script("""
          function getScrollableParent(el){
            while (el && el !== document.body){
              const s = getComputedStyle(el);
              const oy = s.overflowY;
              if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) return el;
              el = el.parentElement;
            }
            return null;
          }
          const el = arguments[0];
          const p = getScrollableParent(el);
          if (p){
            const r = el.getBoundingClientRect();
            const pr = p.getBoundingClientRect();
            p.scrollTop += (r.top - pr.top) - (pr.height/2 - r.height/2);
            p.scrollLeft += (r.left - pr.left) - (pr.width/2 - r.width/2);
          } else {
            el.scrollIntoView({block:'center', inline:'center'});
          }
        """, elem)
    
    def _js_click_variants(self, elem):
        # 1) Нативный element.click()
        try:
            self.driver.execute_script("arguments[0].click();", elem)
            return True
        except Exception:
            pass
    
        # 2) MouseEvent (всплытие + composed) – ближе к реальному клику пользователя
        try:
            self.driver.execute_script("""
              const e = new MouseEvent('click', {
                bubbles: true, cancelable: true, composed: true, view: window
              });
              arguments[0].dispatchEvent(e);
            """, elem)
            return True
        except Exception:
            pass
    
        # 3) Последовательность Pointer + mouse (с composed)
        try:
            self.driver.execute_script("""
              const el = arguments[0];
              const hasPE = typeof window.PointerEvent === 'function';
              function fireMouse(type, tgt){
                tgt.dispatchEvent(new MouseEvent(type, {
                  bubbles: true, cancelable: true, composed: true, view: window
                }));
              }
              if (hasPE) el.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true, cancelable:true, composed:true}));
              fireMouse('mousedown', el);
              if (hasPE) el.dispatchEvent(new PointerEvent('pointerup',   {bubbles:true, cancelable:true, composed:true}));
              fireMouse('mouseup', el);
              fireMouse('click', el);
            """, elem)
            return True
        except Exception:
            pass
    
        # 4) Клик по центру через elementFromPoint (некоторые библиотеки требуют координаты)
        try:
            self.driver.execute_script("""
              const el = arguments[0];
              const r  = el.getBoundingClientRect();
              const x  = r.left + r.width/2;
              const y  = r.top  + r.height/2;
              const t  = document.elementFromPoint(x,y);
              if (t) {
                const e = new MouseEvent('click', {
                  bubbles:true, cancelable:true, composed:true, view:window, clientX:x, clientY:y
                });
                t.dispatchEvent(e);
              } else if (el && el.click) {
                el.click();
              }
            """, elem)
            return True
        except Exception:
            pass
    
        # 5) Если целевой внутренний элемент, пробуем кликнуть ближайшую кнопку
        try:
            self.driver.execute_script("""
              const el = arguments[0];
              const b = el.closest && el.closest('button');
              if (b) b.click();
            """, elem)
            return True
        except Exception:
            pass
    
        # 6) Фокус + ENTER как последний вариант (некоторые фреймворки привязывают обработчики клавиш)
        try:
            self.driver.execute_script("""
              const el = arguments[0];
              const b = el.closest && el.closest('button');
              const tgt = b || el;
              if (tgt && typeof tgt.focus === 'function') {
                tgt.setAttribute('tabindex','0');
                tgt.focus({preventScroll:true});
                const e = new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true});
                tgt.dispatchEvent(e);
                const e2 = new KeyboardEvent('keyup', {key:'Enter', code:'Enter', bubbles:true});
                tgt.dispatchEvent(e2);
              }
            """, elem)
            return True
        except Exception:
            pass
    
        return False
    
    def _temporarily_disable_blockers(self, elem):
        # Отключаем pointer events на элементах, перекрывающих центр цели.
        return self.driver.execute_script("""
          const el = arguments[0];
          const r = el.getBoundingClientRect();
          const cx = r.left + r.width/2;
          const cy = r.top + r.height/2;
    
          // Собираем элементы, находящиеся в точке клика
          const hidden = [];
          const seen = new Set();
          for (let i=0; i<20; i++){
            const top = document.elementFromPoint(cx, cy);
            if (!top || seen.has(top)) break;
            seen.add(top);
    
            if (top !== el && !el.contains(top)) {
              const cs = getComputedStyle(top);
              // Отключаем только если элемент визуально блокирует
              if (cs.pointerEvents !== 'none' && cs.visibility !== 'hidden' && cs.display !== 'none'){
                hidden.push([top, top.style.pointerEvents]);
                top.style.pointerEvents = 'none';
              }
            }
            // Если цель открыта, прекращаем
            if (document.elementFromPoint(cx, cy) === el) break;
          }
          return hidden;
        """, elem)
    
    def _restore_blockers(self, state):
        # Восстанавливаем pointer-events на ранее отключенных элементах
        if not state:
            return
        try:
            self.driver.execute_script("""
              const items = arguments[0];
              for (const [node, oldPE] of items){
                if (node && node.style) node.style.pointerEvents = oldPE || '';
              }
            """, state)
        except Exception:
            pass
    
    def _safe_click_webelement(self, elem, action_description=""):
        try:
            # 1) Центрируем в контейнере
            self._center_in_scroll_parent(elem)
    
            # 2) Ждем видимости, доступности и размера
            WebDriverWait(self.driver, 5).until(EC.visibility_of(elem))
            WebDriverWait(self.driver, 5).until(lambda d: elem.is_enabled())
            WebDriverWait(self.driver, 5).until(
                lambda d: self.driver.execute_script(
                    "var r = arguments[0].getBoundingClientRect(); return (r.width>0 && r.height>0);", elem
                )
            )
    
            # 3) Пробуем клик через ActionChains
            try:
                ActionChains(self.driver).move_to_element(elem).pause(0.05).click(elem).perform()
                return elem
            except (MoveTargetOutOfBoundsException, ElementClickInterceptedException):
                # Попробуем JS ниже
                pass
    
            # 4) Если что-то блокирует, временно отключаем блокировщики
            blockers = self._temporarily_disable_blockers(elem)
            try:
                if self._js_click_variants(elem):
                    self.output(f"Шаг {self.step} - Использован JS клик для {action_description}.", 3)
                    return elem
            finally:
                self._restore_blockers(blockers)
    
            # 5) Последняя попытка: центрируем и пробуем JS еще раз
            self._center_in_scroll_parent(elem)
            if self._js_click_variants(elem):
                self.output(f"Шаг {self.step} - JS клик fallback (вторая попытка) для {action_description}.", 3)
                return elem
    
            self.output(f"Шаг {self.step} - Все стратегии клика не удались для {action_description}.", 2)
            return None
    
        except StaleElementReferenceException:
            self.output(f"Шаг {self.step} - Элемент устарел во время клика для {action_description}.", 2)
            return None
        except Exception as e:
            self.output(f"Шаг {self.step} - Клик не удался: {type(e).__name__}: {e}", 2)
            return None

    def element_still_exists_by_id(self, element_id):
        """Проверяет, существует ли элемент по ID."""
        try:
            element = self.driver.find_element(By.ID, element_id)
            return element.is_displayed()
        except NoSuchElementException:
            return False

    def monitor_element(self, xpath, timeout=8, action_description="no description"):
        end_time = time.time() + timeout
        first_time = True
        if self.settings['debugIsOn']:
            self.debug_information(f"MonElem {action_description}","check")
        while time.time() < end_time:
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
                if first_time:
                    self.output(f"Шаг {self.step} - Найдено {len(elements)} элементов по XPath: {xpath} для {action_description}", 3)
                    first_time = False

                texts = [element.text.replace('\n', ' ').replace('\r', ' ').strip() for element in elements if element.text.strip()]
                if texts:
                    return ' '.join(texts)
            except (StaleElementReferenceException, TimeoutException, NoSuchElementException):
                pass
            except Exception as e:
                self.output(f"Произошла ошибка: {e}", 3)
                if self.settings['debugIsOn']:
                    self.debug_information(f"MonElem ошибка при {action_description}","error")
                return False
        return False

    def debug_information(self, action_description, error_type="error"):
        # Используем только первую строку, чтобы избежать полного стектрейса
        short_description = action_description.splitlines()[0]
    
        # Заменяем символы, которые могут повредить имя файла
        sanitized_description = re.sub(r'[\/\0\\\*\?\:\|\<\>\"\&\;\$~ ]', '-', short_description)
    
        # Ограничиваем длину имени файла
        max_filename_length = 50  # при необходимости изменить
        sanitized_description = sanitized_description[:max_filename_length]
    
        # Делаем скриншот, если элемент должен быть виден
        time.sleep(3)
        screenshot_path = f"{self.screenshots_path}/{self.step}_{sanitized_description}.png"
        self.driver.save_screenshot(screenshot_path)
    
        # Проверяем, есть ли "not" в скобках в описании; если да, пропускаем отладку
        if re.search(r'\(.*?not.*?\)', action_description, re.IGNORECASE):
            return
    
        # Сохраняем исходный HTML при ошибке
        if error_type == "error":
            page_source = self.driver.page_source
            page_source_path = f"{self.screenshots_path}/{self.step}_{sanitized_description}_page_source.html"
            with open(page_source_path, "w", encoding="utf-8") as f:
                f.write(page_source)

    def find_working_link(self, old_step, custom_xpath=None):
        # Используем custom_xpath, если задан, иначе self.start_app_xpath
        start_app_xpath = custom_xpath if custom_xpath is not None else self.start_app_xpath
        self.output(f"Шаг {self.step} - Пытаемся открыть ссылку для приложения: {start_app_xpath}...", 2)
    
        try:
            # Ждем появления элементов в DOM
            start_app_buttons = WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, start_app_xpath))
            )
    
            num_buttons = len(start_app_buttons)
            self.output(f"Шаг {self.step} - Найдено {num_buttons} подходящих ссылок.", 2)
    
            if num_buttons == 0:
                self.output(f"Шаг {self.step} - Кнопки не найдены по XPath: {start_app_xpath}\n", 1)
                if self.settings['debugIsOn']:
                    self.debug_information("find working link - кнопки не найдены", "error")
                return False
    
            # Перебираем кнопки в обратном порядке
            for idx in range(num_buttons - 1, -1, -1):  # Обратный порядок
                link_xpath = f"({start_app_xpath})[{idx + 1}]"  # Индексы XPath начинаются с 1
                self.output(f"Шаг {self.step} - Пытаемся кликнуть по ссылке {idx + 1}...", 2)
    
                # Используем move_and_click для видимости, скролла и клика
                if self.move_and_click(link_xpath, 10, True, "найти ссылку запуска игры", self.step, "clickable"):
                    self.output(f"Шаг {self.step} - Ссылка для запуска приложения успешно открыта.\n", 3)
                    if self.settings['debugIsOn']:
                        self.debug_information("успешно открыта ссылка запуска игры", "success")
                    return True
                else:
                    self.output(f"Шаг {self.step} - Ссылка {idx + 1} не кликабельна, переходим к следующей...", 2)
    
            # Если ни одна ссылка не сработала
            self.output(f"Шаг {self.step} - Ни одна из подходящих ссылок не была кликабельна.\n", 1)
            if self.settings['debugIsOn']:
                self.debug_information("нет рабочей ссылки на игру", "error")
            return False
    
        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти кнопку 'Open Wallet' в отведенное время.\n", 1)
            if self.settings['debugIsOn']:
                self.debug_information("таймаут при попытке открыть игру", "error")
            return False
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка при попытке открыть приложение: {e}\n", 1)
            if self.settings['debugIsOn']:
                self.debug_information("неуказанная ошибка при запуске игры", "error")
            return False

    def validate_seed_phrase(self, allowed_lengths=(12, 13)):
        """
        Запрашивает у пользователя фразу восстановления и валидирует её.
    
        - По умолчанию принимает 12 или 13 слов (настраивается allowed_lengths).
        - Нормализует ввод: приводит к нижнему регистру, убирает лишние пробелы, разбивает по пробелам.
        - Возвращает нормализованную фразу (слова через один пробел).
        """
        lengths_str = "/".join(str(n) for n in allowed_lengths)
    
        while True:
            prompt = f"Шаг {self.step} - Пожалуйста, введите вашу фразу восстановления из {lengths_str} слов"
            phrase_raw = (
                getpass.getpass(prompt + " (ввод скрыт): ")
                if self.settings.get('hideSensitiveInput')
                else input(prompt + " (ввод видим): ")
            )
    
            try:
                if not phrase_raw or not phrase_raw.strip():
                    raise ValueError("Фраза восстановления не может быть пустой.")
    
                # Нормализация: нижний регистр, обрезка, разделение по пробелам
                words = phrase_raw.strip().lower().split()
    
                # Проверка длины
                if len(words) not in allowed_lengths:
                    raise ValueError(
                        f"Фраза восстановления должна содержать ровно {lengths_str} слов (получено {len(words)})."
                    )
    
                # Проверка символов (только буквы)
                if not all(re.fullmatch(r"[a-z]+", w) for w in words):
                    raise ValueError("Фраза восстановления может содержать только буквы a–z.")
    
                # Успех: сохраняем нормализованную фразу
                self.seed_phrase = " ".join(words)
                return self.seed_phrase
    
            except ValueError as e:
                # Безопасность: не выводим саму фразу
                self.output(f"Ошибка: {e}", 1)

    # Запуск нового процесса PM2
    def start_pm2_app(self, script_path, app_name, session_name):
        interpreter_path = "venv/bin/python3"
        command = f"NODE_NO_WARNINGS=1 pm2 start {script_path} --name {app_name} --interpreter {interpreter_path} --watch {script_path} -- {session_name}"
        subprocess.run(command, shell=True, check=True)

    # Сохранение процесса PM2
    def save_pm2(self):
        command = f"NODE_NO_WARNINGS=1 pm2 save"
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        print(result.stdout)
        
    def backup_telegram(self):

        # Спрашиваем пользователя, хочет ли он сделать резервную копию директории Telegram
        backup_prompt = input("Хотите сделать резервную копию директории Telegram? (Y/n): ").strip().lower()
        if backup_prompt == 'n':
            self.output(f"Шаг {self.step} - Резервное копирование пропущено по выбору пользователя.", 3)
            return

        # Запрашиваем пользовательское имя файла
        custom_filename = input("Введите имя файла для резервной копии (оставьте пустым для значения по умолчанию): ").strip()

        # Определяем путь назначения резервной копии
        if custom_filename:
            backup_directory = os.path.join(os.path.dirname(self.session_path), f"Telegram:{custom_filename}")
        else:
            backup_directory = os.path.join(os.path.dirname(self.session_path), "Telegram")

        try:
            # Создаем директорию резервной копии и копируем содержимое
            if not os.path.exists(backup_directory):
                os.makedirs(backup_directory)
            shutil.copytree(self.session_path, backup_directory, dirs_exist_ok=True)
            self.output(f"Шаг {self.step} - Мы сделали резервную копию данных сессии на случай сбоя!", 3)
        except Exception as e:
            self.output(f"Шаг {self.step} - Упс, не удалось сделать резервную копию данных сессии! Ошибка: {e}", 1)

    def get_seed_phrase_from_file(self, screenshots_path):
        seed_file_path = os.path.join(screenshots_path, 'seed.txt')
        if os.path.exists(seed_file_path):
            with open(seed_file_path, 'r') as file:
                return file.read().strip()
        return None

    def show_time(self, time):
        hours = int(time / 60)
        minutes = time % 60
        if hours > 0:
            hour_str = f"{hours} час" if hours == 1 else f"{hours} часов"
            if minutes > 0:
                minute_str = f"{minutes} минута" if minutes == 1 else f"{minutes} минут"
                return f"{hour_str} и {minute_str}"
            return hour_str
        minute_str = f"{minutes} минута" if minutes == 1 else f"{minutes} минут"
        return minute_str

    def strip_html_and_non_numeric(self, text):
        """Удаляет HTML теги и оставляет только цифры и точки."""
        text = self.strip_html(text)
        text = self.strip_non_numeric(text)
        return text
    
    def strip_html(self, text):
        """Удаляет HTML теги."""
        clean = re.compile('<.*?>')
        return clean.sub('', text)
    
    def strip_non_numeric(self, text):
        """Оставляет только цифры и точки."""
        return re.sub(r'[^0-9.]', '', text)
    
    def apply_random_offset(self, unmodifiedTimer):
        # Вспомогательная функция форматирования минут в часы и минуты
        def format_time(minutes):
            hours = int(minutes) // 60
            mins = int(minutes) % 60
            time_parts = []
            if hours > 0:
                time_parts.append(f"{hours} час{'а' if hours != 1 else ''}")
            if mins > 0 or hours == 0:
                time_parts.append(f"{mins} минута{'ы' if mins != 1 else ''}")
            return ' '.join(time_parts)
    
        # Пытаемся преобразовать unmodifiedTimer в float, по умолчанию 60 при ошибке
        try:
            unmodifiedTimer = float(unmodifiedTimer)
        except Exception as e:
            self.output(
                f"Ошибка преобразования unmodifiedTimer в float: {str(e)}. Используется значение по умолчанию 60 минут.",
                2
            )
            unmodifiedTimer = 60.0
    
        if self.allow_early_claim:
            if self.settings['lowestClaimOffset'] <= self.settings['highestClaimOffset']:
                low = self.settings['lowestClaimOffset']
                high = self.settings['highestClaimOffset']
                self.output(
                    f"Шаг {self.step} - Выбираем случайное смещение между {low} и {high} минутами.",
                    3
                )
                self.random_offset = random.randint(low, high)
                modifiedTimer = unmodifiedTimer + self.random_offset
                self.output(
                    f"Шаг {self.step} - Случайное смещение применено: {self.random_offset} минут к исходному времени {unmodifiedTimer} минут.",
                    3
                )
                self.output(
                    f"Шаг {self.step} - Возвращаемое измененное время: {modifiedTimer} минут ({format_time(modifiedTimer)}).",
                    3
                )
                return int(modifiedTimer)
        else:
            if self.settings['lowestClaimOffset'] <= self.settings['highestClaimOffset']:
                # Исходные смещения
                original_low = self.settings['lowestClaimOffset']
                original_high = self.settings['highestClaimOffset']
                # Ограничиваем смещения минимумом 0
                capped_lowest = max(original_low, 0)
                capped_highest = max(original_high, 0)
                # Проверяем, были ли ограничения
                low_capped = capped_lowest != original_low
                high_capped = capped_highest != original_high
                # Формируем строки для вывода
                low_str = f"{capped_lowest}" + (" (ограничено)" if low_capped else "")
                high_str = f"{capped_highest}" + (" (ограничено)" if high_capped else "")
                self.output(
                    f"Шаг {self.step} - Выбираем случайное смещение между {low_str} и {high_str} минутами.",
                    3
                )
                if low_capped or high_capped:
                    self.output(
                        f"Шаг {self.step} - Смещения были ограничены до 0: lowestClaimOffset={low_str}, highestClaimOffset={high_str}",
                        3
                    )
                self.random_offset = random.randint(capped_lowest, capped_highest)
                modifiedTimer = unmodifiedTimer + self.random_offset
                self.output(
                    f"Шаг {self.step} - Случайное смещение применено к таймеру ожидания: {self.random_offset} минут ({format_time(self.random_offset)}).",
                    3
                )
                self.output(
                    f"Шаг {self.step} - Возвращаемое измененное время: {modifiedTimer} минут ({format_time(modifiedTimer)}).",
                    3
                )
                return int(modifiedTimer)
        # Если условия не выполнены, возвращаем исходное unmodifiedTimer
        return unmodifiedTimer

    def get_balance(self, balance_xpath, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3
        priority = max(self.settings['verboseLevel'], default_priority)
        balance_text = f'{prefix} БАЛАНС:'
        
        try:
            # Перемещаемся к элементу баланса
            # self.move_and_click(balance_xpath, 20, False, "переместиться к балансу", self.step, "visible")
            monitor_result = self.monitor_element(balance_xpath, 15, "получить баланс")
            
            # Резервный вариант, если ничего не получено
            if not monitor_result:
                self.output(f"Шаг {self.step} - monitor_element вернул пустое значение. Пробуем резервный метод для баланса...", priority)
                try:
                    elements = self.driver.find_elements(By.XPATH, balance_xpath)
                    fallback_texts = []
                    for el in elements:
                        text = self.driver.execute_script("return arguments[0].textContent;", el).strip()
                        if text:
                            fallback_texts.append(text)
                    if fallback_texts:
                        monitor_result = " ".join(fallback_texts)
                    else:
                        monitor_result = False
                except Exception as fallback_e:
                    self.output(f"Шаг {self.step} - Резервный метод не удался: {fallback_e}", priority)
                    monitor_result = False

            if monitor_result is False:
                self.output(f"Шаг {self.step} - Текст баланса не найден. Перезапускаем драйвер...", priority)
                self.quit_driver()
                self.launch_iframe()
                monitor_result = self.monitor_element(balance_xpath, 20, "получить баланс")
            
            # Очищаем и конвертируем результат
            element = self.strip_html_and_non_numeric(monitor_result)
            if element:
                balance_float = round(float(element), 3)
                self.output(f"Шаг {self.step} - {balance_text} {balance_float}", priority)
                return balance_float
            else:
                self.output(f"Шаг {self.step} - {balance_text} не найден или не является числом.", priority)
                return None
        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с '{prefix} Баланс:' не найден.", priority)
            return None
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)
            return None
        finally:
            self.increase_step()

    def get_wait_time(self, wait_time_xpath, step_number="108", beforeAfter="pre-claim"):
        try:
            self.output(f"Шаг {self.step} - Получаем время ожидания...", 3)
            
            # Перемещаемся к элементу таймера и получаем текст
            wait_time_text = self.monitor_element(wait_time_xpath, 20, "таймер клэйма")
            
            # Резервный вариант, если ничего не получено
            if not wait_time_text:
                self.output(f"Шаг {self.step} - monitor_element вернул пустое значение. Пробуем резервный метод для времени ожидания...", 3)
                try:
                    elements = self.driver.find_elements(By.XPATH, wait_time_xpath)
                    fallback_texts = []
                    for el in elements:
                        text = self.driver.execute_script("return arguments[0].textContent;", el).strip()
                        if text:
                            fallback_texts.append(text)
                    if fallback_texts:
                        wait_time_text = " ".join(fallback_texts)
                    else:
                        wait_time_text = False
                except Exception as fallback_e:
                    self.output(f"Шаг {self.step} - Резервный метод не удался: {fallback_e}", 3)
                    wait_time_text = False
    
            if wait_time_text:
                wait_time_text = wait_time_text.strip()
                self.output(f"Шаг {self.step} - Извлеченный текст времени ожидания: '{wait_time_text}'", 3)
                
                # Обновленные шаблоны для игнорирования предшествующего текста и явного формата часы-минуты
                patterns = [
                    r".*?(\d+)h\s*(\d+)m(?:\s*(\d+)(?:s|d))?",
                    r".*?(\d{1,2}):(\d{2})(?::(\d{2}))?"
                ]
                
                total_minutes = None
                for pattern in patterns:
                    match = re.search(pattern, wait_time_text)
                    if match:
                        groups = match.groups()
                        total_minutes = 0.0
                        if len(groups) == 3:
                            hours, minutes, seconds = groups
                            if hours:
                                total_minutes += int(hours) * 60
                            if minutes:
                                total_minutes += int(minutes)
                            if seconds:
                                total_minutes += int(seconds) / 60.0
                            if not any([hours, minutes, seconds]):
                                total_minutes = None
                        # Если совпадение с паттерном с двоеточием (часы и минуты, опционально секунды)
                        elif len(groups) == 2:
                            hours, minutes = groups
                            if hours:
                                total_minutes += int(hours) * 60
                            if minutes:
                                total_minutes += int(minutes)
                        if total_minutes is not None:
                            break
                
                if total_minutes is not None and total_minutes > 0:
                    total_minutes = round(total_minutes, 1)
                    self.output(f"Шаг {self.step} - Общее время ожидания в минутах: {total_minutes}", 3)
                    return total_minutes
                else:
                    self.output(f"Шаг {self.step} - Шаблон времени ожидания не совпал с текстом: '{wait_time_text}'", 3)
                    return False
            else:
                self.output(f"Шаг {self.step} - Текст времени ожидания не найден.", 3)
                return False
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 3)

            return False