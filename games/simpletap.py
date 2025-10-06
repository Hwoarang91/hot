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

class SimpleTapClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/simpletap.py"
        self.prefix = "SimpleTap:"
        self.url = "https://web.telegram.org/k/#@Simple_Tap_Bot"
        self.pot_full = "Заполнено"
        self.pot_filling = "Добыча"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.start_app_xpath = "//div[contains(@class, 'new-message-wrapper')]//div[contains(text(), 'Start')]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='Simple Coin']]"

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

        status_text = None  # Инициализировать status_text заранее

        try:
            # Новая кнопка для присоединения к "Bump"
            original_window = self.driver.current_window_handle
            xpath = "//*[text()='Start']"
            self.move_and_click(xpath, 8, True, "нажать кнопку 'Start' (может отсутствовать)", self.step, "clickable")

            # Вернуться к исходному окну, если открылось новое
            new_window = [window for window in self.driver.window_handles if window != original_window]
            if new_window:
                self.driver.switch_to.window(original_window)
        except TimeoutException:
            if self.settings['debugIsOn']:
                self.output(f"Шаг {self.step} - Кнопка 'Start' не найдена или новое окно не открыто.", 3)
        self.increase_step()

        opening_balance = self.get_balance(False)  # Запомнить начальный баланс

        # Собрать награду.
        xpath = "//div[contains(text(), 'Collect')]"
        self.move_and_click(xpath, 8, True, "нажать кнопку 'Collect' (может отсутствовать)", self.step, "clickable")

        # Фермерство
        xpath = "//div[contains(text(), 'Start farming')]"
        button = self.move_and_click(xpath, 8, False, "нажать кнопку 'Start farming'", self.step, "clickable")
        if button: 
            button.click()
            status_text = "СТАТУС: Начинаем фермерство"
        else:
            status_text = "СТАТУС: Уже фермерство"

        self.increase_step()

        closing_balance = self.get_balance(True)  # Запомнить конечный баланс

        try:
            # Преобразовать оба баланса в float и вычислить изменение баланса
            opening_balance = float(opening_balance)
            closing_balance = float(closing_balance)
            balance_increase = closing_balance - opening_balance

            # Обновить status_text в зависимости от изменения баланса
            if balance_increase > 0:
                status_text += f". Баланс увеличился на {balance_increase:.2f}"
            else:
                status_text += ". Увеличения баланса нет"
        except ValueError:
            # Обработка ошибок преобразования
            self.output("Ошибка при преобразовании балансов в число с плавающей точкой", 3)

        wait_time = self.get_wait_time(self.step, "pre-claim") 

        # Взять очки друзей
        xpath = "(//div[@class='appbar-tab'])[last()]"
        button = self.move_and_click(xpath, 8, False, "открыть вкладку 'Друзья'", self.step, "clickable")
        if button: button.click()

        xpath = "//div[contains(@class, 'claim-button')]"
        button = self.move_and_click(xpath, 8, False, "нажать кнопку 'Взять очки друзей'", self.step, "clickable")
        if button: 
            button.click()

            # Закрыть всплывающее окно поздравления
            xpath = "//div[contains(@class, 'invite_claimed-button')]"
            button = self.move_and_click(xpath, 8, False, "закрыть всплывающее окно 'Поздравляем'", self.step, "clickable")
            if button: button.click()
                
        self.increase_step()

        if wait_time is None:
            self.output(f"{status_text} - Не удалось получить время ожидания. Следующая попытка через 60 минут", 3)
            return 60
        else:
            self.output(f"{status_text} - Следующая попытка через {self.show_time(wait_time)}.", 2)
            return max(wait_time, 60)

    def get_balance(self, claimed=False):

        def strip_html_and_non_numeric(text):
            """Удалить HTML теги и оставить только цифры и десятичные точки."""
            # Удалить HTML теги
            clean = re.compile('<.*?>')
            text_without_html = clean.sub('', text)
            # Оставить только цифры и десятичные точки
            numeric_text = re.sub(r'[^0-9.]', '', text_without_html)
            return numeric_text

        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        # Динамически настроить приоритет логирования
        priority = max(self.settings['verboseLevel'], default_priority)

        # Сформировать XPath для баланса
        balance_text = f'{prefix} БАЛАНС:' if claimed else f'{prefix} БАЛАНС:'
        balance_xpath = "//div[contains(@class, 'home_balance')]"

        try:
            element = self.monitor_element(balance_xpath)

            # Проверить, что элемент не None и обработать баланс
            if element:
                cleaned_balance = strip_html_and_non_numeric(element)  # Убедиться, что получаем текст элемента
                self.output(f"Шаг {self.step} - {balance_text} {cleaned_balance}", priority)
                return cleaned_balance

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Вывести ошибку как строку для логирования

        # Функция увеличения шага, предполагается, что обрабатывает логику следующего шага
        self.increase_step()

    def get_wait_time(self, step_number="108", beforeAfter="pre-claim"):
        try:

            self.output(f"Шаг {self.step} - проверка истечения таймера...", 3)

            xpath = "//div[contains(@class, 'header_timer')]"
            wait_time = self.extract_time(self.strip_html_tags(self.monitor_element(xpath, 15)))

            self.output(f"Шаг {self.step} - Время ожидания {wait_time} минут.")

            return wait_time          

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 3)
            if self.settings['debugIsOn']:
                screenshot_path = f"{self.screenshots_path}/{self.step}_get_wait_time_error.png"
                self.driver.save_screenshot(screenshot_path)
                self.output(f"Скриншот сохранён в {screenshot_path}", 3)

            return None

    def extract_time(self, text):
        time_parts = text.split(':')
        if len(time_parts) == 3:
            try:
                hours = int(time_parts[0].strip())
                minutes = int(time_parts[1].strip())
                return hours * 60 + minutes
            except ValueError:
                return False
        return False
    
    def strip_html_tags(self, text):
        clean = re.compile('<.*?>')
        text_without_html = re.sub(clean, '', text)
        text_cleaned = re.sub(r'[^0-9:.]', '', text_without_html)
        return text_cleaned

    def show_time(self, time):
        hours = int(time / 60)
        minutes = time % 60
        if hours > 0:
            return f"{hours} часов и {minutes} минут"
        return f"{minutes} минут"

def main():
    claimer = SimpleTapClaimer()
    claimer.run()

if __name__ == "__main__":
    main()