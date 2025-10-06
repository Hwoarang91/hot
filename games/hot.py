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

from claimer import Claimer

class HotClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/hot.py"
        self.prefix = "HOT:"
        self.url = "https://web.telegram.org/k/#@herewalletbot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.step = "01"
        self.imported_seedphrase = None
        self.start_app_xpath = "//a[@href='https://t.me/herewalletbot/app'] | //button[.//span[contains(@class,'reply-markup-button-text') and contains(normalize-space(),'Create HOT Wallet')]]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='HOT Wallet']]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()
        self.random_offset = random.randint(self.settings['lowestClaimOffset'], self.settings['highestClaimOffset'])
        super().__init__()
        
    def add_widget_and_open_storage(self):
        try:
            # Проверка наличия/прокручиваемости "Добавить виджет" без принудительного клика
            probe_xpath = "//p[normalize-space()='Add widget']"
            present = self.move_and_click(
                probe_xpath, 20, False,
                "проверка наличия 'Добавить виджет' (может отсутствовать)",
                self.step, "clickable"
            )
            self.increase_step()

            if not present:
                self.output(f"Шаг {self.step} - 'Добавить виджет' отсутствует/не виден. Пропускаем.", 3)
                return False

            # Один проход грубого клика по Добавить виджет
            self.brute_click(probe_xpath, timeout=15, action_description="клик по иконке 'Добавить виджет'")
            self.increase_step()

            # Один проход грубого клика по Хранилищу
            storage_xpath = "(//h4[contains(normalize-space(.), 'Storage')])[last()]"
            self.brute_click(storage_xpath, timeout=15, action_description="клик по ссылке 'Хранилище' (один проход)")
            self.increase_step()

            self.set_cookies()


        except Exception as e:
            self.output(f"Шаг {self.step} - Ошибка в последовательности Добавить виджет + Хранилище: {e}", 1)
            return False

    def next_steps(self):
        try:
            self.launch_iframe()
            self.increase_step()

            xpath = "//button[.//p[normalize-space()='Import account']]"
            self.move_and_click(xpath, 30, True, "найти кнопку входа HereWallet", "08", "clickable")
            self.increase_step()

            xpath = "//p[normalize-space(text())='Seed phrase or private key']"
            self.move_and_click(xpath, 30, True, "найти элемент с seed фразой или приватным ключом", "08", "clickable")
            self.increase_step()

            xpath = "//p[contains(text(), 'Seed or private key')]/ancestor-or-self::*/textarea"
            input_field = self.move_and_click(xpath, 30, True, "найти текстовое поле seed фразы", self.step, "clickable")
            if not self.imported_seedphrase:
                self.imported_seedphrase = self.validate_seed_phrase()
            input_field.send_keys(self.imported_seedphrase) 
            self.output(f"Шаг {self.step} - Успешно введена seed фраза...", 3)
            self.increase_step()

            xpath = "//button[contains(text(), 'Continue')]"
            self.move_and_click(xpath, 30, True, "нажать продолжить после ввода seed фразы", self.step, "clickable")
            self.increase_step()

            xpath = "//button[contains(text(), 'Continue')]"
            self.move_and_click(xpath, 180, True, "нажать продолжить на экране выбора аккаунта", self.step, "clickable")
            self.increase_step()

            self.add_widget_and_open_storage()
            self.increase_step()
            
            self.set_cookies()

        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение времени ожидания.", 1)

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 1)

    def full_claim(self):
        self.step = "100"
        low_near = True
        
        self.launch_iframe()

        xpath = "(//p[normalize-space(.)='NEAR']/parent::div/following-sibling::div//p[last()])[1]"
        self.move_and_click(xpath, 30, False, "перейти к балансу 'Near'.", self.step, "visible")
        near = self.monitor_element(xpath, 20, "получить ваш баланс 'Near'")
        if near:
            try:
                last_value_float = float(near)
                if last_value_float > 0.2:
                    low_near = False
                    self.output(f"Шаг {self.step} - Снят флаг низкого баланса 'Near', текущий баланс: {last_value_float}", 3)
                else:
                    self.output(f"Шаг {self.step} - Флаг низкого баланса 'Near' остается, текущий баланс: {last_value_float}", 3)
                
            except ValueError:
                self.output(f"Шаг {self.step} - Не удалось преобразовать баланс Near в число с плавающей точкой.", 3)
        else:
            self.output(f"Шаг {self.step} - Не удалось получить ваш баланс Near.", 3)
        self.increase_step()

        self.add_widget_and_open_storage()
        self.increase_step()

        xpath = "//h4[normalize-space(.)='Storage']"
        self.move_and_click(xpath, 30, True, "клик по ссылке 'хранилище'", self.step, "clickable")
        self.increase_step()

        self.get_balance(False)
        self.get_profit_hour(True)

        wait_time_text = self.get_wait_time(self.step, "pre-claim") 

        try:
            if wait_time_text != "Заполнено":
                matches = re.findall(r'(\d+)([hm])', wait_time_text)
                remaining_wait_time = (sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches))
                # Определение динамического порога
                if self.settings['lowestClaimOffset'] < 0:
                    threshold = abs(self.settings['lowestClaimOffset'])
                else:
                    threshold = 5  # Значение по умолчанию
                if remaining_wait_time < threshold or self.settings["forceClaim"]:
                    self.settings['forceClaim'] = True
                    self.output(f"Шаг {self.step} - оставшееся время до запроса меньше минимального смещения, устанавливаем: settings['forceClaim'] = True", 3)
                else:
                    remaining_time = self.apply_random_offset(remaining_wait_time)
                    self.output(f"СТАТУС: Исходное время ожидания {wait_time_text} - {remaining_wait_time} минут, спим {remaining_time} минут с учетом случайного смещения.", 1)
                    return remaining_time
        except Exception as e:
            self.output(f"Обнаружена ошибка: {str(e)}", 2)
            return 120

        if not wait_time_text:
            return 60

        try:
            self.output(f"Шаг {self.step} - Время ожидания перед запросом: {wait_time_text} и случайное смещение {self.random_offset} минут.", 1)
            self.increase_step()

            if wait_time_text == "Заполнено" or self.settings['forceClaim']:
                try:
                    original_window = self.driver.current_window_handle
                    xpath = "//button[contains(text(), 'Check NEWS')]"
                    self.move_and_click(xpath, 20, True, "проверка НОВОСТЕЙ.", self.step, "clickable")
                    self.driver.switch_to.window(original_window)
                except TimeoutException:
                    if self.settings['debugIsOn']:
                        self.output(f"Шаг {self.step} - Нет новостей для проверки или кнопка не найдена.", 3)
                self.increase_step()

                try:
                    self.select_iframe(self.step)
                    self.increase_step()
                    
                    xpath = "//button[contains(text(), 'Claim HOT')]"
                    self.move_and_click(xpath, 20, True, "нажать кнопку запроса (первая кнопка)", self.step, "clickable")
                    self.increase_step()

                    self.output(f"Шаг {self.step} - Ждем, пока индикатор ожидания запроса перестанет крутиться...", 2)
                    time.sleep(5)
                    wait = WebDriverWait(self.driver, 240)
                    spinner_xpath = "//*[contains(@class, 'spinner')]" 
                    try:
                        wait.until(EC.invisibility_of_element_located((By.XPATH, spinner_xpath)))
                        self.output(f"Шаг {self.step} - Индикатор ожидания запроса остановился.\n", 3)
                    except TimeoutException:
                        self.output(f"Шаг {self.step} - Похоже, сайт завис - индикатор не исчез вовремя.\n", 2)
                    self.increase_step()
                    wait_time_text = self.get_wait_time(self.step, "post-claim") 
                    matches = re.findall(r'(\d+)([hm])', wait_time_text)
                    total_wait_time = self.apply_random_offset(sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches))
                    self.increase_step()

                    self.get_balance(True)

                    if wait_time_text == "Заполнено":
                        if low_near:
                            self.output(f"СТАТУС: Таймер ожидания все еще показывает: Заполнено.", 1)
                            self.output(f"СТАТУС: Мы не смогли подтвердить, что у вас >0.2 Near, что могло привести к ошибке запроса.", 1)
                            self.output(f"СТАТУС: Пожалуйста, проверьте в интерфейсе, можете ли вы запросить вручную, и рассмотрите возможность пополнения баланса NEAR.", 1)
                            self.output(f"Шаг {self.step} - Проверим снова через 1 час, если запрос не прошел, попробуем снова.", 2)
                        else:
                            self.output(f"СТАТУС: Таймер ожидания все еще показывает: Заполнено - запрос не удался.", 1)
                            self.output(f"Шаг {self.step} - Это значит, что либо запрос не удался, либо в игре задержка более 4 минут.", 1)
                            self.output(f"Шаг {self.step} - Проверим снова через 1 час, если запрос не прошел, попробуем снова.", 2)
                    else:
                        self.output(f"СТАТУС: Успешный запрос: Следующий запрос через {wait_time_text} / {total_wait_time} минут.", 1)

                    return max(60, total_wait_time)

                except TimeoutException:
                    self.output(f"СТАТУС: Процесс запроса превысил время ожидания: Возможно, сайт завис? Повторим через час.", 1)
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
                    self.output(f"Шаг {self.step} - Еще не время запрашивать этот кошелек. Ждем {total_time} минут, пока хранилище не заполнится.", 2)
                    return total_time
                else:
                    self.output(f"Шаг {self.step} - Данные о времени ожидания не найдены? Проверим снова через час.", 2)
                    return 60
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла непредвиденная ошибка: {e}", 1)
            return 60

    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)
        balance_text = f'{prefix} БАЛАНС:' if claimed else f'{prefix} БАЛАНС:'
        balance_xpath = f"//p[contains(text(), 'HOT')]/following-sibling::img/following-sibling::p"

        try:
            element = self.monitor_element(balance_xpath, 20, "получить баланс")
            if element:
                balance_part = element # .text.strip()
                self.output(f"Шаг {self.step} - {balance_text} {balance_part}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)

        self.increase_step()

    def get_profit_hour(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        # Формируем XPath для прибыли
        profit_text = f'{prefix} ПРИБЫЛЬ/ЧАС:'
        profit_xpath = "//div[div[p[text()='Storage']]]//p[last()]"

        try:
            element = self.strip_non_numeric(self.monitor_element(profit_xpath, 20, "получить прибыль в час"))

            # Проверяем, что элемент не None и выводим прибыль
            if element:
                self.output(f"Шаг {self.step} - {profit_text} {element}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с '{prefix} Прибыль/Час:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Вывод ошибки в виде строки для логирования
        
        self.increase_step()

    def get_wait_time(self, step_number="108", beforeAfter="pre-claim"):
        try:
            xpath = f"//div[contains(., 'Storage')]//p[contains(., '{self.pot_full}') or contains(., '{self.pot_filling}')]"
            wait_time_element = self.monitor_element(xpath, 20, "получить время ожидания")
            if wait_time_element is not None:
                return wait_time_element
            else:
                self.output(f"Шаг {self.step}: Элемент времени ожидания не найден. Кликаем по ссылке 'Хранилище' и пробуем снова...", 3)
                storage_xpath = "//h4[text()='Storage']"
                self.move_and_click(storage_xpath, 30, True, "клик по ссылке 'хранилище'", f"{self.step} повторная проверка", "clickable")
                wait_time_element = self.monitor_element(xpath, 20, "получить время ожидания после повторной попытки")
                if wait_time_element is not None:
                    return wait_time_element
                else:
                    self.output(f"Шаг {self.step}: Элемент времени ожидания все еще не найден после повторной попытки.", 3)
                
        except TimeoutException:
            self.output(f"Шаг {self.step}: Превышено время ожидания при попытке получить время ожидания.", 3)

        except Exception as e:
            self.output(f"Шаг {self.step}: Произошла ошибка: {e}", 3)

        return False

def main():
    claimer = HotClaimer()
    claimer.run()

if __name__ == "__main__":
    main()