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
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, ElementClickInterceptedException
from datetime import datetime, timedelta
from selenium.webdriver.chrome.service import Service as ChromeService

import requests
import urllib.request
from claimer import Claimer

class SpellClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/christmas-raffle.py"
        self.prefix = "Xmas-Raffle:"
        self.url = "https://web.telegram.org/k/#@tapps_bot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.allow_early_claim = True
        self.start_app_xpath = "//div[@class='new-message-bot-commands-view' and contains(text(),'Apps Center')]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()
        self.random_offset = random.randint(self.settings['lowestClaimOffset'], self.settings['highestClaimOffset'])
        super().__init__()

    def next_steps(self):
        if self.step:
            pass
        else:
            self.step = "01"

        try:
            self.launch_iframe()
            self.increase_step()
            
            # Финальная уборка
            self.set_cookies()

        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение времени ожидания.", 1)

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 1)

    def full_claim(self):
        # Инициализация status_text
        status_text = ""

        # Запуск iframe
        self.step = "100"
        self.launch_iframe()

        # Захват баланса до запроса
        # before_balance = self.get_balance(False)

        # Перебор для сбора всех '%' и затем вращение колеса:
        xpath = "//button[contains(text(),'Next')]"
        if self.brute_click(xpath, 12, "нажать кнопку 'Далее'"):
            self.output(f"Шаг {self.step} - Кнопка(и) 'Далее' были доступны и нажаты.", 3)
            self.increase_step()
            
            xpath = "//button[contains(text(),'Done')]"
            self.brute_click(xpath, 12, "нажать кнопку 'Готово'")

        # Проверка количества дней в серии
        self.get_balance(False)
        self.increase_step()

        # Получение таймера ожидания, если он есть
        remaining_wait_time = self.get_wait_time(self.step, "после запроса")
        self.increase_step()
            
        if not remaining_wait_time:
            self.output(f"СТАТУС: Запрос не выполнен; нужно подождать до следующего шанса получить ежедневную награду.", 1)
            return 60 * 8 
            
        xpath = "//h1[contains(text(),'Complete day')]"
        self.move_and_click(xpath, 20, True, "проверка ежедневной награды", self.step, "доступно для клика")
        self.increase_step()
        
        xpath = "//span[contains(@class, 'styles_button') and text()='Open']"
        self.move_and_click(xpath, 20, True, "нажать кнопку 'открыть'", self.step, "доступно для клика")
        self.increase_step()
        
        # Теперь перейдем к кнопке "Отмена" и кликнем через JS
        xpath = "//button[contains(@class, 'popup-button') and contains(., 'Cancel')]"
        button = self.move_and_click(xpath, 8, True, "нажать кнопку 'Отмена'", self.step, "доступно для клика")
        self.increase_step()
        
        self.output(f"СТАТУС: Запрос выполнен; нужно подождать до следующего шанса получить ежедневную награду.", 1)
        return 60 * 8 

    def get_balance(self, claimed=False):
        prefix = "После серии из # дней" if claimed else "Перед серией из # дней"
        default_priority = 2 if claimed else 3
    
        # Динамическая настройка приоритета лога
        priority = max(self.settings.get('verboseLevel', default_priority), default_priority)
    
        # Формирование текста в зависимости от до/после
        balance_text = f'{prefix} БАЛАНС:'
        balance_xpath = "//h1[contains(text(),'Complete day')]"
    
        try:
            # Мониторинг элемента и проверка на валидность строки
            element = self.monitor_element(balance_xpath, 15, "получить баланс")
            if not element:
                self.output(f"Шаг {self.step} - Элемент {balance_text} не найден.", priority)
                return None
    
            # Удаление HTML и нечисловых символов, проверка валидности
            stripped_element = self.strip_html_and_non_numeric(element)
            if stripped_element is None or not stripped_element.isdigit():
                self.output(f"Шаг {self.step} - Элемент {balance_text} найден, но не числовой: '{element}'", priority)
                return None
    
            # Конвертация в целое число и вывод баланса
            balance_float = int(stripped_element)
            self.output(f"Шаг {self.step} - {balance_text} {balance_float}", priority)
            return balance_float
    
        except Exception as e:
            # Обработка общих исключений с понятными сообщениями об ошибках
            self.output(f"Шаг {self.step} - Произошла ошибка при получении баланса: {str(e)}", priority)
            return None
    
        finally:
            # Обеспечение увеличения шага даже при ошибке
            self.increase_step()
    
    def get_wait_time(self, step_number="108", beforeAfter="pre-claim"):
        try:
            self.output(f"Шаг {self.step} - Получение времени ожидания...", 3)
    
            # XPath для поиска span с определенным классом
            xpath = "//span[contains(@class, 'styles_footNote__A+ki8') and contains(text(), ':')]"
            wait_time_text = self.monitor_element(xpath, 10, "таймер запроса")
    
            # Проверка валидности wait_time_text
            if not wait_time_text:
                self.output(f"Шаг {self.step} - Текст времени ожидания не найден.", 3)
                return False
    
            wait_time_text = wait_time_text.strip()
            self.output(f"Шаг {self.step} - Извлеченный текст времени ожидания: '{wait_time_text}'", 3)
    
            # Регулярные выражения для форматов hh:mm:ss или mm:ss
            pattern_hh_mm_ss = r'^(\d{1,2}):(\d{2}):(\d{2})$'
            pattern_mm_ss = r'^(\d{1,2}):(\d{2})$'
    
            if re.match(pattern_hh_mm_ss, wait_time_text):
                hours, minutes, seconds = map(int, re.findall(r'\d+', wait_time_text))
                total_minutes = hours * 60 + minutes
                self.output(f"Шаг {self.step} - Общее время ожидания в минутах: {total_minutes}", 3)
                return total_minutes
            elif re.match(pattern_mm_ss, wait_time_text):
                minutes, seconds = map(int, re.findall(r'\d+', wait_time_text))
                self.output(f"Шаг {self.step} - Общее время ожидания в минутах: {minutes}", 3)
                return minutes
            else:
                self.output(f"Шаг {self.step} - Формат времени ожидания не распознан: '{wait_time_text}'", 3)
                return False
    
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка при получении времени ожидания: {str(e)}", 3)
            return False

def main():
    claimer = SpellClaimer()
    claimer.run()

if __name__ == "__main__":
    main()