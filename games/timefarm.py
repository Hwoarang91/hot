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
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, ElementClickInterceptedException, UnexpectedAlertPresentException
from datetime import datetime, timedelta
from selenium.webdriver.chrome.service import Service as ChromeService
from claimer import Claimer
import requests
from datetime import date
import urllib.request

class TimeFarmClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/timefarm.py"
        self.prefix = "TimeFarm:"
        self.url = "https://web.telegram.org/k/#@TimeFarmCryptoBot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.start_app_xpath = "//span[contains(text(), 'Открыть приложение')]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='Time Farm']]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()
        self.random_offset = random.randint(max(self.settings['lowestClaimOffset'], 0), max(self.settings['highestClaimOffset'], 0))
        super().__init__()

    def next_steps(self):

        if self.step:
            pass
        else:
            self.step = "01"

        try:
            self.launch_iframe()
            self.increase_step()

            cookies_path = f"{self.session_path}/cookies.json"
            cookies = self.driver.get_cookies()
            with open(cookies_path, 'w') as file:
                json.dump(cookies, file)

        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение времени ожидания.",1)

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}",1)

    def full_claim(self):

        self.step = "100"

        self.launch_iframe()
        xpath = "//div[@class='app-container']//div[@class='btn-text' and contains(., 'Claim')]"
        start_present = self.move_and_click(xpath, 8, False, "сделать заставку 'Claim' (может отсутствовать)", self.step, "clickable")
        self.increase_step()

        self.get_balance(False)
        self.increase_step()

        xpath = "//div[@class='farming-button-block'][.//span[text()='Start']]"
        start_present = self.move_and_click(xpath, 10, True, "нажать кнопку 'Start' (может отсутствовать)", self.step, "clickable")
        self.increase_step()

        xpath = "//div[@class='farming-button-block'][.//span[contains(text(), 'Claim')]]"
        success = self.move_and_click(xpath, 20, True, "искать кнопку claim (может отсутствовать)", self.step, "clickable")
        self.increase_step()
        if success:
            self.output(f"СТАТУС: Похоже, мы успешно нажали кнопку claim.",1)
        else:
            self.output(f"СТАТУС: Кнопка Claim в этот раз была недоступна для нажатия.",1)

        xpath = "//div[@class='farming-button-block'][.//span[text()='Start']]"
        self.move_and_click(xpath, 20, True, "нажать кнопку 'Start' (может отсутствовать)", self.step, "clickable")

        remaining_time = self.get_wait_time()
        self.increase_step()
        self.get_balance(True)
        # self.stake_coins()
        # self.claim_frens()
        # self.claim_oracle()
        if isinstance(remaining_time, (int, float)):
            return self.apply_random_offset(remaining_time)
        else:
            return 120
        
    def claim_frens(self):

        self.quit_driver()
        self.launch_iframe()

        # Перейти на вкладку 'Frens'
        FREN_TAB_XPATH = "//div[@class='tab-title' and text()='Frens']"
        if not self.move_and_click(FREN_TAB_XPATH, 20, True, "Переключиться на вкладку 'Frens'", self.step, "clickable"):
            self.increase_step()
            return
        self.increase_step()

        # Нажать кнопку 'Claim'        
        CLAIM_BUTTON_XPATH = "//div[@class='btn-text' and text()='Claim']"
        self.move_and_click(CLAIM_BUTTON_XPATH, 20, True, "Нажать кнопку 'Claim'", self.step, "clickable")
        self.increase_step()
            

    def navigate_to_date_input(self):
        # Шаг 1: Перейти на вкладку 'Earn'
        EARN_TAB_XPATH = "//div[@class='tab-title'][contains(., 'Earn')]"
        if not self.move_and_click(EARN_TAB_XPATH, 20, True, "Переключиться на вкладку 'Earn'", self.step, "clickable"):
            self.increase_step()
            return False

        self.increase_step()

        # Шаг 2: Нажать кнопку 'Oracle of Time'
        ORACLE_BUTTON_XPATH = "//div[contains(text(), 'Oracle of Time')]"
        if not self.move_and_click(ORACLE_BUTTON_XPATH, 20, True, "Нажать кнопку 'Oracle of Time'", self.step, "clickable"):
            self.increase_step()
            return False

        # Шаг 3: Проверить, был ли уже дан ответ
        CHECK_XPATH = "//div[contains(text(), 'You have already answered')]"
        if self.move_and_click(CHECK_XPATH, 10, True, "проверить, был ли уже дан ответ", self.step, "clickable"):
            self.increase_step()
            self.output(f"Шаг {self.step} - Вы уже ответили на сегодняшний Oracle of Time", 2)
            return False

        self.increase_step()
        return True

    def claim_oracle(self):
        # Шаги 1-3: Перейти в нужное место для ввода даты
        if not self.navigate_to_date_input():
            return

        # Шаг 4: Получить содержимое файла с GitHub с помощью urllib
        url = "https://raw.githubusercontent.com/thebrumby/HotWalletClaimer/main/extras/timefarmdaily"
        try:
            with urllib.request.urlopen(url) as response:
                content = response.read().decode('utf-8').strip()
            self.output(f"Шаг {self.step} - Получено содержимое с GitHub: {content}", 3)
        except Exception as e:
            self.output(f"Шаг {self.step} - Не удалось получить Oracle of Time с GitHub: {str(e)}", 2)
            return

        self.increase_step()

        # Шаг 4: Обработать содержимое как дату
        content = self.strip_non_numeric(content)
        if len(content) == 8 and content.isdigit():
            day = content[:2]
            month = content[2:4]
            year = content[4:]
            date_string = f"{day}{month}{year}"  # Формат 'ДДММГГГГ'
            self.output(f"Шаг {self.step} - Извлечена дата: {day}/{month}/{year}", 3)
        else:
            self.output(f"Шаг {self.step} - Содержимое не является корректной 8-значной датой: {content}", 2)
            return

        self.increase_step()

        # Шаг 5: Попытаться ввести дату сначала в формате 'дд/мм/гггг'
        if not self.enter_date(day, month, year, date_string, "dd/mm/yyyy"):
            self.output(f"Шаг {self.step} - Формат дд/мм/гггг не сработал. Повторная попытка с мм/дд/гггг.", 3)
            self.quit_driver()  # Закрыть драйвер
            time.sleep(5)  # Немного подождать перед повторным запуском
            self.launch_iframe()  # Перезапустить драйвер

            # Повторно перейти в нужное место
            if not self.navigate_to_date_input():
                return

            # Повторить ввод даты в формате 'мм/дд/гггг'
            if not self.enter_date(day, month, year, date_string, "mm/dd/yyyy"):
                self.output(f"Шаг {self.step} - Формат мм/дд/гггг тоже не сработал. Выход.", 2)
                return

        self.increase_step()

        # Шаг 6: Перейти на вкладку 'checkzedate'
        CHECKDATE_XPATH = "//div[text()='Check the date']"
        self.move_and_click(CHECKDATE_XPATH, 10, True, "проверить правильность даты", self.step, "clickable")

        TRYAGAIN_XPATH = "//div[text()='Try again']"
        failure = self.move_and_click(TRYAGAIN_XPATH, 10, True, "проверить ошибку завершения", self.step, "clickable")
        if not failure:
            CLAIM_XPATH = "//div[contains(text(),'Claim')]"
            self.move_and_click(CLAIM_XPATH, 10, True, "заявить после успеха", self.step, "clickable")
            self.output(f"Шаг {self.step} - Oracle of Time подтверждён как завершённый.", 2)
        else:
            self.output(f"Шаг {self.step} - Дата oracle of time была неверной для текущей головоломки.", 3)

    def enter_date(self, day, month, year, date_string, date_format):
        DATE_XPATH = "//input[@name='trip-start']"
        TRYAGAIN_XPATH = "//div[text()='Try again']"
        CHECKDATE_XPATH = "//div[text()='Check the date']"
    
        try:
            trip_start_field = self.move_and_click(DATE_XPATH, 10, True, "нажать на выбор даты", self.step, "clickable")
            trip_start_field.clear()  # Очистить любое предыдущее значение в поле
            self.increase_step()

            if date_format == "dd/mm/yyyy":
                # Сначала день
                self.output(f"Шаг {self.step} - Пробуем формат дд/мм/гггг", 3)
                self.output(f"Шаг {self.step} - Вводим день: {day}", 3)
                trip_start_field.send_keys(day)
                time.sleep(1)
                self.output(f"Шаг {self.step} - Вводим месяц: {month}", 3)
                trip_start_field.send_keys(month)
            else:
                # Сначала месяц
                self.output(f"Шаг {self.step} - Пробуем формат мм/дд/гггг", 3)
                self.output(f"Шаг {self.step} - Вводим месяц: {month}", 3)
                trip_start_field.send_keys(month)
                time.sleep(1)
                self.output(f"Шаг {self.step} - Вводим день: {day}", 3)
                trip_start_field.send_keys(day)

            # Ввод года
            time.sleep(1)
            self.output(f"Шаг {self.step} - Вводим год: {year}", 3)
            trip_start_field.send_keys(year)
        
            # Подтвердить ввод даты
            time.sleep(2)
            self.move_and_click(CHECKDATE_XPATH, 10, True, "подтвердить дату", self.step, "visible")
            self.output(f"Шаг {self.step} - Дата успешно отправлена в формате {date_format}: {date_string[:2]}/{date_string[2:4]}/{date_string[4:]}", 3)

            # Проверить наличие кнопки "Попробовать снова", что указывает на ошибку
            if self.move_and_click(TRYAGAIN_XPATH, 10, True, "проверить, был ли ответ неверным", self.step, "visible"):
                self.output(f"Шаг {self.step} - Обнаружена кнопка 'Попробовать снова'. Формат даты {date_format} был неверным.", 2)
                return False  # Запустить повторную попытку

            return True  # Успех

        except Exception as e:
            self.output(f"Шаг {self.step} - Ошибка при отправке даты: {str(e)}", 2)
            return False  # Ошибка


    def get_balance(self, claimed=False):

        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        # Динамически настроить приоритет логирования
        priority = max(self.settings['verboseLevel'], default_priority)

        # Сформировать конкретный XPath баланса
        balance_text = f'{prefix} БАЛАНС:' if claimed else f'{prefix} БАЛАНС:'
        balance_xpath = f"//div[@class='balance']"
        try:
            balance_part = self.monitor_element(balance_xpath)
            # Удалить любые HTML теги и нежелательные символы
            balance_part = "$" + self.strip_html_tags(balance_part)
            # Проверить, что элемент не None и обработать баланс
            self.output(f"Шаг {self.step} - {balance_text} {balance_part}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Вывести ошибку в лог

    def strip_html_tags(self, text):
        """Удалить HTML теги, переносы строк и лишние пробелы из строки."""
        clean = re.compile('<.*?>')
        text_without_html = re.sub(clean, '', text)
        # Удалить все символы, кроме цифр, двоеточий и пробелов (пробелы пока оставить)
        text_cleaned = re.sub(r'[^0-9: ]', '', text_without_html)
        # Удалить пробелы
        text_cleaned = re.sub(r'\s+', '', text_cleaned)
        return text_cleaned

    def extract_time(self, text):
        """Извлечь время из очищенного текста и преобразовать в минуты."""
        time_parts = text.split(':')
        if len(time_parts) == 3:
            try:
                hours = int(time_parts[0].strip())
                minutes = int(time_parts[1].strip())
                # Предполагается, что секунды не нужны для подсчёта минут
                # seconds = int(time_parts[2].strip())
                return hours * 60 + minutes
            except ValueError:
                return "Неизвестно"
        return "Неизвестно"

    def get_wait_time(self, step_number="108", beforeAfter="pre-claim", max_attempts=1):

        for attempt in range(1, max_attempts + 1):
            try:
                self.output(f"Шаг {self.step} - проверяем, идёт ли обратный отсчёт...", 3)
                xpath = "//table[@class='scroller-table']"
                pot_full_value = self.monitor_element(xpath, 15)
                
                # Удалить любые HTML теги и нежелательные символы
                pot_full_value = self.strip_html_tags(pot_full_value)
                
                # Преобразовать в минуты
                wait_time_in_minutes = self.extract_time(pot_full_value)
                return wait_time_in_minutes
            except Exception as e:
                self.output(f"Шаг {self.step} - Произошла ошибка при попытке {attempt}: {e}", 3)
                return "Неизвестно"

        # Если все попытки неудачны         
        return "Неизвестно"

    def stake_coins(self):
        pass

def main():
    claimer = TimeFarmClaimer()
    claimer.run()

if __name__ == "__main__":
    main()