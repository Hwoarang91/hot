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

from timefarm import TimeFarmClaimer

class TimeFarmAUClaimer(TimeFarmClaimer):

    last_success_timestamp = None  # Переменная класса для хранения отметки времени в памяти

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/timefarm-autostake.py"
        self.prefix = "TimeFarm-AutoStake:"

    def __init__(self):
        super().__init__()
        self.start_app_xpath = "//span[contains(text(), 'Open App')]"

    def save_timestamp(self):
        TimeFarmAUClaimer.last_success_timestamp = datetime.now()

    def load_timestamp(self):
        return TimeFarmAUClaimer.last_success_timestamp

    def stake_coins(self):
        # Проверяем, прошло ли менее 24 часов с момента последней успешной операции
        last_success = self.load_timestamp()
        if last_success:
            elapsed_time = datetime.now() - last_success
            if elapsed_time < timedelta(hours=24):
                print("С момента последней успешной операции прошло менее 24 часов.")
                return
        
        # Переходим на вкладку заработка
        xpath = "//div[@class='tab-title' and contains(., 'Earn')]"
        success = self.move_and_click(xpath, 20, True, "переключиться на вкладку 'Заработок'", self.step, "clickable")
        if not success:
            return
        self.increase_step()

        # Переходим на вкладку стейкинга
        xpath = "//div[@class='title' and contains(., 'Staking')]"
        success = self.move_and_click(xpath, 20, True, "переключиться на вкладку 'Стейкинг'", self.step, "clickable")
        if not success:
            return
        self.increase_step()

        # Проверим, есть ли существующий клейм
        xpath = "(//div[not(contains(@class, 'disabled'))]/div[@class='btn-text' and text()='Claim'])[1]"
        success = self.move_and_click(xpath, 20, True, "попытаться получить самый старый клейм (если есть)", self.step, "clickable")
        if success:
            self.output(f"Шаг {self.step} - Мы смогли собрать самый старый клейм.", 3)
        else:
            self.output(f"Шаг {self.step} - Похоже, старых клеймов для стейкинга не было.", 3)
        self.increase_step()

        # Нажимаем кнопку стейкинга
        xpath = "//div[@class='btn-text' and (contains(., 'Stake') or contains(., 'Start staking')) and not(ancestor::div[contains(@class, 'disabled')])]"
        success = self.move_and_click(xpath, 20, True, "нажать кнопку 'Стейк'", self.step, "clickable")
        if not success:
            self.output(f"Шаг {self.step} - Похоже, что дальнейший стейкинг сейчас недоступен, перезапускаем браузер.", 2)
            self.quit_driver()
            self.launch_iframe()
            return
        self.increase_step()

        # Выбираем опцию по умолчанию (3 дня), нажав продолжить
        xpath = "(//div[@class='btn-text' and contains(., 'Continue')])[1]"
        success = self.move_and_click(xpath, 20, True, "нажать кнопку 'Продолжить'", self.step, "clickable")
        if not success:
            return
        self.increase_step()

        # Выбираем опцию Макс
        xpath = "//div[@class='percent' and contains(., 'MAX')]"
        success = self.move_and_click(xpath, 20, True, "нажать опцию 'МАКС'", self.step, "clickable")
        if not success:
            return
        self.increase_step()

        # Нажимаем кнопку "Продолжить"
        xpath = "(//div[@class='btn-text' and contains(., 'Continue')])[2]"
        success = self.move_and_click(xpath, 20, True, "нажать кнопку 'Продолжить'", self.step, "clickable")
        if not success:
            self.output(f"Шаг {self.step} - Похоже, что дальнейший стейкинг сейчас недоступен, перезапускаем браузер.", 2)
            self.quit_driver()
            self.launch_iframe()
            return
        self.increase_step()

        # Нажимаем кнопку "Стейк"
        xpath = "//div[@class='btn-text' and contains(., 'Stake')]"
        success = self.move_and_click(xpath, 20, True, "нажать кнопку 'Стейк'", self.step, "clickable")
        if not success:
            self.output(f"Шаг {self.step} - Похоже, что дальнейший стейкинг сейчас недоступен, перезапускаем браузер.", 2)
            self.quit_driver()
            self.launch_iframe()
            return
        self.increase_step()

        xpath = "//*[contains(text(), \"You've successfully\")]"
        if self.move_and_click(xpath, 5, False, "проверить успешность", self.step, "visible"):
            self.output(f"СТАТУС: Мы нажали ссылку Стейкинга и получили подтверждение успеха.", 1)
            self.increase_step()
            self.save_timestamp()  # Сохраняем отметку времени после успеха
            return "Стейкинг на 3 дня выполнен успешно. "
        else:
            self.output(f"СТАТУС: Мы нажали ссылку Стейкинга (3-дневный срок/максимальное количество монет).", 1)
            self.increase_step()
            return "Попытка стейкинга выполнена. "

def main():
    claimer = TimeFarmAUClaimer()
    claimer.run()

if __name__ == "__main__":
    main()