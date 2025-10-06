import os
import shutil
import sys
import time
import re
import json
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
import requests

from claimer import Claimer

class VertusClaimer(Claimer):
    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/vertus.py"
        self.prefix = "Vertus:"
        self.url = "https://web.telegram.org/k/#@vertus_app_bot"
        self.pot_full = "Filled"
        self.pot_filling = "to fill"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.step = "01"
        self.imported_seedphrase = None
        self.start_app_xpath = "//div[@class='reply-markup-row']//span[contains(text(),'Open app') or contains(text(), 'Play')]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='Vertus']]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()
        self.random_offset = random.randint(self.settings['lowestClaimOffset'], self.settings['highestClaimOffset'])
        self.driver = None  # Инициализируем драйвер как None
        super().__init__()

    def cipher_daily(self):
        return
        cipher_xpath = "//div[contains(@class, 'btnLeft')]"
        self.move_and_click(cipher_xpath, 10, True, "перейти по ссылке на остров Cipher", self.step, "clickable")
        self.increase_step()
        
        xpaths = {
            '1': "//img[contains(@class, '_img_131qd_41') and @src='/icons/islands/farmIsland.png']",
            '2': "//img[contains(@class, '_img_131qd_41') and @src='/icons/islands/mineIsland.png']",
            '3': "//img[contains(@class, '_img_131qd_41') and @src='/icons/islands/buildIsland.png']",
            '4': "//img[contains(@class, '_img_131qd_41') and @src='/icons/islands/forestIsland.png']"
        }
        
        empty_slots_xpaths = "(//img[contains(@class, 'itemEmpty')])"
        
        if not self.move_and_click(empty_slots_xpaths, 10, False, "поиск первого пустого слота", self.step, "visible"):
            self.output(f"Шаг {self.step} - Ежедневная головоломка уже решена.", 2)
            return
        else:
            self.output(f"Шаг {self.step} - Попытка решить ежедневную головоломку.", 2)
            self.increase_step()
            
            try:
                response = requests.get('https://raw.githubusercontent.com/thebrumby/HotWalletClaimer/main/extras/vertuscipher')
                response.raise_for_status()
                sequence = response.text.strip()
            except requests.exceptions.RequestException as e:
                self.output(f"Ошибка при получении последовательности: {e}", 2)
                return

            for i, digit in enumerate(sequence):
                n = i + 1
                xpath = xpaths.get(digit)
                check_xpath = f"{empty_slots_xpaths}[{n}]"

                if xpath:
                    # Переместиться и кликнуть по элементу
                    self.move_and_click(xpath, 10, False, f"поставить цифру {digit} в слот {n}", self.step, "visible")
                    
                    # Найти элемент и кликнуть по нему через JS
                    element = self.driver.find_element(By.XPATH, xpath)
                    self.driver.execute_script("arguments[0].click();", element)
                else:
                    self.output(f"Шаг {self.step} - XPath для цифры {digit} не найден", 2)

                # Увеличить счетчик шага
                self.increase_step()

        if not self.move_and_click(empty_slots_xpaths, 10, False, "повторная проверка завершения головоломки", self.step, "visible"):
            self.output(f"Шаг {self.step} - Ежедневная головоломка решена.", 2)
        else:
            self.output(f"Шаг {self.step} - Ежедневная головоломка не решена, возможно, ждем новое решение.", 2)
            self.increase_step()

    def is_slot_filled(self, check_xpath):
        time.sleep(2)
        try:
            # Проверяем, что элемент по check_xpath больше не пустой
            filled_element = self.driver.find_element(By.XPATH, check_xpath)
            if filled_element.is_displayed():
                self.output(f"Шаг {self.step} - Слот заполнен как ожидалось для XPath: {check_xpath}", 3)
                return True
        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Слот не заполнен или элемент не найден: {check_xpath}", 3)
            return False

        return False


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

    def check_daily_reward(self):
        action = ActionChains(self.driver)
        mission_xpath = "//p[contains(text(), 'Missions')]"
        self.move_and_click(mission_xpath, 10, False, "перейти по ссылке миссий", self.step, "visible")
        success = self.click_element(mission_xpath)
        if success:
            self.output(f"Шаг {self.step} - Успешно кликнули по ссылке 'Миссии'.", 3)
        else:
            self.output(f"Шаг {self.step} - Не удалось кликнуть по ссылке 'Миссии'.", 3)
        self.increase_step()
        

        daily_xpath = "//p[contains(text(), 'Daily')]"
        self.move_and_click(daily_xpath, 10, False, "перейти по ссылке ежедневных миссий", self.step, "visible")
        success = self.click_element(daily_xpath)
        if success:
            self.output(f"Шаг {self.step} - Успешно кликнули по ссылке 'Ежедневные миссии'.", 3)
        else:
            self.output(f"Шаг {self.step} - Не удалось кликнуть по ссылке 'Ежедневные миссии'.", 2)
        self.increase_step()

        claim_xpath = "//p[contains(text(), 'Claim')]"
        button = self.move_and_click(claim_xpath, 10, False, "перейти по ссылке получения ежедневной награды", self.step, "visible")
        if button:
            self.driver.execute_script("arguments[0].click();", button)
        success = self.click_element(claim_xpath)
        if success:
            self.increase_step()
            self.output(f"Шаг {self.step} - Успешно кликнули по ссылке 'Получить ежедневное'.", 3)
            return "Ежедневный бонус получен."

        come_back_tomorrow_xpath = "//p[contains(text(), 'Come back tomorrow')]"
        come_back_tomorrow_msg = self.move_and_click(come_back_tomorrow_xpath, 10, False, "проверка, что бонус будет доступен завтра", self.step, "visible")
        if come_back_tomorrow_msg:
            self.increase_step()
            return "Ежедневный бонус будет доступен завтра."

        self.increase_step()
        return "Статус ежедневного бонуса неизвестен."

    def full_claim(self):
        self.step = "100"
        self.launch_iframe()

        xpath = "//p[text()='Collect']"
        island_text = ""
        button = self.move_and_click(xpath, 10, False, "собрать бонус острова (может отсутствовать)", self.step, "visible")
        if button:
            self.driver.execute_script("arguments[0].click();", button)
            island_text = "Бонус острова получен."
        self.increase_step()    

        xpath = "//p[text()='Mining']"
        button = self.move_and_click(xpath, 10, False, "собрать ссылку на хранилище", self.step, "visible")
        if button:
            self.driver.execute_script("arguments[0].click();", button)
        self.increase_step()

        balance_before_claim = self.get_balance(claimed=False)

        self.get_profit_hour(False)

        wait_time_text = self.get_wait_time(self.step, "pre-claim")
        self.output(f"Шаг {self.step} - Исходный текст времени ожидания перед получением: {wait_time_text}", 3)

        if wait_time_text != "Ready to collect":
            matches = re.findall(r'(\d+)([hm])', wait_time_text)
            if matches:
                remaining_wait_time = (sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches)) + self.random_offset
                if remaining_wait_time < 5:
                    self.settings['forceClaim'] = True
                    self.output(f"Шаг {self.step} - оставшееся время до получения меньше случайного смещения, применяем: settings['forceClaim'] = True", 3)
                if not self.settings["forceClaim"]:
                    remaining_wait_time = min(180, remaining_wait_time)
                    self.output(f"СТАТУС: {island_text} Мы снова ляжем спать на {remaining_wait_time} минут.", 1)
                    return remaining_wait_time
            else:
                self.output("В wait_time_text не найдено совпадений, назначаем время ожидания по умолчанию.", 2)
                return 60  # Значение по умолчанию, если совпадений нет
                
        if not wait_time_text:
            return 60

        try:
            self.output(f"Шаг {self.step} - Время ожидания перед получением: {wait_time_text} и случайное смещение {self.random_offset} минут.", 1)
            self.increase_step()

            if wait_time_text == "Ready to collect" or self.settings['forceClaim']:
                try:
                    xpath = "//div[p[text()='Collect']]"
                    self.move_and_click(xpath, 10, True, "собрать основной приз", self.step, "clickable")
                    self.increase_step()

                    xpath = "//div[div/p[text()='Claim']]/div/p"
                    self.move_and_click(xpath, 10, True, "получить без подключения кошелька (может отсутствовать)", self.step, "clickable")
                    self.increase_step()

                    # xpath = "//p[contains(@class, '_text_16x1w_17') and text()='Claim']"
                    # success = self.click_element(xpath)
                    # self.move_and_click(xpath, 10, True, "собрать награду 'splash'", self.step, "clickable")
                    # self.increase_step()

                    wait_time_text = self.get_wait_time(self.step, "post-claim")
                    self.output(f"Шаг {self.step} - Исходный текст времени ожидания после получения: {wait_time_text}", 3)
                    matches = re.findall(r'(\d+)([hm])', wait_time_text)
                    total_wait_time = self.apply_random_offset(sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches))
                    self.increase_step()

                    balance_after_claim = self.get_balance(claimed=True)

                    self.cipher_daily() 

                    daily_reward_text = self.check_daily_reward()
                    self.increase_step()

                    if wait_time_text == "Ready to collect":
                        self.output(f"СТАТУС: Таймер ожидания все еще показывает: Filled.", 1)
                        self.output(f"Шаг {self.step} - Это значит, что либо получение не удалось, либо в игре задержка >4 минут.", 1)
                        self.output(f"Шаг {self.step} - Проверим снова через 1 час, если получение не прошло, попробуем снова.", 2)
                    else:
                        self.output(f"СТАТУС: {island_text}. Успешное получение & {daily_reward_text}", 1)
                    return min(180, total_wait_time)

                except TimeoutException:
                    self.output(f"СТАТУС: Время ожидания получения истекло: Возможно, сайт завис? Попробуем снова через час.", 1)
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
                    self.output(f"Шаг {self.step} - Еще не время получать для этого кошелька. Ждем {total_time} минут, пока хранилище не заполнится.", 2)
                    return total_time
                else:
                    self.output(f"Шаг {self.step} - Нет данных о времени ожидания? Проверим снова через час.", 2)
                    return 60
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла непредвиденная ошибка: {e}", 1)
            return 60

    def get_profit_hour(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        # Формируем XPath для прибыли
        profit_text = f'{prefix} ПРИБЫЛЬ/ЧАС:'
        profit_xpath = "(//p[@class='_descInfo_19xzr_38'])[last()]"

        try:
            element = self.strip_non_numeric(self.monitor_element(profit_xpath, 15, "прибыль в час"))
            # Проверяем, что элемент не None и выводим прибыль
            if element:
                self.output(f"Шаг {self.step} - {profit_text} {element}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Прибыль/Час:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Ошибка в виде строки для логирования
        
        self.increase_step()

    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        # Динамически регулируем приоритет лога
        priority = max(self.settings['verboseLevel'], default_priority)

        balance_text = f'{prefix} БАЛАНС:'
        balance_xpath = "//div[p[contains(text(), 'Vert balance')]]/div/p"

        try:
            balance_part = self.monitor_element(balance_xpath, 15, "баланс")

            if balance_part:
                self.output(f"Шаг {self.step} - {balance_text} {balance_part}", priority)
                return balance_part

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)

        self.increase_step()

    def get_wait_time(self, step_number="108", beforeAfter="pre-claim", max_attempts=2):
        for attempt in range(1, max_attempts + 1):
            try:
                xpath = "//p[contains(@class, 'descInfo') and contains(text(), 'to')]"
                self.move_and_click(xpath, 10, False, f"получить таймер ожидания {beforeAfter}", self.step, "visible")
                wait_time_element = self.monitor_element(xpath, 10, "таймер получения")
                
                if wait_time_element is not None:
                    return wait_time_element
                else:
                    self.output(f"Шаг {step_number} - Попытка {attempt}: Элемент времени ожидания не найден. Кликаем по ссылке 'Хранилище' и повторяем попытку...", 3)
                    storage_xpath = "//h4[text()='Storage']"
                    self.move_and_click(storage_xpath, 30, True, "клик по ссылке 'хранилище'", f"{step_number} повторная проверка", "clickable")
                    self.output(f"Шаг {step_number} - Попытка повторного выбора хранилища...", 3)

            except TimeoutException:
                if attempt < max_attempts:
                    self.output(f"Шаг {step_number} - Попытка {attempt}: Элемент времени ожидания не найден. Кликаем по ссылке 'Хранилище' и повторяем попытку...", 3)
                    storage_xpath = "//h4[text()='Storage']"
                    self.move_and_click(storage_xpath, 30, True, "клик по ссылке 'хранилище'", f"{step_number} повторная проверка", "clickable")
                else:
                    self.output(f"Шаг {step_number} - Попытка {attempt}: Элемент времени ожидания не найден.", 3)

            except Exception as e:
                self.output(f"Шаг {step_number} - Произошла ошибка при попытке {attempt}: {e}", 3)

        return False

def main():
    claimer = VertusClaimer()
    claimer.run()

if __name__ == "__main__":
    main()