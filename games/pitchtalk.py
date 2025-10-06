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

from claimer import Claimer

class PitchTalkClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/pitchtalk.py"
        self.prefix = "PitchTalk:"
        self.url = "https://web.telegram.org/k/#@pitchtalk_bot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.box_claim = "Никогда."
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.allow_early_claim = False
        self.start_app_xpath = "//div[contains(@class, 'new-message-bot-commands') and .//div[text()='Запустить']]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='PitchTalk']]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()  # Загрузить настройки перед инициализацией других атрибутов
        self.random_offset = random.randint(self.settings['lowestClaimOffset'], self.settings['highestClaimOffset'])
        super().__init__()

    def replace_platform(self):
        pass

    def next_steps(self):
        if self.step:
            pass
        else:
            self.step = "01"

        try:
            self.launch_iframe()
            self.increase_step()
            self.set_cookies()

        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение времени ожидания.", 1)

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 1)

    def full_claim(self):
        self.step = "100"

        # Открыть драйвер и перейти к игре.
        self.launch_iframe()
        self.increase_step()

        # Получить ежедневную награду
        xpath = "//button[text()='Продолжить']"
        self.move_and_click(xpath, 8, True, "проверка ежедневной награды (может отсутствовать)", self.step, "кликабельно")
        
        # Получить исходный баланс перед получением награды
        original_balance = self.get_balance(True)
        self.increase_step()
        
        # Мы фармим? если нет, начать!
        xpath = "//button[text()='Начать фарминг']"
        self.move_and_click(xpath, 8, True, "начальный запуск фарминга (может отсутствовать)", self.step, "кликабельно")

        # Проверить, есть ли время ожидания
        remaining_wait_time = self.get_wait_time(self.step, False)
        self.increase_step()
        
        if remaining_wait_time:
            original_wait_time = remaining_wait_time
            modified_wait_time = self.apply_random_offset(original_wait_time)
            self.output(
                f"Шаг {self.step} - СТАТУС: Рассматриваем время ожидания {original_wait_time} минут и применяем смещение, будем спать {modified_wait_time} минут.", 
                1
            )
            return modified_wait_time

        # Сделать основной клейм
        xpath = "//button[contains(text(), 'Получить')]"
        self.move_and_click(xpath, 8, True, "попытка сделать основной клейм", self.step, "кликабельно")
        
        # Мы фармим? если нет, начать!
        xpath = "//button[text()='Начать фарминг']"
        self.move_and_click(xpath, 8, True, "начать фарминг после клейма", self.step, "кликабельно")

        # Получить новый баланс после получения награды
        new_balance = self.get_balance(True)
        self.increase_step()

        balance_diff = None  # По умолчанию, если разницу баланса определить не удалось
        if new_balance:
            try:
                # Вычислить разницу баланса
                balance_diff = float(new_balance) - float(original_balance)
                if balance_diff > 0:
                    self.output(f"Шаг {self.step} - Получение награды увеличило баланс на {balance_diff}", 2)
            except Exception as e:
                self.output(f"Шаг {self.step} - Ошибка при вычислении разницы баланса: {e}", 2)
            self.output(f"Шаг {self.step} - Основная награда получена.", 1)
        else:
            self.output(f"Шаг {self.step} - Клейм выглядел корректным, но баланс не удалось проверить.", 2)
        self.increase_step()

        # Проверить, есть ли время ожидания (второе ожидание)
        remaining_wait_time = self.get_wait_time(self.step, False)
        self.increase_step()

        self.attempt_upgrade()

        # Обработка второго времени ожидания и вывод в зависимости от того, была ли вычислена разница баланса
        if remaining_wait_time:
            original_wait_time = remaining_wait_time
            modified_wait_time = self.apply_random_offset(original_wait_time)

            if balance_diff is not None:
                # Разница баланса успешно вычислена
                self.output(
                    f"СТАТУС: Клейм успешен, баланс увеличился на {balance_diff}. Будем спать {modified_wait_time} минут.", 
                    1
                )
            else:
                # Разницу баланса подтвердить не удалось
                self.output(
                    f"СТАТУС: Клейм выглядел корректным, но не удалось подтвердить изменение баланса. Будем спать {modified_wait_time} минут.", 
                    1
                )
            return modified_wait_time

        # Если времени ожидания нет, по умолчанию спать 60 минут
        self.output(f"СТАТУС: Не удалось подтвердить клейм. Спим 60 минут.", 1)
        return 60
        
    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3
        priority = max(self.settings['verboseLevel'], default_priority)
        
        balance_text = f"{prefix} БАЛАНС:"
        balance_xpath = "//div[@class='pitchtalk-points']/span"  # Обновлённый XPath
        
        try:
            # Отслеживать элемент с новым XPath
            element = self.monitor_element(balance_xpath, 15, "получить баланс")
            if element:
                balance_value = self.strip_html_and_non_numeric(element)
                
                try:
                    # Преобразовать в float напрямую, так как это просто число
                    balance_value = float(balance_value)
                    self.output(f"Шаг {self.step} - {balance_text} {balance_value}", priority)
                    return balance_value
                except ValueError:
                    self.output(f"Шаг {self.step} - Не удалось преобразовать баланс '{balance_value}' в число.", priority)
                    return None
            else:
                self.output(f"Шаг {self.step} - Элемент баланса не найден.", priority)
                return None
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", priority)
            return None

    def get_wait_time(self, step_number="108", beforeAfter="pre-claim", max_attempts=1):
        for attempt in range(1, max_attempts + 1):
            try:
                self.output(f"Шаг {self.step} - Получаем время ожидания...", 3)
                # Обновлённый XPath для соответствия тегу <p> с временем
                xpath = "//p[contains(text(), 'Получить через')]"
                element = self.monitor_element(xpath, 10, "получить таймер клейма")
                
                if element:
                    time_text = element.strip()  # Извлечь текст времени (например, "Получить через 05ч 58м")
                    
                    # Извлечь часы и минуты с помощью regex
                    match = re.search(r'(\d+)ч\s*(\d+)м', time_text)
                    if match:
                        hh = int(match.group(1))
                        mm = int(match.group(2))
                        
                        # Конвертировать в общее количество минут
                        total_minutes = hh * 60 + mm
                        
                        self.output(f"Шаг {self.step} - Время ожидания {total_minutes} минут", 3)
                        return total_minutes + 1
                
                return False
            except Exception as e:
                self.output(f"Шаг {self.step} - Произошла ошибка при попытке {attempt}: {e}", 3)
                return False

        return False

    def attempt_upgrade(self):
        pass

def main():
    claimer = PitchTalkClaimer()
    claimer.run()

if __name__ == "__main__":
    main()