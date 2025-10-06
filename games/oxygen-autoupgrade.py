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

from oxygen import OxygenClaimer

from oxygen import OxygenClaimer
import random
import time
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException

class OxygenAUClaimer(OxygenClaimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/oxygen-autoupgrade.py"
        self.prefix = "Oxygen-Auto:"

    def __init__(self):
        super().__init__()
        self.start_app_xpath = "//div[contains(@class, 'reply-markup-row')]//button[.//span[contains(text(), 'Start App')] or .//span[contains(text(), 'Play Now!')]]"
        self.new_cost_oxy = None
        self.new_cost_food = None
        self.oxy_upgrade_success = None
        self.food_upgrade_success = None

    def full_claim(self):
        self.step = "100"

        self.launch_iframe()
        self.increase_step()

        xpath = "//div[@class='farm_btn']"
        button = self.brute_click(xpath, 10, "нажать кнопку 'Получить'")
        self.increase_step()
        if button:
            self.quit_driver()
            self.launch_iframe()

        xpath = "//div[contains(text(),'Get reward')]"
        self.move_and_click(xpath, 10, True, "нажать кнопку 'Получить награду'", self.step, "clickable")
        self.increase_step()

        self.get_balance(False)
        self.increase_step()

        self.output(f"Шаг {self.step} - Последняя попытка получить счастливый ящик была {self.box_claim}.", 2)
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
                    self.output(f"Шаг {self.step} - Ждем 10 секунд для обновления итогов и таймера...", 3)
                    time.sleep(10)
                    self.increase_step()
                    
                    self.click_daily_buttons()
                    self.increase_step()

                    self.output(f"Шаг {self.step} - Ждем 10 секунд для обновления итогов и таймера...", 3)
                    time.sleep(10)

                    wait_time_text = self.get_wait_time(self.step, "post-claim")
                    matches = re.findall(r'(\d+)([hm])', wait_time_text)
                    calculated_time = sum(int(value) * (60 if unit == 'h' else 1) for value, unit in matches)
                    random_offset = self.apply_random_offset(calculated_time)

                    total_wait_time = random_offset if random_offset > calculated_time else calculated_time

                    self.increase_step()

                    self.get_balance(True)
                    self.get_profit_hour(True)
                    self.increase_step()
                    self.collect_guildbox()
                    self.output(f"Шаг {self.step} - проверяем наличие счастливых ящиков..", 3)
                    xpath = "//div[@class='boxes_cntr']"
                    boxes = self.monitor_element(xpath,15,"количество счастливых ящиков")
                    self.output(f"Шаг {self.step} - Обнаружено {boxes} ящиков для получения.", 3)
                    if boxes:  # This will check if boxes is not False
                        self.output(f"Шаг {self.step} - Обнаружено {boxes} ящиков для получения.", 3)
                        if boxes.isdigit() and int(boxes) > 0:
                            xpath = "//div[@class='boxes_d_wrap']"
                            self.move_and_click(xpath, 10, True, "нажать кнопку ящиков", self.step, "clickable")
                            xpath = "//div[@class='boxes_d_open' and contains(text(), 'Open box')]"
                            box = self.move_and_click(xpath, 10, True, "открыть ящик...", self.step, "clickable")
                            if box:
                                self.box_claim = datetime.now().strftime("%d %B %Y, %I:%M %p")
                                self.output(f"Шаг {self.step} - Дата и время получения ящика обновлены на {self.box_claim}.", 3)
                        else:
                            self.output(f"Шаг {self.step} - Не обнаружено валидное количество ящиков или их количество равно нулю.", 3)
                    else:
                        self.output(f"Шаг {self.step} - Элементы для ящиков не найдены.", 3)
                    if wait_time_text == self.pot_full:
                        self.output(f"СТАТУС: Таймер ожидания все еще показывает: Заполнено.", 1)
                        self.output(f"Шаг {self.step} - Это означает, что либо получение не удалось, либо в игре задержка.", 1)
                        self.output(f"Шаг {self.step} - Проверим через 1 час, если получение не прошло, попробуем снова.", 2)
                    else:
                        self.output(f"СТАТУС: Успешное получение: Следующее получение через {wait_time_text} / {total_wait_time} минут.", 1)
                    return max(60, total_wait_time)

                except TimeoutException:
                    self.output(f"СТАТУС: Процесс получения превысил время ожидания: Возможно, сайт завис? Повторим через час.", 1)
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
                    self.output(f"Шаг {self.step} - Еще не время получать для этого кошелька. Ждем {total_time} минут до заполнения хранилища.", 2)
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

        balance_text = f'{prefix} БАЛАНС:'

        try:
            oxy_balance_xpath = "//span[@class='oxy_counter']"
            food_balance_xpath = "//div[@class='indicator_item i_food' and @data='food']/div[@class='indicator_text']"
            oxy_balance = float(self.monitor_element(oxy_balance_xpath,15,"баланс кислорода"))
            food_balance = float(self.monitor_element(food_balance_xpath,15, "баланс еды"))

            self.output(f"Шаг {self.step} - {balance_text} {oxy_balance:.0f} O2, {food_balance:.0f} еды", priority)

            boost_xpath = "(//div[@class='menu_item' and @data='boosts']/div[@class='menu_icon icon_boosts'])[1]"
            self.move_and_click(boost_xpath, 10, True, "нажать кнопку усиления", self.step, "clickable")

            cost_oxy_upgrade_xpath = "//span[@class='upgrade_price oxy_upgrade']"
            cost_food_upgrade_xpath = "//span[@class='upgrade_price']"

            initial_cost_oxy_upgrade = float(self.monitor_element(cost_oxy_upgrade_xpath, 15, "стоимость улучшения кислорода"))
            initial_cost_food_upgrade = float(self.monitor_element(cost_food_upgrade_xpath,15, "стоимость улучшения еды"))

            self.attempt_upgrade('oxy', 'food', food_balance, initial_cost_oxy_upgrade, cost_oxy_upgrade_xpath)
            self.attempt_upgrade('food', 'oxygen', oxy_balance, initial_cost_food_upgrade, cost_food_upgrade_xpath)

            close_page_button_xpath = "//div[@class='page_close']"
            self.move_and_click(close_page_button_xpath, 10, True, "закрыть всплывающее окно", self.step, "clickable")

            return {
                'oxy': oxy_balance,
                'food': food_balance,
                'initial_cost_oxy': initial_cost_oxy_upgrade,
                'initial_cost_food': initial_cost_food_upgrade,
                'new_cost_oxy': self.new_cost_oxy,
                'new_cost_food': self.new_cost_food,
                'oxy_upgrade_success': self.oxy_upgrade_success,
                'food_upgrade_success': self.food_upgrade_success
            }

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент с текстом '{prefix} Баланс:' не найден.", priority)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {str(e)}", priority)

        self.increase_step()

        return None

    def attempt_upgrade(self, resource_name, cost_name, balance, initial_cost, cost_xpath):
        try:
            balance = float(balance)
            initial_cost = float(initial_cost)

            self.output(f"Шаг {self.step} - Улучшение {resource_name.capitalize()} будет стоить {initial_cost:.1f} {cost_name.capitalize()}, при балансе {balance:.1f}.")

            if balance >= initial_cost:
                click_xpath = f"//div[@class='upgrade_btn' and @data='{resource_name}'][1]"
                upgrade_element = self.move_and_click(click_xpath, 10, True, f"нажать кнопку улучшения {resource_name.capitalize()}", self.step, "clickable")
                new_cost = float(self.monitor_element(cost_xpath,15,f"стоимость {resource_name}"))
                upgrade_success = "Успешно" if new_cost != initial_cost else "Неудачно"
                self.output(f"Шаг {self.step} - Улучшение {resource_name.capitalize()}: {upgrade_success}", 3)
                setattr(self, f'new_cost_{resource_name}', new_cost)
                setattr(self, f'{resource_name}_upgrade_success', upgrade_success)
            else:
                shortfall = initial_cost - balance
                self.output(f"Шаг {self.step} - Недостаточно {cost_name.capitalize()} для улучшения {resource_name.capitalize()}, нехватка: {shortfall:.1f}", 3)
        except ValueError as e:
            self.output(f"Шаг {self.step} - Ошибка: Недопустимое значение для улучшения {resource_name}. Подробности: {str(e)}", 3)

    def collect_guildbox(self, max_attempts=2, timeout=10):
        xpath_guild_icon = "//div[@class='menu_icon icon_guilds']"
        xpath_deposit_button = "//div[@class='guilds_btn guilds_send_oxy' and text()='Deposit']"
        xpath_check_claimed = "//div[contains(text(), 'You can deposit in:')]"
        close_page_button_xpath = "//div[@class='page_close']"

        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    self.quit_driver()
                    self.launch_iframe()

                if not self.move_and_click(xpath_guild_icon, timeout, True, "нажать иконку гильдии", self.step, "clickable"):
                    self.output(f"Шаг {self.step} - Попытка {attempt} - Не удалось нажать иконку гильдии.", 1)
                    continue

                if not self.move_and_click(xpath_deposit_button, timeout, True, "нажать кнопку 'Внести'", self.step, "clickable"):
                    self.output(f"Шаг {self.step} - Попытка {attempt} - Не удалось нажать кнопку 'Внести', возможно вы не член гильдии.", 3)
                    break

                message = self.monitor_element(xpath_check_claimed, timeout, "депозит в гильдийский ящик")
                if message:
                    self.output(f"Шаг {self.step} - Сообщение гильдийского ящика: {message}.", 2)

                self.output(f"Шаг {self.step} - Успешное получение гильдийского ящика: действия выполнены успешно!", 2)
                return True

            except TimeoutException:
                self.output(f"Шаг {self.step} - Элемент не найден за {timeout} секунд при попытке {attempt}.", 1)
            except ElementClickInterceptedException:
                self.output(f"Шаг {self.step} - Клик по элементу был перехвачен при попытке {attempt}. Пробуем снова.", 3)
            except Exception as e:
                self.output(f"Шаг {self.step} - Ошибка при попытке {attempt}: {str(e)}", 1)
        
            finally:
                self.move_and_click(close_page_button_xpath, 10, True, "закрыть всплывающее окно", self.step, "clickable")

        self.output(f"Шаг {self.step} - Не удалось завершить получение гильдийского ящика после нескольких попыток.", 2)
        return False

def main():
    claimer = OxygenAUClaimer()
    claimer.run()

if __name__ == "__main__":
    main()