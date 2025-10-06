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

class BlumClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/blum.py"
        self.prefix = "Blum:"
        self.url = "https://web.telegram.org/k/#@BlumCryptoBot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.seed_phrase = None
        self.forceLocalProxy = True
        self.forceRequestUserAgent = False
        self.allow_early_claim = False
        self.start_app_xpath = "//button[span[contains(text(), 'Запустить Blum')]]"
        self.start_app_menu_item = "//div[contains(@class, 'dialog-title')]//span[contains(text(), 'Blum')]"

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

        xpath = "//span[contains(text(), 'Ваши ежедневные награды')]"
        present = self.move_and_click(xpath, 20, False, "проверка ежедневной награды", self.step, "visible")
        self.increase_step()
        reward_text = None
        if present:
            xpath = "(//div[@class='count'])[1]"
            points = self.move_and_click(xpath, 10, False, "получить ежедневные очки", self.step, "visible")
            xpath = "(//div[@class='count'])[2]"
            days = self.move_and_click(xpath, 10, False, "получить количество подряд сыгранных дней", self.step, "visible")
            reward_text = f"Ежедневные награды: {points.text} очков и {days.text} дней."
            xpath = "//button[.//span[text()='Продолжить']]"
            self.move_and_click(xpath, 10, True, "нажать продолжить", self.step, "clickable")
            self.increase_step()

        xpath = "//button[.//div[text()='Продолжить']]"
        self.move_and_click(xpath, 10, True, "нажать продолжить", self.step, "clickable")
        self.increase_step()

        xpath = "//button[.//span[contains(text(), 'Начать фарминг')]][1]"
        self.move_and_click(xpath, 10, True, "нажать кнопку 'Начать фарминг' (может отсутствовать)", self.step, "clickable")
        # self.click_element(xpath)
        self.increase_step()

        self.get_balance(False)

        wait_time_text = self.get_wait_time(self.step, "до запроса") 

        if not wait_time_text:
            return 60

        if wait_time_text != self.pot_full:
            matches = re.findall(r'(\d+)([hm])', wait_time_text)
            remaining_wait_time = (sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches)) + self.random_offset
            if remaining_wait_time < 5 or self.settings["forceClaim"]:
                self.settings['forceClaim'] = True
                self.output(f"Шаг {self.step} - оставшееся время до запроса меньше случайного смещения, применяем: settings['forceClaim'] = True", 3)
            else:
                self.output(f"СТАТУС: Осталось {wait_time_text} и смещение {self.random_offset} минут - Пойдем поспим. {reward_text}", 1)
                return remaining_wait_time

        try:
            self.output(f"Шаг {self.step} - Время ожидания до запроса: {wait_time_text} и случайное смещение {self.random_offset} минут.", 1)
            self.increase_step()

            if wait_time_text == self.pot_full or self.settings['forceClaim']:
                try:
                    xpath = "//button[.//div[contains(text(), 'Запросить')]]"
                    self.move_and_click(xpath, 10, True, "нажать кнопку 'Запросить'", self.step, "clickable")
                    self.increase_step()

                    time.sleep(5)

                    xpath = "//button[.//span[contains(text(), 'Начать фарминг')]][1]"
                    self.move_and_click(xpath, 10, True, "нажать кнопку 'Начать фарминг'", self.step, "clickable")
                    self.increase_step()

                    self.output(f"Шаг {self.step} - Ждем 10 секунд для обновления итогов и таймера...", 3) 
                    time.sleep(10)
                    
                    wait_time_text = self.get_wait_time(self.step, "после запроса") 
                    matches = re.findall(r'(\d+)([hm])', wait_time_text)
                    total_wait_time = self.apply_random_offset(sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches))
                    self.increase_step()

                    self.get_balance(True)

                    if wait_time_text == self.pot_full:
                        self.output(f"Шаг {self.step} - Таймер ожидания все еще показывает: Заполнено.", 1)
                        self.output(f"Шаг {self.step} - Это значит, что запрос не удался или в игре задержка >4 минут.", 1)
                        self.output(f"Шаг {self.step} - Проверим через 1 час, если запрос не прошел, попробуем снова.", 2)
                    else:
                        self.output(f"СТАТУС: Время ожидания после запроса: {wait_time_text} и новый таймер = {total_wait_time} минут. {reward_text}", 1)
                    return max(60, total_wait_time)

                except TimeoutException:
                    self.output(f"СТАТУС: Время запроса истекло: Возможно, сайт завис? Попробуем снова через час.", 1)
                    return 60
                except Exception as e:
                    self.output(f"СТАТУС: Произошла ошибка при попытке запроса: {e}\nПодождем час и попробуем снова", 1)
                    return 60

            else:
                matches = re.findall(r'(\d+)([hm])', wait_time_text)
                if matches:
                    total_time = sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches)
                    total_time += 1
                    total_time = max(5, total_time) 
                    self.output(f"Шаг {self.step} - Еще не время запрашивать для этого кошелька. Ждем {total_time} минут до заполнения хранилища.", 2)
                    return total_time 
                else:
                    self.output(f"Шаг {self.step} - Не найдено данных о времени ожидания? Проверим снова через час.", 2)
                    return 60
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла непредвиденная ошибка: {e}", 1)
            return 60
        
    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        balance_text = f'{prefix} БАЛАНС:' if claimed else f'{prefix} БАЛАНС:'
        balance_xpath = f"//div[@class='balance']//div[@class='kit-counter-animation value']"

        try:
            balance_element = WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, balance_xpath))
            )

            if balance_element:
                char_elements = balance_element.find_elements(By.XPATH, ".//div[@class='el-char']")
                balance_part = ''.join([char.text for char in char_elements]).strip()
                
                self.output(f"Шаг {self.step} - {balance_text} {balance_part}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority) 

        self.increase_step()

    def get_wait_time(self, step_number="108", beforeAfter="pre-claim", max_attempts=1):
        for attempt in range(1, max_attempts + 1):
            try:
                self.output(f"Шаг {self.step} - Сначала проверяем, идет ли еще отсчет времени...", 3)
                xpath = "//div[@class='time-left']"
                wait_time_value = self.monitor_element(xpath, 10, "таймер ожидания заполнения")
                if wait_time_value:
                    return wait_time_value

                self.output(f"Шаг {self.step} - Затем проверяем, заполнен ли контейнер...", 3)
                xpath = "//button[.//div[contains(text(), 'Запросить')]]"
                pot_full_value = self.monitor_element(xpath, 10, "таймер ожидания заполненного контейнера")
                if pot_full_value:
                    return self.pot_full
                return False
            except Exception as e:
                self.output(f"Шаг {self.step} - Произошла ошибка при попытке {attempt}: {e}", 3)
                return False

        return False

def main():
    claimer = BlumClaimer()
    claimer.run()

if __name__ == "__main__":
    main()