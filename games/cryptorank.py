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
import requests

from claimer import Claimer


class CryptoRankClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/cryptorank.py"
        self.prefix = "CryptoRank:"
        self.url = "https://web.telegram.org/k/#@CryptoRank_app_bot"
        self.pot_full = "Заполнено"
        self.pot_filling = "для заполнения"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.allow_early_claim = False
        self.start_app_xpath = "//button[.//span[contains(text(),'Начать зарабатывать CR очки')]]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='CryptoRank Mini App']]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.daily_reward_text = ""
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

            self.check_opening_screens()

            self.set_cookies()

        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение времени ожидания.",1)

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}",1)

    def check_opening_screens(self):

        # Проверка начального экрана
        xpath = "//button[text()='Пропустить']"
        if self.move_and_click(xpath, 8, True, "начальный экран (может отсутствовать)", self.step, "кликабельно"):
            return True
        else:
            return False

    def full_claim(self):

        self.step = "100"
        self.launch_iframe()
        self.check_opening_screens()

        # Мы фармим? Если нет, начинаем!
        xpath = "//button[div[text()='Начать фарминг']]"
        self.move_and_click(xpath, 8, True, "начальный запуск фарминга (может отсутствовать)", self.step, "кликабельно")

        pre_balance = self.get_balance(False)
        self.increase_step()

        remaining_time = self.get_wait_time()
        if remaining_time:
            matches = re.findall(r'(\d+)([hm])', remaining_time)
            remaining_wait_time = sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches)
            remaining_wait_time = self.apply_random_offset(remaining_wait_time)
            self.output(f"СТАТУС: Учитывая {remaining_time}, мы будем спать {remaining_wait_time} секунд.",2)
            return remaining_wait_time

        self.increase_step()
    
        # Мы дошли до этого момента, так что попробуем заявить!
        xpath = "//button[div[contains(text(), 'Заявить')]]"
        success = self.move_and_click(xpath, 20, True, "поиск кнопки 'Заявить'.", self.step, "видимо")
        self.increase_step()

        # И снова начинаем фарминг.
        xpath = "//button[div[text()='Начать фарминг']]"
        self.move_and_click(xpath, 30, True, "начальный запуск фарминга (может отсутствовать)", self.step, "кликабельно")
        self.increase_step()

        # Проверяем баланс после заявки
        post_balance = self.get_balance(True)

        try:
            # Проверяем, что pre_balance и post_balance не None
            if pre_balance is not None and post_balance is not None:
                # Пытаемся преобразовать обе переменные в float
                pre_balance_float = float(pre_balance)
                post_balance_float = float(post_balance)
                if post_balance_float > pre_balance_float:
                    success_text = "Заявка успешна."
                else:
                    success_text = "Заявка могла не пройти."
            else:
                success_text = "Проверка заявки не удалась из-за отсутствия информации о балансе."
        except ValueError:
            success_text = "Проверка заявки не удалась из-за неверного формата баланса."


        self.increase_step()

        # Сохраняем время ожидания для дальнейшего использования
        remaining_time = self.get_wait_time()
        
        # Проверяем ежедневную награду.
        self.complete_daily_reward()
       
        # В конце подводим итог времени до следующего захода
        if remaining_time:
            matches = re.findall(r'(\d+)([hm])', remaining_time)
            remaining_wait_time = sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches)
            remaining_wait_time = self.apply_random_offset(remaining_wait_time)
            self.output(f"СТАТУС: {success_text} {self.daily_reward_text} Спим {remaining_time}.",2)
            return remaining_wait_time

        return 60
        
    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        balance_text = f'{prefix} БАЛАНС:' if claimed else f'{prefix} БАЛАНС:'
        balance_xpath = f"//img[contains(@src, 'crystal')]/following-sibling::span[last()]"

        try:
            element = self.monitor_element(balance_xpath, 15, "получить баланс")
            if element:
                balance_part = float(self.strip_html_and_non_numeric(element))
                self.output(f"Шаг {self.step} - {balance_text} {balance_part}", priority)
                return balance_part

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)

        self.increase_step()

    def get_wait_time(self, step_number="108", before_after="до заявки"):
        """
        Получает таймер “Получить после” (например, "01:15:12") без повторных попыток.
        Возвращает список подходящих WebElement, или False, если не найдено / ошибка.
        """
        self.output(f"Шаг {self.step} - [{before_after}] получение времени ожидания…", 3)
    
        xpath = (
            "//p"
            "[contains(normalize-space(.), 'Получить после')]"  # найти <p> с текстом “Получить после”
            "/span"                                             # затем его дочерний <span>
        )
    
        try:
            elements = self.monitor_element(xpath, timeout=10, description="получить таймер заявки")
            if elements:
                return elements
            self.output(f"Шаг {self.step} - Элемент таймера не найден.", 2)
        except Exception as e:
            self.output(f"Шаг {self.step} - Ошибка при получении времени ожидания: {e}", 1)
    
        return False

    def stake_coins(self):
        pass

    def complete_daily_reward(self):
        # Выбрать вкладку Задачи
        xpath = "//a[normalize-space(text())='Задачи']"
        self.move_and_click(xpath, 8, True, "клик по вкладке 'Задачи'", self.step, "кликабельно")

        # Проверить доступность ежедневной награды
        xpath = "//div[span[text()='Ежедневная проверка']]/following-sibling::div//button[normalize-space(text())='Заявить']"
        success = self.move_and_click(xpath, 8, True, "клик по кнопке 'Заявить' ежедневной награды", self.step, "кликабельно")
        if not success:
            self.output(f"Шаг {self.step} - Похоже, ежедневная награда уже была получена.", 2)
            self.daily_reward_text = "Ежедневная награда уже получена."

        xpath = "//button[div[text()='Отметиться']]"
        success = self.move_and_click(xpath, 8, True, "клик по кнопке 'Отметиться'", self.step, "кликабельно")
        if success:
            self.output(f"Шаг {self.step} - Похоже, мы успешно получили ежедневную награду.", 2)
            self.daily_reward_text = "Ежедневная награда получена."
        else:
            self.output(f"Шаг {self.step} - Похоже, ежедневная награда уже была получена или неудачна.", 2)
            self.daily_reward_text = "Ежедневная награда уже получена."

def main():
    claimer = CryptoRankClaimer()
    claimer.run()

if __name__ == "__main__":
    main()