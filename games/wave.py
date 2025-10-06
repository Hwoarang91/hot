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

class WaveClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/wave.py"
        self.prefix = "Wave:"
        self.url = "https://web.telegram.org/k/#@waveonsuibot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.start_app_xpath = "//span[contains(text(), 'Войти в Wave') or contains(text(), 'Открыть приложение Wave')]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()
        self.random_offset = random.randint(self.settings['lowestClaimOffset'], self.settings['highestClaimOffset']) + 1
        super().__init__()
        
    def switch_tab(self):
        """ Перечислить все открытые вкладки, вывести их в лог и переключиться на самую новую. """
        tabs = self.driver.window_handles
        self.output(f"Шаг {self.step} - Найдено {len(tabs)} открытых вкладок:", 3)
        
        # Вывести URL каждой вкладки
        for index, tab in enumerate(tabs):
            self.driver.switch_to.window(tab)
            self.output(f"→ Вкладка {index + 1}: {self.driver.current_url}", 3)
        
        # ✅ Переключиться на самую новую вкладку
        if len(tabs) > 1:
            self.driver.switch_to.window(tabs[-1])
            self.output(f"Шаг {self.step} - Переключено на новую вкладку: {self.driver.current_url}", 3)
        else:
            self.output(f"Шаг {self.step} - Новых вкладок не обнаружено, остаёмся на текущей странице.", 3)

    def next_steps(self):
        if not self.step:
            self.step = "01"
    
        def switch_tab():
            """ Перечислить все открытые вкладки, вывести их в лог и переключиться на самую новую. """
            tabs = self.driver.window_handles
            self.output(f"Шаг {self.step} - Найдено {len(tabs)} открытых вкладок:", 3)
        
            # Вывести URL каждой вкладки
            for index, tab in enumerate(tabs):
                self.driver.switch_to.window(tab)
                self.output(f"→ Вкладка {index + 1}: {self.driver.current_url}", 3)
        
            # ✅ Переключиться на самую новую вкладку
            if len(tabs) > 1:
                self.driver.switch_to.window(tabs[-1])
                self.output(f"Шаг {self.step} - Переключено на новую вкладку: {self.driver.current_url}", 3)
            else:
                self.output(f"Шаг {self.step} - Новых вкладок не обнаружено, остаёмся на текущей странице.", 3)

        def validate_telegram():
            """ Проверка последовательности входа в Telegram. """
            self.switch_tab()
    
            xpath = "//span[contains(text(), 'Открыть в веб')]"
            self.move_and_click(xpath, 30, True, "проверка всплывающего окна 'Открыть'", self.step, "кликабельно")
            self.increase_step() 
    
            xpath = "(//span[contains(text(), 'Войти в Wave')])[last()]"
            self.move_and_click(xpath, 10, True, "найти последнюю ссылку игры для токена доступа", self.step, "кликабельно")
            self.increase_step()
            
            xpath = "//button[contains(@class, 'popup-button') and contains(., 'Открыть')]"
            self.move_and_click(xpath, 10, True, "проверка всплывающего окна 'Открыть' (может отсутствовать)", self.step, "кликабельно")
            self.increase_step()
    
            self.switch_tab()
            
            # Шаг 3: Импорт кошелька (только если нужно)
            xpath = "//button[normalize-space(text())='Импортировать кошелек']"
            if self.move_and_click(xpath, 10, True, "импорт сид-фразы (может отсутствовать)", self.step, "кликабельно"):
                populate_seedphrase()
            self.increase_step()
    
        def populate_seedphrase():
            """ Заполнить сид-фразу, если требуется. """
            try:
                # Шаг 1: Ввести сид-фразу
                xpath = "//p[contains(text(), 'Сид-фраза или приватный ключ')]/following-sibling::textarea[1]"
                input_field = WebDriverWait(self.driver, 30).until(
                    EC.visibility_of_element_located((By.XPATH, xpath))
                )
    
                self.driver.execute_script("arguments[0].click();", input_field)
                input_field.send_keys(self.validate_seed_phrase())
                self.output(f"Шаг {self.step} - Сид-фраза успешно введена...", 3)
    
            except Exception as e:
                self.output(f"Шаг {self.step} - Не удалось ввести сид-фразу: {str(e)}", 2)
    
            self.increase_step()  # Всегда увеличиваем шаг, даже если ввод не удался
    
            # Шаг 2: Нажать 'Продолжить' после ввода сид-фразы
            xpath = "//button[normalize-space(text())='Продолжить']"
            self.move_and_click(xpath, 10, True, "нажать продолжить после ввода сид-фразы", self.step, "кликабельно")
            self.increase_step()
    
        try:
            # Шаг 1: Войти в Wave
            xpath = "//span[contains(text(), 'Войти в Wave') или contains(text(), 'Открыть приложение Wave')]"
            self.find_working_link(self.step, xpath)
            self.increase_step()
            
            xpath = "//button[contains(@class, 'popup-button') и содержит(., 'Открыть')]"
            self.move_and_click(xpath, 10, True, "проверка всплывающего окна 'Открыть' (может отсутствовать)", self.step, "кликабельно")
            self.increase_step()
            
            self.switch_tab()
    
            # Шаг 2: Проверить сессию Telegram, если это ещё не сделано
            xpath = "//span[normalize-space(text())='Вход в Telegram']"
            if self.move_and_click(xpath, 10, True, "инициировать ссылку 'Войти' (может отсутствовать)", self.step, "кликабельно"):
                validate_telegram()
            self.increase_step()
    
            # Шаг 3: Проверить, что мы вошли в систему
            xpath = "//span[contains(text(), 'Ocean Game')]"
            if self.move_and_click(xpath, 10, True, "нажать ссылку 'Получить сейчас'", self.step, "видимо"):
                self.output(f"Шаг {self.step} - Похоже, мы успешно вошли в систему", 2)
                self.set_cookies()  # ✅ Устанавливать куки только если вход прошёл успешно
            else:
                self.output(f"СТАТУС Похоже, вход не удался!", 1)
            self.increase_step()
    
        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение времени ожидания.", 1)
    
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 1)
            
    def launch_iframe(self):
        self.driver = self.get_driver()
        # Установить размер окна для десктопного браузера, например 1920x1080 для полного HD
        self.driver.set_window_size(1920, 1080)

        # Начинаем с чистой папки для скриншотов
        if int(self.step) < 101:
            if os.path.exists(self.screenshots_path):
                shutil.rmtree(self.screenshots_path)
            os.makedirs(self.screenshots_path)

        try:
            self.driver.get(self.url)
            WebDriverWait(self.driver, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
            self.output(f"Шаг {self.step} - Пытаемся проверить, вошли ли мы в систему (надеюсь, QR-код отсутствует).", 2)
            xpath = "//canvas[@class='qr-canvas']"
            if self.settings['debugIsOn']:
                self.debug_information("Проверка QR-кода при запуске сессии","проверка")
            wait = WebDriverWait(self.driver, 10)
            wait.until(EC.visibility_of_element_located((By.XPATH, xpath)))
            self.output(f"Шаг {self.step} - Драйвер Chrome сообщает, что QR-код виден: Похоже, мы больше не вошли в систему.", 2)
            self.output(f"Шаг {self.step} - Скорее всего, вы получите предупреждение, что центральное поле ввода не найдено.", 2)
            self.output(f"Шаг {self.step} - Система попытается восстановить сессию или перезапустить скрипт из CLI для принудительного нового входа.\n", 2)

        except TimeoutException:
            self.output(f"Шаг {self.step} - Ничего для действия не найдено. Тест QR-кода пройден.\n", 3)
        self.increase_step()

        self.driver.get(self.url)
        WebDriverWait(self.driver, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        
        for _ in range(3):
            self.output(f"Шаг {self.step} - Загрузка: {str(self.url)}", 3)
            self.driver.get(self.url)
            WebDriverWait(self.driver, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
            title_xapth = "(//div[@class='user-title']//span[contains(@class, 'peer-title')])[1]"
            try:
                wait = WebDriverWait(self.driver, 30)
                wait.until(EC.visibility_of_element_located((By.XPATH, title_xapth)))
                title = self.monitor_element(title_xapth, 10, "Получить текущий заголовок страницы")
                self.output(f"Шаг {self.step} - Текущий заголовок страницы: {title}", 3)
                break
            except TimeoutException:
                self.output(f"Шаг {self.step} - Заголовок не найден.", 3)
                if self.settings['debugIsOn']:
                    self.debug_information("Проверка заголовка приложения при загрузке telegram", "проверка")
                time.sleep(5)

        # Есть крайне маловероятный сценарий, что чат мог быть очищен.
        # В этом случае нужно нажать кнопку "START", чтобы открыть окно чата!
        xpath = "//button[contains(., 'START')]"
        button = self.move_and_click(xpath, 8, True, "проверка кнопки запуска (не должна присутствовать)", self.step, "кликабельно")
        self.increase_step()

        # Обработка всплывающего окна HereWalletBot
        self.output(f"Шаг {self.step} - Подготовительные шаги завершены, передаём управление основной функции настройки/запроса...", 2)


    def full_claim(self):
        self.step = "100"

        def apply_random_offset(unmodifiedTimer):
            lowest_claim_offset = max(0, self.settings['lowestClaimOffset'])
            highest_claim_offset = max(0, self.settings['highestClaimOffset'])
            if self.settings['lowestClaimOffset'] <= self.settings['highestClaimOffset']:
                self.random_offset = random.randint(lowest_claim_offset, highest_claim_offset) + 1
                modifiedTimer = unmodifiedTimer + self.random_offset
                self.output(f"Шаг {self.step} - К таймеру ожидания добавлено случайное смещение: {self.random_offset} минут.", 2)
                return modifiedTimer

        self.launch_iframe()
        
        xpath = "(//span[contains(text(), 'Войти в Wave')])[last()]"
        self.move_and_click(xpath, 10, True, "найти последнюю ссылку игры для токена доступа", self.step, "кликабельно")
        self.increase_step()
            
        xpath = "//button[contains(@class, 'popup-button') and contains(., 'Открыть')]"
        self.move_and_click(xpath, 10, True, "проверка всплывающего окна 'Открыть' (может отсутствовать)", self.step, "кликабельно")
        self.increase_step()
        
        self.switch_tab()

        xpath = "//button//span[contains(text(), 'Получить сейчас')]"
        button = self.move_and_click(xpath, 10, False, "нажать ссылку 'Ocean Game'", self.step, "видимо")
        self.driver.execute_script("arguments[0].click();", button)
        self.increase_step()

        self.get_balance(False)
        self.get_profit_hour(False)

        wait_time_text = self.get_wait_time(self.step, "до запроса")

        if wait_time_text != self.pot_full:
            matches = re.findall(r'(\d+)([hm])', wait_time_text)
            remaining_wait_time = (sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches))
            if remaining_wait_time < 5 or self.settings["forceClaim"]:
                self.settings['forceClaim'] = True
                self.output(f"Шаг {self.step} - Оставшееся время до запроса короткое, поэтому запросим сейчас, установив: settings['forceClaim'] = True", 3)
            else:
                remaining_wait_time += self.random_offset
                self.output(f"СТАТУС: Учитывая {wait_time_text}, мы вернёмся к сну на {remaining_wait_time} минут.", 1)
                return remaining_wait_time

        if not wait_time_text:
            return 60

        try:
            self.output(f"Шаг {self.step} - Время ожидания перед запросом: {wait_time_text} и случайное смещение: {self.random_offset} минут.", 1)
            self.increase_step()

            if wait_time_text == self.pot_full or self.settings['forceClaim']:
                try:
                    xpath = "//div[contains(text(), 'Получить сейчас')]"
                    button = self.move_and_click(xpath, 10, False, "нажать кнопку запроса", self.step, "присутствует")
                    try:
                        self.driver.execute_script("arguments[0].click();", button)
                        self.increase_step()
                    except Exception:
                        pass

                    self.output(f"Шаг {self.step} - Ждём, пока индикатор ожидания запроса перестанет крутиться...", 2)
                    time.sleep(5)
                    wait = WebDriverWait(self.driver, 240)
                    spinner_xpath = "//*[contains(@class, 'spinner')]"
                    try:
                        wait.until(EC.invisibility_of_element_located((By.XPATH, spinner_xpath)))
                        self.output(f"Шаг {self.step} - Индикатор ожидания запроса остановился.\n", 3)
                    except TimeoutException:
                        self.output(f"Шаг {self.step} - Похоже, сайт подвис - индикатор не исчез вовремя.\n", 2)
                    self.increase_step()
                    wait_time_text = self.get_wait_time(self.step, "после запроса")
                    matches = re.findall(r'(\d+)([hm])', wait_time_text)
                    total_wait_time = apply_random_offset(sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches))
                    self.increase_step()

                    self.get_balance(True)

                    if wait_time_text == self.pot_full:
                        self.output(f"СТАТУС: Таймер ожидания всё ещё показывает: Заполнено.", 1)
                        self.output(f"Шаг {self.step} - Это значит, что либо запрос не удался, либо в игре задержка >4 минут.", 1)
                        self.output(f"Шаг {self.step} - Проверим через 1 час, если запрос не прошёл, попробуем снова.", 2)
                    else:
                        self.output(f"СТАТУС: Успешный запрос: Следующий запрос через {wait_time_text} / {total_wait_time} минут.", 1)
                    return max(60, total_wait_time)

                except TimeoutException:
                    self.output(f"СТАТУС: Время запроса истекло: Возможно, сайт подвис? Попробуем снова через час.", 1)
                    return 60
                except Exception as e:
                    self.output(f"СТАТУС: Произошла ошибка при попытке запроса: {e}\nПодождём час и попробуем снова", 1)
                    return 60

            else:
                matches = re.findall(r'(\d+)([hm])', wait_time_text)
                if matches:
                    total_time = sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches)
                    total_time += 1
                    total_time = max(5, total_time)
                    self.output(f"Шаг {self.step} - Ещё не время запрашивать для этого кошелька. Ждём {total_time} минут, пока хранилище не заполнится.", 2)
                    return total_time
                else:
                    self.output(f"Шаг {self.step} - Нет данных о времени ожидания? Проверим снова через час.", 2)
                    return 60
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла непредвиденная ошибка: {e}", 1)
            return 60
        
    def get_balance(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        balance_text = f'{prefix} БАЛАНС:' if claimed else f'{prefix} БАЛАНС:'
        xpath = "//p[contains(@class, 'wave-balance')]"

        try:
            element = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )

            balance_part = self.driver.execute_script("return arguments[0].textContent.trim();", element)
            
            if balance_part:
                self.output(f"Шаг {self.step} - {balance_text} {balance_part}", priority)
                return balance_part

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)

        self.increase_step()

    def get_wait_time(self, step_number="108", beforeAfter="до запроса", max_attempts=2):
        for attempt in range(1, max_attempts + 1):
            try:
                xpath = "//span[contains(@class, 'boat_balance')]"
                wait_time_element = self.move_and_click(xpath, 5, True, f"получить таймер ожидания {beforeAfter} (метод отсчёта времени)", self.step, "присутствует")
                if wait_time_element is not None:
                    return wait_time_element.text
                xpath = "//div[contains(text(), 'Получить сейчас')]"
                wait_time_element = self.move_and_click(xpath, 10, False, f"получить таймер ожидания {beforeAfter} (метод полного хранилища)", self.step, "присутствует")
                if wait_time_element is not None:
                    return self.pot_full
                    
            except Exception as e:
                self.output(f"Шаг {self.step} - Произошла ошибка при попытке {attempt}: {e}", 3)

        return False

    def get_profit_hour(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        # Сформировать XPath для прибыли
        profit_text = f'{prefix} ПРИБЫЛЬ/ЧАС:'
        profit_xpath = "//span[text()='Aqua Cat']/following-sibling::span[1]"

        try:
            element = self.strip_non_numeric(self.monitor_element(profit_xpath, 15, "прибыль в час"))
            # Проверить, что элемент не None и обработать прибыль
            if element:
                self.output(f"Шаг {self.step} - {profit_text} {element}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Прибыль/Час:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Вывести ошибку как строку для логирования
        
        self.increase_step()

def main():
    claimer = WaveClaimer()
    claimer.run()

if __name__ == "__main__":
    main()