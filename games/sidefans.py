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
from datetime import datetime, timedelta, timezone
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


class SideKickClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/sidefans.py"
        self.prefix = "SideFans:"
        self.url = "https://web.telegram.org/k/#@sidekick_fans_bot"
        self.pot_full = "Filled"
        self.pot_filling = "to fill"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.allow_early_claim = True
        self.start_app_xpath = "//div[contains(@class, 'new-message-bot-commands') and div[contains(@class, 'new-message-bot-commands-view') and text()='Play']]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='SideFans (By SideKick)']]"

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

            self.set_cookies()

        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение времени ожидания.", 1)

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 1)

    def full_claim(self):
        self.step = "100"

        self.launch_iframe()

        xpath = "//button[contains(text(), 'START')]"
        success = self.move_and_click(xpath, 25, True, "нажать кнопку 'START'", self.step, "clickable")
        self.increase_step()

        if success:
            xpath = "//button[contains(text(), 'Awesome!')]"
            next_button = self.move_and_click(xpath, 25, True, "нажать кнопку 'Awesome!'", self.step, "clickable")
            self.increase_step()

            xpath = "//button[contains(text(), 'CLAIM')]"
            next_button = self.move_and_click(xpath, 25, True, 'нажать кнопку "CLAIM"', self.step, "clickable")
            self.increase_step()

        # Получить исходный баланс до запроса
        original_balance = self.get_balance(False)
        self.increase_step()

        xpath = "//div[normalize-space(text()) = 'Pass']"
        self.move_and_click(xpath, 25, True, "нажать вкладку 'Pass'", self.step, "visible")
        self.increase_step()

        xpath = "//div[div[text()='Daily check-in']]/following-sibling::div//div[text()='GO']"
        self.move_and_click(xpath, 25, True, "нажать кнопку 'GO' для ежедневной проверки", self.step, "visible")
        self.increase_step()

        xpath = "//button[contains(text(), 'See you tomorrow')]"
        already_claimed = self.move_and_click(xpath, 10, False, "проверить, был ли уже получен запрос", self.step, "visible")
        if already_claimed:
            self.output("СТАТУС: Ежедневная награда уже получена", 1)
            return self.get_wait_time()
        self.increase_step()

        xpath = "//button[contains(text(), 'Claim')]"
        self.move_and_click(xpath, 25, True, "нажать кнопку 'Claim'", self.step, "clickable")
        self.increase_step()

        self.quit_driver()
        self.launch_iframe()

        # Получить новый баланс после запроса
        new_balance = self.get_balance(True)
        self.increase_step()

        balance_diff = None  # По умолчанию, если не удается определить разницу баланса
        if new_balance:
            try:
                # Вычислить разницу баланса
                balance_diff = float(new_balance) - float(original_balance)
                if balance_diff > 0:
                    self.output(f"СТАТУС: Запрос увеличил баланс на {balance_diff}", 1)
                    return self.get_wait_time()
            except Exception as e:
                self.output(f"Шаг {self.step} - Ошибка при вычислении разницы баланса: {e}", 2)
        self.output(f"СТАТУС: Не удалось подтвердить увеличение баланса после запроса, проверим снова через 2 часа.", 1)
        return 120

    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        priority = 2  # Всегда устанавливать 2

        balance_text = f"{prefix} БАЛАНС:"
        balance_xpath = "//div[text()='DIAMONDS']/preceding-sibling::span"

        attempts = 0
        max_attempts = 3

        while attempts < max_attempts:
            try:
                # Отслеживать элемент с новым XPath
                element = self.monitor_element(balance_xpath, 10, "получить баланс")
                if element:
                    balance_value = self.strip_html_and_non_numeric(element)

                    try:
                        # Преобразовать в float напрямую, так как это просто число
                        balance_value = float(balance_value)
                        self.output(f"Шаг {self.step} - {balance_text} {balance_value}", priority)

                        # Проверить, равен ли баланс 0, если да, повторить попытку до max_attempts
                        if balance_value == 0.0:
                            attempts += 1
                            self.output(f"Шаг {self.step} - Баланс равен 0.0, повторная попытка {attempts}/{max_attempts}", priority)
                            continue  # Повторить, если баланс 0.0
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

        # Если баланс оставался 0.0 после всех попыток
        self.output(f"Шаг {self.step} - Баланс оставался 0.0 после {max_attempts} попыток.", priority)
        return 0.0

    def get_wait_time(self, step_number="108", beforeAfter="pre-claim", max_attempts=1):
        current_time_utc = datetime.now(timezone.utc)

        # Рассчитать время начала и конца следующего дня (08:00 до 16:00)
        next_day_8am = (current_time_utc + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        next_day_4pm = (current_time_utc + timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)

        # Получить общее количество минут между 08:00 и 16:00
        minutes_range = int((next_day_4pm - next_day_8am).total_seconds() / 60)

        # Выбрать случайное количество минут в этом диапазоне
        random_minutes = random.randint(0, minutes_range)

        # Рассчитать случайное время между 08:00 и 16:00
        random_time = next_day_8am + timedelta(minutes=random_minutes)

        # Рассчитать количество минут от текущего времени до случайного времени
        time_to_random_time = int((random_time - current_time_utc).total_seconds() / 60)

        return time_to_random_time


def main():
    claimer = SideKickClaimer()
    claimer.run()


if __name__ == "__main__":
    main()