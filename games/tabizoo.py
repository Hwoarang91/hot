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

class TabizooClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/tabizoo.py"
        self.prefix = "TabiZoo:"
        self.url = "https://web.telegram.org/k/#@tabizoobot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.box_claim = "Никогда."
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.allow_early_claim = False
        self.start_app_xpath = "//div[contains(@class, 'new-message-bot-commands') and .//div[text()='Start']]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='TabiZoo']]"

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
            self.check_initial_screens()
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
    
        # Проверить начальные экраны.
        self.check_initial_screens()
        self.increase_step()
    
        # Проверить ежедневные награды.
        self.click_daily_reward()
        self.increase_step()
    
        original_balance = self.get_balance(False)
        self.increase_step()
    
        xpath = "//span[contains(text(), 'Claim')]"
        success = self.brute_click(xpath, 10, "нажать кнопку 'Получить'")
        old_balance = self.get_balance(True)
        if success:
            try:
                balance_diff = float(old_balance) - float(original_balance)
                if balance_diff > 0:
                    self.output(f"Шаг {self.step} - Получение награды увеличило баланс на {balance_diff}", 2)
            except Exception as e:
                pass
            self.output(f"Шаг {self.step} - Основная награда получена.", 1)
        self.increase_step()
    
        # Получить прибыль в час для логирования (если нужно)
        self.get_profit_hour(True)
    
        try:
            # Получить время ожидания в минутах напрямую из новой функции.
            wait_time_minutes = self.get_wait_time(self.step, "post-claim")
            
            # Попробовать игру в слоты.
            self.play_spins()
            balance = self.get_balance(True)
            try:
                balance_diff = float(balance) - float(old_balance)
                if balance_diff > 0:
                    self.output(f"Шаг {self.step} - Игра в слоты увеличила баланс на {balance_diff}", 2)
            except Exception as e:
                pass
    
            # Вернуться на главную страницу.
            xpath = "(//div[normalize-space(.) = 'Shiro'])[1]"
            self.move_and_click(xpath, 10, True, "нажать вкладку 'Главная'", self.step, "clickable")
    
            # Попытаться повысить уровень, если включено автообновление.
            self.attempt_upgrade(balance)
    
            if wait_time_minutes:
                wait_time_minutes = self.apply_random_offset(wait_time_minutes)
                self.output(f"СТАТУС: Мы собираемся снова уснуть на {wait_time_minutes:.2f} минут.", 1)
                return wait_time_minutes
    
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла непредвиденная ошибка: {e}", 1)
            return 60
    
        self.output(f"СТАТУС: Похоже, мы дошли до конца без подтверждения действия!", 1)
        return 60

    def play_spins(self):
        return
        xpath_spin_tab = "(//div[normalize-space(.) = 'Spin'])[1]"
        xpath_spin_button = "//img[contains(@src, 'spin_btn')]"

        # Попытка нажать вкладку 'Spin'
        success = self.move_and_click(xpath_spin_tab, 10, True, "нажать вкладку 'Spin'", self.step, "clickable")
        if not success:
            self.quit_driver()
            self.launch_iframe()
            success = self.brute_click(xpath_spin_tab, 10, "нажать вкладку 'Spin'")
            if not success:
                self.output(f"Шаг {self.step} - Похоже, последовательность для игры в слот не удалась.", 2)
                return

        self.brute_click(xpath_spin_button, 60, "крутить барабаны")
        
    def click_daily_reward(self):
        # Проверить ежедневные награды.
        xpath = "//div[contains(@class, 'bg-[#FF5C01]') and contains(@class, 'rounded-full') and contains(@class, 'w-[8px]') and contains(@class, 'h-[8px]')]"
        success = self.move_and_click(xpath, 10, False, "проверить, можно ли получить ежедневную награду (может отсутствовать)", self.step, "clickable")
        if not success:
            self.output(f"Шаг {self.step} - Похоже, ежедневная награда уже была получена.", 2)
            self.increase_step()
            return
        xpath = "//img[contains(@src, 'task_icon')]"
        success = self.brute_click(xpath, 10, "нажать вкладку 'Проверить вход'")
        self.increase_step()

        xpath = "//h4[contains(text(), 'Ежедневная награда')]"
        success = self.brute_click(xpath, 10, "нажать кнопку 'Ежедневная награда'")
        self.increase_step()

        xpath = "//div[contains(text(), 'Получить')]"
        success = self.brute_click(xpath, 10, "получить 'Ежедневную награду'")
        self.increase_step()

        xpath = "//div[contains(text(), 'Приходите завтра')]"
        success = self.move_and_click(xpath, 10, False, "проверить наличие 'Приходите завтра'", self.step, "visible")
        self.increase_step()

        if not success:
            self.output(f"Шаг {self.step}: Похоже, последовательность получения ежедневной награды не удалась.", 2)
            return

        self.output(f"СТАТУС: Ежедневная награда успешно получена.", 2)

        self.quit_driver()
        self.launch_iframe()

    def check_initial_screens(self):
        # Первая кнопка 'Следующий шаг'
        xpath = "//div[normalize-space(text())='Go']"
        self.move_and_click(xpath, 10, True, "нажать кнопку 'Go'", self.step, "clickable")
        self.output(f"Шаг {self.step} - Вы уже прошли начальные экраны.", 2)
        self.increase_step()
        
    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3
    
        priority = max(self.settings['verboseLevel'], default_priority)
    
        balance_text = f'{prefix} БАЛАНС:' if claimed else f'{prefix} БАЛАНС:'
        # Обновленный xpath: выбрать <div>, следующий за <img> с 'coin_icon' в src.
        balance_xpath = "//img[contains(@src, 'coin_icon')]/following-sibling::div"
    
        try:
            element = self.monitor_element(balance_xpath, 15, "получить баланс")
            if element:
                balance_part = element.strip()
                multiplier = 1  # Стандартный множитель
    
                # Проверить наличие 'K' или 'M' и скорректировать множитель
                if balance_part.endswith('K'):
                    multiplier = 1_000
                    balance_part = balance_part[:-1]  # Удалить 'K'
                elif balance_part.endswith('M'):
                    multiplier = 1_000_000
                    balance_part = balance_part[:-1]  # Удалить 'M'
    
                try:
                    balance_value = float(balance_part) * multiplier
                    self.output(f"Шаг {self.step} - {balance_text} {balance_value}", priority)
                    return balance_value
                except ValueError:
                    self.output(f"Шаг {self.step} - Не удалось преобразовать баланс '{balance_part}' в число.", priority)
                    return None
    
        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)
    
        self.increase_step()

    def get_wait_time(self, step_number="108", beforeAfter="pre-claim", max_attempts=1):
        return 180

    def get_profit_hour(self, claimed=False):
        """
        Получает прибыль в час в виде числа с плавающей точкой, извлекая значение из элемента прибыли.
        """
        import re
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3
        priority = max(self.settings['verboseLevel'], default_priority)
    
        # Обновленный XPath: найти span с ведущим '+' после метки Mining Rate.
        profit_xpath = "//label[normalize-space(text())='Mining Rate']/following-sibling::div//span[starts-with(normalize-space(text()), '+')]"
        try:
            profit_text = self.monitor_element(profit_xpath, 15, "прибыль в час")
            if profit_text:
                # Удалить все нечисловые символы (например, знак '+')
                profit_clean = re.sub(r"[^\d.]", "", profit_text)
                profit_value = float(profit_clean)
                self.output(f"Шаг {self.step} - {prefix} ПРИБЫЛЬ/ЧАС: {profit_value}", priority)
                return profit_value
        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Прибыль/Час:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)
        
        self.increase_step()
        return None

    def attempt_upgrade(self, balance):
        pass

def main():
    claimer = TabizooClaimer()
    claimer.run()

if __name__ == "__main__":
    main()