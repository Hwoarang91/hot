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

class HamsterKombatClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/hamsterkombat.py"
        self.prefix = "HammyKombat:"
        self.url = "https://web.telegram.org/k/#@hamster_kombat_bot"
        self.pot_full = "Заполнено"
        self.pot_filling = "Добыча"
        self.seed_phrase = None
        self.forceLocalProxy = True
        self.forceRequestUserAgent = False
        self.start_app_xpath = "//button//span[contains(text(), 'Играть в 1')] | //div[contains(@class, 'new-message-bot-commands-view') and contains(text(), 'Играть')]"

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
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение времени ожидания.",1)

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}",1)
            
    def full_claim(self):
        self.step = "100"
        self.launch_iframe()
        
        # Попытка получить ежедневную награду, если она есть
        xpath = "//button[span[text()='Получить']]"
        success = self.move_and_click(xpath, 20, True, "поиск кнопки получения ежедневной награды.", self.step, "clickable")
        self.increase_step()
    
        # И бонус "спасибо хомяку"
        xpath = "//button[span[text()='Спасибо, Хомяк']]"
        success = self.move_and_click(xpath, 20, True, "поиск бонуса 'Спасибо, хомяк'.", self.step, "clickable")
        self.increase_step()
        
        # Захват начальных значений до получения награды
        initial_remains = self.get_remains()  # Захват начального количества оставшихся кликов
        initial_balance = self.get_balance(False)  # Захват начального баланса (до получения награды)
        
        # Убедиться, что начальный баланс получен корректно
        if initial_balance is None:
            self.output(f"Шаг {self.step} - Не удалось получить начальный баланс.", 2)

        self.output(f"Шаг {self.step} - Начальные остатки: {initial_remains}, Начальный баланс: {initial_balance}", 3)
    
        # Получить остатки после получения награды, но до кликов
        starting_clicks = initial_remains
        self.output(f"Шаг {self.step} - Начальное количество кликов (остаток после получения): {starting_clicks}", 3)
    
        # Вызывать click_ahoy только если starting_clicks - число и больше 0
        if isinstance(starting_clicks, (int, float)) and starting_clicks > 0:
            self.click_ahoy(starting_clicks)
    
            # Получить остатки после click_ahoy
        remains_after_clicks = self.get_remains()
    
        # Показать оставшиеся клики, если это валидное число
        if isinstance(remains_after_clicks, (int, float)):
            self.output(f"Шаг {self.step} - Остаток кликов: {remains_after_clicks}", 3)
        else:
            self.output(f"Шаг {self.step} - Не удалось получить валидный остаток после кликов.", 3)
    
        # Вернуть текущую прибыль в час
        self.get_profit_hour(True)

        # Получить итоговый баланс после кликов
        final_balance = self.get_balance(True)
    
        # Убедиться, что итоговый баланс получен корректно
        if final_balance is None:
            self.output(f"Шаг {self.step} - Не удалось получить итоговый баланс.", 2)

        # Рассчитать разницы
        remains_diff = initial_remains - remains_after_clicks if isinstance(initial_remains, (int, float)) and isinstance(remains_after_clicks, (int, float)) else 0
        balance_diff = final_balance - initial_balance if isinstance(initial_balance, (int, float)) and isinstance(final_balance, (int, float)) else 0
    
        # Вывести результат с приоритетом 1
        self.output(f"СТАТУС: Мы использовали {remains_diff} энергии, чтобы получить {balance_diff} дополнительных токенов.", 1)

        random_timer = random.randint(20, 60)
        self.output(f"Шаг {self.step} - Зарядка энергии в течение {random_timer} минут.", 3)
        return random_timer

    def get_balance(self, claimed=False):

        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        # Динамически настроить приоритет логирования
        priority = max(self.settings['verboseLevel'], default_priority)

        # Сформировать XPath для баланса
        balance_text = f'{prefix} БАЛАНС:'
        balance_xpath = f"//div[@class='user-balance-large-inner']/p"

        try:
            element = self.monitor_element(balance_xpath, 10, "получить баланс")

            # Проверить, что элемент не None и обработать баланс
            if element:
                cleaned_balance = self.strip_html_and_non_numeric(element)
                self.output(f"Шаг {self.step} - {balance_text} {cleaned_balance}", priority)
                return float(cleaned_balance)
        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Ошибка в виде строки для логирования

        # Функция увеличения шага, предположительно для перехода к следующему шагу
        self.increase_step()


    def get_remains(self):
        remains_xpath = "//div[@class='user-tap-energy']/p"
        try:
            # Переместиться и кликнуть по элементу, если нужно
            first = self.move_and_click(remains_xpath, 10, False, "убрать оверлеи", self.step, "visible")
            
            # Отслеживать элемент для получения содержимого
            remains_element = self.monitor_element(remains_xpath, 15, "получить оставшиеся клики")
            
            # Проверить, найден ли remains_element и получить его текст
            if remains_element:
                remains_text = remains_element.strip()  # Получить текст и убрать пробелы
                if " / " in remains_text:
                    n1, n2 = remains_text.split(" / ")  # Разделить строку на две части
                    n1, n2 = int(n1), int(n2)  # Преобразовать обе части в целые числа
                    
                    # Вывести результат с приоритетом 3
                    self.output(f"Шаг {self.step} - Осталось энергии: {n1} из максимума {n2}.", 3)
                    
                    # Вернуть n1 (оставшиеся клики)
                    return n1
                else:
                    # Если формат текста не соответствует ожидаемому
                    self.output(f"Шаг {self.step} - Неожиданный формат: '{remains_text}'", 3)
                    return None
            else:
                # Если элемент не найден
                self.output(f"Шаг {self.step} - Элемент с 'Остаток' не найден.", 3)
                return None
        except NoSuchElementException:
            # Обработка случая, когда элемент не найден
            self.output(f"Шаг {self.step} - Элемент с 'Остаток' не найден.", 3)
            return None
        except Exception as e:
            # Обработка любых других исключений
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", 3)
            return None

    def click_ahoy(self, remains):
        xpath = "//div[@class='user-tap-energy']/p"
        self.move_and_click(xpath, 10, False, "подойти ближе к хомяку!", self.step, "visible")
    
        self.output(f"Шаг {self.step} - У нас есть {remains} целей для клика. Это может занять некоторое время!", 3)
    
        try:
            # Найти элемент по XPath, чтобы убедиться, что страница загрузилась
            element = self.driver.find_element(By.XPATH, xpath)
        except Exception as e:
            self.output(f"Шаг {self.step} - Ошибка при поиске элемента: {str(e)}", 2)
            return None
    
        if not isinstance(remains, (int, float)) or remains <= 0:
            self.output(f"Шаг {self.step} - Некорректное значение 'remains': {remains}", 2)
            return None
    
        # Рассчитать max_clicks как 80% от оставшихся кликов
        max_clicks = max(1, int(remains * 0.8))  # 80% от remains
        self.output(f"Шаг {self.step} - Установлено максимальное количество кликов: 80% от остатка: {max_clicks}", 3)
    
        # Размер партии - 100 кликов за раз
        batch_size = 100
        total_clicks = 0
        # Увеличить таймаут скрипта до 10 минут (600 секунд)
        self.driver.set_script_timeout(600)
    
        while total_clicks < max_clicks and remains > 0:
            # Рассчитать количество кликов для текущей партии
            batch_clicks = min(batch_size, max_clicks - total_clicks)
    
            # Определить JavaScript функцию для симуляции batch_clicks кликов по кнопке
            click_script = f"""
            return new Promise((resolve) => {{
                let clicks = 0;
                const xPositions = [135, 150, 165];  // Цикл по этим позициям по X

                function performClick() {{
                    const clickButton = document.getElementsByClassName('user-tap-button')[0];
                    if (clickButton && clicks < {batch_clicks}) {{
                        xPositions.forEach((xPos) => {{
                            // Случайная позиция по Y между 290 и 310
                            const randomY = Math.floor(Math.random() * 21) + 290;
                            const clickEvent1 = new PointerEvent('pointerdown', {{clientX: xPos, clientY: randomY}});
                            const clickEvent2 = new PointerEvent('pointerup', {{clientX: xPos, clientY: randomY}});
                            clickButton.dispatchEvent(clickEvent1);
                            clickButton.dispatchEvent(clickEvent2);
                        }});
                        clicks += 3;  // Увеличить на 3 после каждого набора кликов

                        // Случайная задержка между 200 и 400 миллисекундами для следующего набора кликов
                        const randomDelay = Math.floor(Math.random() * 201) + 200;  
                        setTimeout(performClick, randomDelay);
                    }} else {{
                        console.log('Завершено кликов: ' + clicks + ' раз');
                        resolve(clicks);  // Разрешить Promise с итоговым количеством кликов для этой партии
                    }}
                }}

                // Начать первый набор кликов сразу
                performClick();
            }});
            """
    
            # Выполнить JavaScript для текущей партии и дождаться завершения
            try:
                batch_result = self.driver.execute_script(click_script)
                total_clicks += batch_result
                remains -= batch_result
    
                self.output(f"Шаг {self.step} - Выполнено {batch_result} кликов. Итого: {total_clicks} кликов. Осталось: {remains}.", 2)
            except Exception as e:
                self.output(f"Шаг {self.step} - Ошибка при выполнении JS функции клика: {str(e)}", 2)
                return None
    
            # Проверить, достигли ли максимума кликов или остатков
            if total_clicks >= max_clicks or remains <= 0:
                break
    
            # Необязательно: задержка между партиями для имитации поведения человека
            time.sleep(random.uniform(0.2, 0.5))  # Короткая задержка между партиями
    
        self.output(f"Шаг {self.step} - Сессия завершена с {total_clicks} кликами. Осталось целей: {remains}.", 2)

    def get_profit_hour(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3

        priority = max(self.settings['verboseLevel'], default_priority)

        # Сформировать XPath для прибыли
        profit_text = f'{prefix} ПРИБЫЛЬ/ЧАС:'
        profit_xpath = "//div[@class='price-value']"

        try:
            element = self.strip_non_numeric(self.monitor_element(profit_xpath, 15, "получить прибыль в час"))

            # Проверить, что элемент не None и обработать прибыль
            if element:
                self.output(f"Шаг {self.step} - {profit_text} {element}", priority)

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с '{prefix} Прибыль/Час:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)  # Ошибка в виде строки для логирования
        
        self.increase_step()

def main():
    claimer = HamsterKombatClaimer()
    claimer.run()

if __name__ == "__main__":
    main()