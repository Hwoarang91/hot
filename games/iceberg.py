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
import requests

from claimer import Claimer

class IcebergClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/iceberg.py"
        self.prefix = "Iceberg:"
        self.url = "https://web.telegram.org/k/#@IcebergAppBot"
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.allow_early_claim = False
        self.start_app_xpath = "//div[contains(@class,'new-message-bot-commands-view')][contains(normalize-space(.),'Play')]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='Iceberg']]"
        self.balance_xpath = f"//p[normalize-space(.)='Your balance']/ancestor::div[2]/p"
        self.time_remaining_xpath = "//p[contains(text(), 'Receive after')]/span"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()
        self.random_offset = random.randint(max(self.settings['lowestClaimOffset'], 0), max(self.settings['highestClaimOffset'], 0))
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
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение отведенного времени.", 1)

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 1)

    def full_claim(self):

        self.step = "100"
        self.launch_iframe()

        # Есть ли вступительный экран? Если да, очистим его!
        xpath = "//button[div[text()='Skip']]"
        self.brute_click(xpath, 20, "предварительный экран информации (может отсутствовать)")

        # Мы занимаемся фармом? Если нет, начинаем!
        xpath = "//button[div[text()='Start farming']]"
        self.brute_click(xpath, 20, "начальный запуск фарма (может отсутствовать)")

        pre_balance = self.get_balance(self.balance_xpath, False)
        self.increase_step()

        remaining_time = self.get_wait_time(self.time_remaining_xpath, self.step, "до запроса")
        if remaining_time:
            self.output(f"СТАТУС: Запрос еще не готов, будем спать {remaining_time} минут.", 2)
            return min(30,remaining_time)

        self.increase_step()
    
        # Мы дошли до этого момента, попробуем запросить!
        xpath = "//button[contains(text(), 'Collect')]"
        success = self.brute_click(xpath, 20, "сбор очков")
        self.increase_step()

        # И снова начинаем фармить.
        xpath = "//button[div[text()='Start farming']]"
        self.brute_click(xpath, 20, "запуск фарма после запроса (может отсутствовать)")
        self.increase_step()

        # И проверяем баланс после запроса
        post_balance = self.get_balance(self.balance_xpath, True)

        try:
            if pre_balance is not None and post_balance is not None:
                pre_balance_float = float(pre_balance)
                post_balance_float = float(post_balance)
                if post_balance_float > pre_balance_float:
                    success_text = "Запрос выполнен успешно."
                else:
                    success_text = "Возможно, запрос не удался."
            else:
                success_text = "Проверка запроса не удалась из-за отсутствия информации о балансе."
        except ValueError:
            success_text = "Проверка запроса не удалась из-за неверного формата баланса."

        self.increase_step()

        # Сохраняем время ожидания для дальнейшего использования
        remaining_time = self.get_wait_time(self.time_remaining_xpath, self.step, "после запроса")
        
        # В конце подведем итог времени до следующего запуска
        if remaining_time:
            self.output(f"СТАТУС: {success_text} Спим {remaining_time} минут.", 2)
            return remaining_time
        # Если дошли до конца без действий, возвращаемся через час
        return 60

def main():
    claimer = IcebergClaimer()
    claimer.run()

if __name__ == "__main__":
    main()