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

class PocketFiClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/pocketfi.py"
        self.prefix = "Pocketfi:"
        self.url = "https://web.telegram.org/k/#@pocketfi_bot"
        self.pot_full = "Filled"
        self.pot_filling = "to fill"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.start_app_xpath = "//div[contains(@class, 'reply-markup-row')]//span[contains(., 'Mining') or contains(., 'PocketFi')]"
        self.balance_xpath = f"//p[contains(., 'Total $SWITCH mined')]/following-sibling::div[1][.//img[contains(@src, '/switch.svg')]]/span"
        self.time_remaining_xpath = "//p[contains(text(), 'burn in')]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()
        self.random_offset = -60
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

        button_texts = [
            "Какие простые действия?",
            "Что еще здесь?",
            "Начать майнинг"
        ]
        
        for text in button_texts:
            xpath = f"//button[normalize-space(.)='{text}']"
            button = self.move_and_click(xpath, 15, True, f"нажать кнопку '{text}'", self.step, "clickable")
            if button:
                self.increase_step()
            else:
                self.output(f"Шаг {self.step} - Кнопка с текстом '{text}' не найдена. Попробуем выполнить запрос.", 3)
                break


        xpath = f"//button[descendant::*[local-name()='svg' и @width='14' и @height='14']]"
        self.move_and_click(xpath, 15, True, f"закрыть всплывающее окно (может отсутствовать)", self.step, "clickable")
        self.increase_step()

        self.get_balance(self.balance_xpath, False)
        self.increase_step()

        wait_time_text_pre = self.get_wait_time(self.time_remaining_xpath, "108", "предварительный запрос")
        if wait_time_text_pre is False:
            self.output("СТАТУС: Не удалось получить время ожидания перед запросом. Попробуем снова через 1 час.", 1)
            return 60
        
        if wait_time_text_pre > 330:
            actual_wait_time = wait_time_text_pre - 30 
            self.output(f"СТАТУС: Похоже, что горшок не готов к запросу в течение {wait_time_text_pre} минут. Вернемся через {actual_wait_time} минут.", 1)
            return actual_wait_time
        
        self.output(f"Шаг {self.step} - таймер перед запросом показывает {wait_time_text_pre} минут до сгорания.", 2)
        
        xpath = "//div[@class='absolute flex items-center justify-center flex-col text-white']/span[contains(text(), 'запрос')]"
        clicked_it = False
        button = self.move_and_click(xpath, 15, True, "нажать запрос", self.step, "clickable")
        possible_click = False

        xpath = f"//button[descendant::*[local-name()='svg' и @width='14' и @height='14']]"
        self.move_and_click(xpath, 15, True, f"закрыть всплывающее окно (может отсутствовать)", self.step, "clickable")
        self.increase_step()
        
        # Запасной метод, если move_and_click не вернул кнопку
        if not button:
            self.output(f"Шаг {self.step} - Кнопка для нажатия не найдена. Пытаемся запасной метод для кнопки запроса...", 3)
            try:
                elements = self.driver.find_elements(By.XPATH, xpath)
                if elements:
                    for el in elements:
                        try:
                            self.driver.execute_script("arguments[0].click();", el)
                            button = el  # Используем этот элемент как успешно нажатый
                            break
                        except Exception as e:
                            self.output(f"Шаг {self.step} - Запасной клик не удался: {e}", 3)
            except Exception as fallback_e:
                self.output(f"Шаг {self.step} - Запасной метод вызвал ошибку: {fallback_e}", 3)
        
        if button:
            self.output(f"Шаг {self.step} - Возможно, мы нажали, проверим таймер.", 3)
            possible_click = True
        else:
            self.output(f"Шаг {self.step} - Кнопка не найдена даже после запасного метода.", 3)
        
        time.sleep(5)
        wait_time_text_mid = self.get_wait_time(self.time_remaining_xpath, "108", "после запроса")
        if wait_time_text_mid is False:
            self.output("СТАТУС: Не удалось получить время ожидания после запроса. Попробуем снова через 1 час.", 1)
            return 60
        if possible_click and wait_time_text_mid > 330:
            self.output(f"Шаг {self.step} - Похоже, запрос выполнен успешно.", 3)
            clicked_it = True
        else:
            self.output(f"Шаг {self.step} - Похоже, запрос не удался.", 3)

        self.increase_step()
        
        self.get_balance(self.balance_xpath, True)
        self.increase_step()

        self.get_profit_hour(True)
        
        if wait_time_text_mid:
            next_claim = max(5, wait_time_text_mid-30) 

        if clicked_it and next_claim:
            self.output(f"СТАТУС: Запрос выполнен успешно. Майним снова через {next_claim} минут.", 1)
            return next_claim

        if next_claim:
            self.output(f"СТАТУС: Запрос не выполнен в этот раз. Попробуем майнить снова через {next_claim} минут.", 1)
            return next_claim
        
        self.output(f"СТАТУС: Проблемы с выполнением запроса, вернемся через час.", 1)
        return 60

    def get_profit_hour(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        # Формируем конкретный XPath для прибыли
        profit_text = f'{prefix} ПРИБЫЛЬ/ЧАС:'
        profit_xpath = "//p[contains(., '$SWITCH')]//span[last()]"

        try:
            element = self.strip_non_numeric(self.monitor_element(profit_xpath, 15, "прибыль в час"))

            # Проверяем, что элемент не None и выводим прибыль
            if element:
                self.output(f"Шаг {self.step} - {profit_text} {element}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Прибыль/Час:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Ошибка как строка для логирования
        
        self.increase_step()

def main():
    claimer = PocketFiClaimer()
    claimer.run()

if __name__ == "__main__":
    main()