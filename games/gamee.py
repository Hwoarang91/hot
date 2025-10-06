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

class GameeClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/gamee.py"
        self.prefix = "Gamee:"
        self.url = "https://web.telegram.org/k/#@gamee"
        self.pot_full = "Заполнено"
        self.pot_filling = "Добыча"
        self.seed_phrase = None
        self.forceLocalProxy = True
        self.forceRequestUserAgent = False
        self.start_app_xpath = "//div[text()='Открыть приложение']"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()
        self.random_offset = random.randint(self.settings['lowestClaimOffset'], self.settings['highestClaimOffset'])
        super().__init__()

    def launch_iframe(self):
        super().launch_iframe()

        # Открыть вкладку в главном окне
        self.driver.switch_to.default_content()

        iframe = self.driver.find_element(By.TAG_NAME, "iframe")
        iframe_url = iframe.get_attribute("src")
        
        # Проверить, существует ли 'tgWebAppPlatform=' в URL iframe перед заменой
        if "tgWebAppPlatform=" in iframe_url:
            # Заменить 'web' и 'weba' на динамическую платформу
            iframe_url = iframe_url.replace("tgWebAppPlatform=web", f"tgWebAppPlatform={self.default_platform}")
            iframe_url = iframe_url.replace("tgWebAppPlatform=weba", f"tgWebAppPlatform={self.default_platform}")
            self.output(f"Платформа найдена и заменена на '{self.default_platform}'.", 2)
        else:
            self.output("Параметр tgWebAppPlatform не найден в URL iframe.", 2)

        self.driver.execute_script(f"location.href = '{iframe_url}'")

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
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение времени ожидания.",1)

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}",1)

    def full_claim(self):
        self.step = "100"
        self.launch_iframe()

        clicked_it = False

        status_text = ""

        # Попытка нажать кнопку 'Начать добычу'
        xpath = "//button[span[contains(text(), 'Start mining')]]"
        clicked = self.move_and_click(xpath, 8, True, "нажать кнопку 'Начать добычу'", self.step, "clickable")
        if clicked:
            self.output(f"Шаг {self.step} - Успешно нажата кнопка 'Начать добычу'.", 3)
            status_text = "Добыча начата"
        else:
            # Попытка нажать кнопку 'Заявить и начать'
            xpath = "//button[span[contains(text(), 'Claim & start')]]"
            clicked = self.move_and_click(xpath, 8, True, "нажать кнопку 'Заявить и начать'", self.step, "clickable")
            if clicked:
                self.output(f"Шаг {self.step} - Успешно нажата кнопка 'Заявить и начать'.", 3)
                status_text = "Добыча начата"
            else:
                # Проверить, идет ли добыча
                xpath = "//p[contains(text(), 'to claim')]"
                element_present = self.move_and_click(xpath, 8, False, "проверить, идет ли добыча", self.step, "clickable")
                if element_present:
                    self.output(f"Шаг {self.step} - Добыча идет: ДА.", 3)
                    status_text = "Добыча идет"
                else:
                    self.output(f"Шаг {self.step} - Кнопка 'Добыча' НЕ найдена.", 3)
                    status_text = "Кнопка 'Добыча' НЕ найдена"

        self.increase_step()

        wait_time = self.get_wait_time(self.step, "pre-claim")
        self.get_balance(True)


        xpath = "//div[contains(@href, 'wheel')]"
        self.move_and_click(xpath, 10, True, "нажать вкладку 'Колесо'", self.step, "clickable")
        xpath = "//button[.//text()[contains(., 'available')]]"
        success = self.move_and_click(xpath, 10, True, "крутить колесо", self.step, "clickable")
        if success:
            status_text += ". Бонус колеса получен"

        if wait_time is None:
            self.output(f"СТАТУС: {status_text} - Не удалось получить время ожидания. Следующая попытка через 60 минут", 2)
            return 60
        else:
            remaining_time = self.apply_random_offset(wait_time)
            self.output(f"СТАТУС: {status_text} - Следующая попытка через {self.show_time(remaining_time)}.", 1)
            return wait_time

    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        # Динамически настроить приоритет логирования
        priority = max(self.settings['verboseLevel'], default_priority)

        # Сформировать текст на основе до/после
        balance_text = f'{prefix} БАЛАНС:' if claimed else f'{prefix} БАЛАНС:'
        balance_xpath = "//p[@id='wat-racer-mining--bht-text']"

        try:
            element = self.strip_html_and_non_numeric(self.monitor_element(balance_xpath, 15, "получить баланс"))

            # Проверить, что элемент не None и обработать баланс
            if element:
                balance_float = float(element)
                self.output(f"Шаг {self.step} - {balance_text} {balance_float}", priority)
                return balance_float
            else:
                self.output(f"Шаг {self.step} - {balance_text} не найден или не числовой.", priority)
                return None

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с '{prefix} Баланс:' не найден.", priority)
            return None
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Ошибка как строка для логирования
            return None

        # Функция увеличения шага, предполагается, что обрабатывает логику следующего шага
        self.increase_step()

    def get_profit_hour(self, claimed=False):

        self.driver.execute_script("location.href = 'https://prizes.gamee.com/telegram/mining/26'")

        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        # Динамически настроить приоритет логирования
        priority = max(self.settings['verboseLevel'], default_priority)

        # Сформировать XPath для прибыли
        profit_text = f'{prefix} ПРИБЫЛЬ/ЧАС:'
        profit_xpath = "(//p[contains(@class, 'bXJWuE')])[1]"

        try:
            element = self.monitor_element(profit_xpath)
            if element:
                profit_part = self.strip_html_and_non_numeric(element)
                self.output(f"Шаг {self.step} - {profit_text} {profit_part}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с '{prefix} Прибыль/Час:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Ошибка как строка для логирования

        # Функция увеличения шага, предполагается, что обрабатывает логику следующего шага
        self.increase_step()

    def get_wait_time(self, step_number="108", beforeAfter="pre-claim"):
        try:
            self.output(f"Шаг {self.step} - Получение времени ожидания...", 3)

            # XPath для поиска элемента с временем ожидания
            xpath = "//p[contains(text(), 'to claim')]"
            wait_time_text = self.monitor_element(xpath, 10, "таймер ожидания")

            # Проверить, что wait_time_text не пустой
            if wait_time_text:
                wait_time_text = wait_time_text.strip()
                self.output(f"Шаг {self.step} - Извлечён текст времени ожидания: '{wait_time_text}'", 3)

                # Регулярное выражение для поиска чисел с 'h' или 'm', возможно с пробелами
                pattern = r'(\d+)\s*([hH]|hours?|[mM]|minutes?)'
                matches = re.findall(pattern, wait_time_text)

                total_minutes = 0
                if matches:
                    for value, unit in matches:
                        unit = unit.lower()
                        if unit.startswith('h'):
                            total_minutes += int(value) * 60
                        elif unit.startswith('m'):
                            total_minutes += int(value)
                    self.output(f"Шаг {self.step} - Общее время ожидания в минутах: {total_minutes}", 3)
                    return total_minutes if total_minutes > 0 else False
                else:
                    # Если шаблон не совпал, вернуть False
                    self.output(f"Шаг {self.step} - Шаблон времени ожидания не совпал с текстом: '{wait_time_text}'", 3)
                    return False
            else:
                # Текст не найден в элементе
                self.output(f"Шаг {self.step} - Текст времени ожидания не найден.", 3)
                return False
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 3)
            return False

def main():
    claimer = GameeClaimer()
    claimer.run()

if __name__ == "__main__":
    main()