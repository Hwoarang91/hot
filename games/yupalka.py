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

class YupalkaClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/yupalka.py"
        self.prefix = "Yupalka:"
        self.url = "https://web.telegram.org/k/#@YupLand_bot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.box_claim = "Никогда."
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.allow_early_claim = False
        self.start_app_xpath = "//div[contains(@class, 'new-message-bot-commands') and .//div[text()='Yupalka']]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='Yupalka']]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()  # Загрузить настройки перед инициализацией других атрибутов
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

        # Открыть драйвер и перейти к игре.
        self.launch_iframe()
        self.increase_step()

        # Получить исходный баланс до запроса
        original_balance = self.get_balance(True)
        self.increase_step()

        # Проверить, есть ли время ожидания
        remaining_wait_time = self.get_wait_time(self.step, False)
        self.increase_step()
        
        if remaining_wait_time:
            original_wait_time = remaining_wait_time
            modified_wait_time = self.apply_random_offset(original_wait_time)
            self.output(
                f"Шаг {self.step} - СТАТУС: Учитывая время ожидания {original_wait_time} минут и применяя смещение, мы будем спать {modified_wait_time} минут.", 
                1
            )
            return modified_wait_time

        # Запросить карту
        self.click_random_card()
        self.increase_step()

        # Получить новый баланс после запроса
        new_balance = self.get_balance(True)
        self.increase_step()

        balance_diff = None  # По умолчанию, если разницу баланса определить не удалось
        if new_balance:
            try:
                # Рассчитать разницу баланса
                balance_diff = float(new_balance) - float(original_balance)
                if balance_diff > 0:
                    self.output(f"Шаг {self.step} - Запрос увеличил баланс на {balance_diff}", 2)
            except Exception as e:
                self.output(f"Шаг {self.step} - Ошибка при расчёте разницы баланса: {e}", 2)
            self.output(f"Шаг {self.step} - Основная награда получена.", 1)
        else:
            self.output(f"Шаг {self.step} - Запрос выглядел корректным, но баланс не удалось проверить.", 2)
        self.increase_step()

        # Проверить, есть ли время ожидания (второе ожидание)
        remaining_wait_time = self.get_wait_time(self.step, False)
        self.increase_step()

        self.attempt_upgrade()

        # Обработка второго времени ожидания и вывод в зависимости от того, была ли рассчитана разница баланса
        if remaining_wait_time:
            original_wait_time = remaining_wait_time
            modified_wait_time = self.apply_random_offset(original_wait_time)

            if balance_diff is not None:
                # Разница баланса успешно рассчитана
                self.output(
                    f"СТАТУС: Запрос успешен, баланс увеличился на {balance_diff}. Мы будем спать {modified_wait_time} минут.", 
                    1
                )
            else:
                # Разницу баланса подтвердить не удалось
                self.output(
                    f"СТАТУС: Запрос выглядел корректным, но мы не смогли подтвердить изменение баланса. Мы будем спать {modified_wait_time} минут.", 
                    1
                )
            return modified_wait_time

        # Если времени ожидания нет, по умолчанию спать 60 минут
        self.output(f"СТАТУС: Мы не смогли подтвердить запрос. Давайте поспим 60 минут.", 1)
        return 60
        
    def click_random_card(self):
        # Определить базовый XPath для лицевой стороны карты
        card_front_xpath = "//div[@class='c-home__card-front']"

        # Использовать WebDriverWait для ожидания наличия элементов карт
        wait = WebDriverWait(self.driver, 15)

        try:
            # Ожидать, пока элементы, соответствующие XPath, не будут найдены
            card_elements = wait.until(EC.presence_of_all_elements_located((By.XPATH, card_front_xpath)))

            # Проверить, есть ли элементы карт
            if card_elements:
                # Подсчитать количество лицевых сторон карт (общее количество элементов)
                total_cards = len(card_elements)

                # Случайно выбрать карту (индекс с 0 для Selenium)
                chosen_card_index = random.randint(0, total_cards - 1)

                # Записать выбранную карту и попытаться кликнуть по ней
                self.output(f"Шаг {self.step} - Кликаем по карте {chosen_card_index + 1} из {total_cards}.", 2)

                # Выполнить клик по выбранной карте
                card_elements[chosen_card_index].click()

                return chosen_card_index + 1  # Возвращаем индекс с 1 для удобства логирования
            else:
                self.output(f"Шаг {self.step} - Лицевые стороны карт не найдены.", 2)
                return None

        except TimeoutException:
            # Обработать таймаут, если лицевые стороны карт не найдены в течение времени ожидания
            self.output(f"Шаг {self.step} - Лицевые стороны карт не найдены в течение времени ожидания.", 2)
            return None

        except Exception as e:
            # Обработать любые другие исключения
            self.output(f"Шаг {self.step} - Произошла ошибка при ожидании лицевых сторон карт.", 2)
            return None

    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3
        priority = max(self.settings['verboseLevel'], default_priority)
        
        balance_text = f"{prefix} БАЛАНС:"
        balance_xpath = "//div[@class='c-home__header-item-text']"  # Обновлённый XPath
    
        try:
            # Отслеживать элемент с новым XPath
            element = self.monitor_element(balance_xpath, 15, "получить баланс")
            if element:
                balance_str = element.strip()
                multiplier = 1
    
                # Заменить запятую на точку для правильного преобразования в float
                balance_str = balance_str.replace(',', '.')
    
                # Проверить сокращения и установить множитель соответственно
                if balance_str.endswith('K'):
                    multiplier = 1_000
                    balance_str = balance_str[:-1].strip()
                elif balance_str.endswith('M'):
                    multiplier = 1_000_000
                    balance_str = balance_str[:-1].strip()
                elif balance_str.endswith('B'):
                    multiplier = 1_000_000_000
                    balance_str = balance_str[:-1].strip()
    
                try:
                    balance_value = float(balance_str) * multiplier
                    self.output(f"Шаг {self.step} - {balance_text} {balance_value}", priority)
                    return balance_value
                except ValueError:
                    self.output(f"Шаг {self.step} - Не удалось преобразовать баланс '{balance_str}' в число.", priority)
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
                # Обновлённый XPath для тега <p>, содержащего время
                xpath = "//div[@class='c-home__timer']/p"
                element = self.monitor_element(xpath, 10, "получить таймер запроса")
                
                if element:
                    time_text = element.strip()  # Извлечь текст времени (например, "19:42:26")
                    hh, mm, ss = map(int, time_text.split(':'))  # Разделить время и преобразовать в целые числа
                    
                    # Преобразовать в общее количество минут
                    total_minutes = hh * 60 + mm + ss / 60
                    
                    self.output(f"Шаг {self.step} - Время ожидания {total_minutes:.2f} минут", 3)
                    return int(total_minutes)+1
                
                return False
            except Exception as e:
                self.output(f"Шаг {self.step} - Произошла ошибка при попытке {attempt}: {e}", 3)
                return False

        return False

    def attempt_upgrade(self):
        pass

def main():
    claimer = YupalkaClaimer()
    claimer.run()

if __name__ == "__main__":
    main()