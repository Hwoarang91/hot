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
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException, ElementClickInterceptedException, UnexpectedAlertPresentException
from datetime import datetime, timedelta
from selenium.webdriver.chrome.service import Service as ChromeService

from tabizoo import TabizooClaimer

class TabizooAUClaimer(TabizooClaimer):
    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/tabizoo-autoupgrade.py"
        self.prefix = "TabiZoo-AutoUpgrade:"

    def __init__(self):
        super().__init__()

    def attempt_upgrade(self, balance):
        try:
            start_lvl = None
            end_lvl = None
            # пытается выполнить одно улучшение за сессию получения награды
            xpath = "//span[contains(text(), 'Lv')]"
            current_level = self.monitor_element(xpath, 15, "текущий уровень")
            original_balance = balance
            self.increase_step()
            if current_level:
                self.output(f"Шаг {self.step} - Текущий уровень: {current_level}", 2)

            xpath = "//img[contains(@src, 'level_icon')]"
            if self.brute_click(xpath, 10, "нажать на вкладку 'Улучшение'"):
                self.increase_step()

                xpath = "//label[text()='Consume']/following-sibling::p//span"
                upgrade_cost = None
                upgrade_cost = self.monitor_element(xpath, 15, "стоимость улучшения")
                self.increase_step()
                if upgrade_cost:
                    self.output(f"Шаг {self.step} - Стоимость улучшения: {upgrade_cost}", 3)

                xpath = "//div[text()='Insufficient Balance']"
                no_money = self.move_and_click(xpath, 10, False, "проверить, достаточно ли средств (таймаут означает, что средств достаточно!)", self.step, "доступно для клика")
                self.increase_step()
                if no_money:
                    self.output(f"Шаг {self.step} - Улучшение стоит {upgrade_cost}, но у вас только {balance}.", 3)
                    return

                for attempt in range(3):
                    xpath = "//div[text()='Upgrade']"
                    self.brute_click(xpath, 10, f"попытка {attempt+1} нажать кнопку 'Улучшить'")
                    self.increase_step()
                    
                    # Проверяем, увеличилась ли стоимость улучшения
                    new_upgrade_cost = self.monitor_element("//label[text()='Consume']/following-sibling::p//span", 10, "стоимость улучшения после нажатия")
                    
                    if new_upgrade_cost and new_upgrade_cost != upgrade_cost:
                        break  # Выход из цикла, если стоимость изменилась, значит улучшение, вероятно, прошло

                self.quit_driver()
                self.launch_iframe()
                xpath = "//span[contains(text(), 'Lv')]"
                new_level = self.monitor_element(xpath, 15, "текущий уровень")
                self.increase_step()

                if current_level:
                    start_lvl = float(self.strip_html_and_non_numeric(current_level))
                if new_level:
                    end_lvl = float(self.strip_html_and_non_numeric(new_level))

                if start_lvl and new_level:
                    if end_lvl > start_lvl:
                        self.output(f"СТАТУС: Улучшено с {current_level} до {new_level} за {upgrade_cost}.", 2)
                    else:
                        self.output(f"Шаг {self.step} - Похоже, последовательность улучшения не удалась.", 2)
                else:
                    self.output(f"Шаг {self.step} - Не удалось прочитать некоторые уровни.", 2)

        except NoSuchElementException as e:
            self.output(f"Шаг {self.step} - Элемент не найден: {str(e)}", 1)
        except TimeoutException as e:
            self.output(f"Шаг {self.step} - Произошло превышение времени ожидания: {str(e)}", 1)
        except ElementClickInterceptedException as e:
            self.output(f"Шаг {self.step} - Клик был перехвачен: {str(e)}", 1)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла неожиданная ошибка: {str(e)}", 1)

def main():
    claimer = TabizooAUClaimer()
    claimer.run()

if __name__ == "__main__":
    main()