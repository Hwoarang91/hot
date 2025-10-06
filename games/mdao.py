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

class MDAOClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/mdao.py"
        self.prefix = "MDAO:"
        self.url = "https://web.telegram.org/k/#@Mdaowalletbot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.start_app_xpath = "//div[contains(@class, 'new-message-bot-commands') and .//div[text()='Запустить приложение']]"
        self.start_app_menu_item = "//a[.//span[contains(@class,'peer-title')][normalize-space(.)='ZAVOD' or .//span[normalize-space(.)='ZAVOD']]]"
        self.balance_xpath = f"//div[@data-tooltip-id='balance']/div[1]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()
        self.random_offset = random.randint(min(self.settings['lowestClaimOffset'], 0), min(self.settings['highestClaimOffset'], 0))
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
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение заданного времени ожидания.", 1)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 1)

    def full_claim(self):

        def return_minutes(wait_time_text, random_offset=0):
            matches = re.findall(r'(\d+)([hms])', wait_time_text)
            total_minutes = 0
            for value, unit in matches:
                if unit == 'h':
                    total_minutes += int(value) * 60
                elif unit == 'm':
                    total_minutes += int(value)
                elif unit == 's':
                    total_minutes += int(value) / 60  # Конвертировать секунды в минуты
            remaining_wait_time = total_minutes
            return int(remaining_wait_time)

        self.step = "100"

        self.launch_iframe()
        
        xpath = "(//div[contains(normalize-space(.), 'CLAIM') and contains(@class,'sc-gtLWhw sc-egkSDF sc-iqyJx kvyHci jpUGsD jzBzGm')] )[1]"
        button = self.move_and_click(xpath, 20, True, "запросить приз (может отсутствовать)", self.step, "clickable")
        self.increase_step()

        self.get_balance(self.balance_xpath, False)

        remaining_wait_time = self.get_wait_time(self.step, "до запроса")

        if remaining_wait_time == "Заполнено":
            self.settings['forceClaim'] = True
            remaining_wait_time = 0
        elif not remaining_wait_time:
            return 30
        else:
            remaining_wait_time = return_minutes(remaining_wait_time)
            self.output(f"СТАТУС: Котел еще не заполнен, подождем {remaining_wait_time} минут.", 1)
            return remaining_wait_time

        self.increase_step()

        if int(remaining_wait_time) < 5 or self.settings["forceClaim"]:
            self.settings['forceClaim'] = True
            self.output(f"Шаг {self.step} - оставшееся время до запроса меньше случайного смещения, применяем: settings['forceClaim'] = True", 3)
        else:
            self.output(f"СТАТУС: Время ожидания {remaining_wait_time} минут и смещение {self.random_offset}.", 1)
            return remaining_wait_time + self.random_offset

        xpath = "//div[text()='CLAIM']/ancestor::div[@bgcolor]"
        button = self.move_and_click(xpath, 20, True, "перейти к кнопке запроса", self.step, "clickable")
        self.increase_step()
        xpath = "(//div[normalize-space()='CLAIM WITHOUT BONUS'])[last()]"
        button = self.move_and_click(xpath, 20, True, "подтвердить запрос без просмотра видео", self.step, "clickable")
        self.increase_step()

        self.get_balance(self.balance_xpath, True)
        self.get_profit_hour(True)

        remaining_wait_time = return_minutes(self.get_wait_time(self.step, "после запроса"))
        self.increase_step()
        self.attempt_upgrade()
        self.random_offset = random.randint(max(self.settings['lowestClaimOffset'], 0), max(self.settings['highestClaimOffset'], 0))
        self.output(f"СТАТУС: Время ожидания {remaining_wait_time} минут и смещение {self.random_offset}.", 1)
        return remaining_wait_time + self.random_offset

    def get_wait_time(self, step_number="108", beforeAfter="до запроса", max_attempts=1):
        for attempt in range(1, max_attempts + 1):
            try:
                self.output(f"Шаг {self.step} - проверяем, идет ли отсчет таймера...", 3)
                xpath = "//div[contains(text(),'h ') and contains(text(),'m ') and contains(text(),'s')]"
                pot_full_value = self.monitor_element(xpath, 15, "таймер запроса")
                if pot_full_value:
                    return pot_full_value
                else:
                    return "Заполнено"
            except Exception as e:
                self.output(f"Шаг {self.step} - Произошла ошибка при попытке {attempt}: {e}", 3)
                return False
        return False

    def get_profit_hour(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        # Формируем XPath для прибыли
        profit_text = f'{prefix} ПРИБЫЛЬ/ЧАС:'
        profit_xpath = "//div[contains(text(), 'в час')]"

        try:
            element = self.strip_non_numeric(self.monitor_element(profit_xpath,15,"прибыль в час"))
            # Проверяем, что элемент не None и обрабатываем прибыль
            if element:
                self.output(f"Шаг {self.step} - {profit_text} {element}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Прибыль/Час:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Ошибка для логирования
        
        self.increase_step()

    def attempt_upgrade(self):
        pass

def main():
    claimer = MDAOClaimer()
    claimer.run()

if __name__ == "__main__":
    main()