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

class OxygenClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/oxygen.py"
        self.prefix = "Oxygen:"
        self.url = "https://web.telegram.org/k/#@oxygenminerbot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.box_claim = "Никогда."
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.allow_early_claim = False
        self.start_app_xpath = "//div[contains(@class, 'reply-markup-row')]//button[.//span[contains(text(), 'Start App')] or .//span[contains(text(), 'Play Now!')]]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='Oxygen Miner']]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()  # Загрузка настроек перед инициализацией других атрибутов
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
        self.increase_step()

        xpath = "//div[contains(text(),'Get reward')]"
        self.move_and_click(xpath, 10, True, "нажать на открывающую кнопку 'Получить награду' (может отсутствовать)", self.step, "clickable")
        self.increase_step()

        self.get_balance(False)
        self.increase_step()

        self.output(f"Шаг {self.step} - Последняя попытка получить счастливый бокс была {self.box_claim}.", 2)
        self.increase_step()

        wait_time_text = self.get_wait_time(self.step, "pre-claim")

        if not wait_time_text:
            return 60

        if wait_time_text != self.pot_full:
            matches = re.findall(r'(\d+)([hm])', wait_time_text)
            remaining_wait_time = (sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches))
            remaining_wait_time = self.apply_random_offset(remaining_wait_time)
            if remaining_wait_time < 5 or self.settings["forceClaim"]:
                self.settings['forceClaim'] = True
                self.output(f"Шаг {self.step} - оставшееся время до получения меньше случайного смещения, применяем: settings['forceClaim'] = True", 3)
            else:
                self.output(f"СТАТУС: Учитывая {wait_time_text}, мы снова ляжем спать на {remaining_wait_time} минут.", 1)
                return remaining_wait_time

        try:
            self.output(f"Шаг {self.step} - Время ожидания перед получением: {wait_time_text} и случайное смещение {self.random_offset} минут.", 1)
            self.increase_step()

            if wait_time_text == self.pot_full or self.settings['forceClaim']:
                try:
                    xpath = "//div[@class='farm_btn']"
                    button = self.brute_click(xpath, 10, "нажать кнопку 'Получить'")
                    self.increase_step()

                    self.output(f"Шаг {self.step} - Ждем 10 секунд для обновления итогов и таймера...", 3)
                    time.sleep(10)

                    wait_time_text = self.get_wait_time(self.step, "post-claim")
                    matches = re.findall(r'(\d+)([hm])', wait_time_text)

                    calculated_time = sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches)
                    random_offset = self.apply_random_offset(calculated_time)
                    total_wait_time = random_offset if random_offset > calculated_time else calculated_time

                    self.increase_step()
                    self.click_daily_buttons()
                    self.get_balance(True)
                    self.get_profit_hour(True)
                    self.increase_step()

                    self.output(f"Шаг {self.step} - проверяем наличие счастливых боксов...", 3)
                    xpath = "//div[@class='boxes_cntr']"
                    boxes = self.monitor_element(xpath,15,"счастливые боксы")
                    self.output(f"Шаг {self.step} - Обнаружено {boxes} боксов для получения.", 3)
                    if boxes:  # Проверка, что boxes не False
                        self.output(f"Шаг {self.step} - Обнаружено {boxes} боксов для получения.", 3)
                        if boxes.isdigit() and int(boxes) > 0:
                            xpath = "//div[@class='boxes_d_wrap']"
                            self.move_and_click(xpath, 10, True, "нажать кнопку боксов", self.step, "clickable")
                            xpath = "//div[@class='boxes_d_open' and contains(text(), 'Open box')]"
                            box = self.move_and_click(xpath, 10, True, "открыть бокс...", self.step, "clickable")
                            if box:
                                self.box_claim = datetime.now().strftime("%d %B %Y, %I:%M %p")
                                self.output(f"Шаг {self.step} - Дата и время получения бокса обновлены на {self.box_claim}.", 3)
                        else:
                            self.output(f"Шаг {self.step} - Не обнаружено валидное количество боксов или их количество равно нулю.", 3)
                    else:
                        self.output(f"Шаг {self.step} - Элементы боксов не найдены.", 3)
                        
                    if wait_time_text == self.pot_full:
                        self.output(f"СТАТУС: Таймер ожидания все еще показывает: Заполнено.", 1)
                        self.output(f"Шаг {self.step} - Это означает, что либо получение не удалось, либо в игре задержка.", 1)
                        self.output(f"Шаг {self.step} - Проверим через 1 час, обработался ли запрос, и если нет, попробуем снова.", 2)
                    else:
                        self.output(f"СТАТУС: Успешное получение: Следующее получение через {wait_time_text} / {total_wait_time} минут.", 1)
                    return max(60, total_wait_time)

                except TimeoutException:
                    self.output(f"СТАТУС: Время ожидания процесса получения истекло: Возможно, сайт завис? Повторим попытку через час.", 1)
                    return 60
                except Exception as e:
                    self.output(f"СТАТУС: Произошла ошибка при попытке получить: {e}\nПодождем час и попробуем снова", 1)
                    return 60

            else:
                matches = re.findall(r'(\d+)([hm])', wait_time_text)
                if matches:
                    total_time = sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches)
                    total_time += 1
                    total_time = max(5, total_time)
                    self.output(f"Шаг {self.step} - Еще не время получать для этого кошелька. Подождите {total_time} минут, пока хранилище не заполнится.", 2)
                    return total_time
                else:
                    self.output(f"Шаг {self.step} - Не найдено данных о времени ожидания? Проверим снова через час.", 2)
                    return 60
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла непредвиденная ошибка: {e}", 1)
            return 60
        
    def click_daily_buttons(self, wait_time=10, timeout=10):
        try:
            # Нажать первую кнопку
            xpath_first_button = "//div[@class='daily_btn_wrap']"
            self.move_and_click(xpath_first_button, timeout, True, "нажать 'daily_btn_wrap'", self.step, "clickable")

            # Нажать вторую кнопку
            xpath_second_button = "//div[@class='daily_get' and contains(text(), 'Get reward')]"
            self.move_and_click(xpath_second_button, timeout, True, "нажать 'Получить награду'", self.step, "clickable")

            # Проверить, была ли награда уже получена
            xpath_reward_message = "//div[contains(text(), 'You have already claimed this reward')]"
            if self.move_and_click(xpath_reward_message, timeout, False, "проверить, если уже получено", self.step, "visible"):
                self.output(f"Шаг {self.step} - Ежедневная награда уже получена.", 2)

            # Нажать закрыть
            xpath_close_button = "//div[@class='page_close']"
            self.move_and_click(xpath_close_button, timeout, True, "нажать закрыть вкладку", self.step, "clickable")

            return True

        except Exception as e:
            self.output(f"Ошибка при нажатии ежедневных кнопок: {e}", 1)
            return False
            
    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        balance_text = f'{prefix} БАЛАНС:'

        try:
            oxy_balance_xpath = "//span[@class='oxy_counter']"
            food_balance_xpath = "//div[@class='indicator_item i_food' and @data='food']/div[@class='indicator_text']"
            oxy_balance = float(self.monitor_element(oxy_balance_xpath,15,"баланс кислорода"))
            food_balance = float(self.monitor_element(food_balance_xpath,15,"баланс еды"))

            self.output(f"Шаг {self.step} - {balance_text} {oxy_balance:.0f} O2, {food_balance:.0f} еды", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)

        self.increase_step()

    def get_wait_time(self, step_number="108", beforeAfter="pre-claim", max_attempts=1):
        for attempt in range(1, max_attempts + 1):
            try:
                            
                # Шаг 1: Проверка кнопки "Собрать еду"
                xpath_collect = "//div[@class='farm_btn']"
                elements_collect = self.monitor_element(xpath_collect, 10, "проверка, заполнен ли горшок")
                if isinstance(elements_collect, str) and re.search(r"[СC]ollect food", elements_collect, re.IGNORECASE):
                    return self.pot_full
            
                # Шаг 2: Проверка элемента времени ожидания
                xpath_wait = "//div[@class='farm_wait']"
                elements_wait = self.monitor_element(xpath_wait, 10, "проверка оставшегося времени")
                if elements_wait:
                    return elements_wait
            
                return False
        
            except TypeError as e:
                self.output(f"Шаг {self.step} - Ошибка типа на попытке {attempt}: {e}", 3)
                return False
        
            except Exception as e:
                self.output(f"Шаг {self.step} - Произошла ошибка на попытке {attempt}: {e}", 3)
                return False

        return False

    def get_profit_hour(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        # Формируем XPath для прибыли
        profit_text = f'{prefix} ПРИБЫЛЬ/ЧАС:'
        profit_xpath = "//span[@id='oxy_coef']"

        try:
            element = self.strip_non_numeric(self.monitor_element(profit_xpath,15,"прибыль в час"))

            # Проверяем, что элемент не None и обрабатываем прибыль
            if element:
                element = float(element)*3600
                self.output(f"Шаг {self.step} - {profit_text} {element}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Прибыль/Час:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Ошибка в виде строки для логирования
        
        self.increase_step()

def main():
    claimer = OxygenClaimer()
    claimer.run()

if __name__ == "__main__":
    main()