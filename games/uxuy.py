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

class UXUYlaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/uxuy.py"
        self.prefix = "UXUY:"
        self.url = "https://web.telegram.org/k/#@UXUYbot"
        self.pot_full = "Filled"
        self.pot_filling = "to fill"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.allow_early_claim = False
        self.start_app_xpath = "//div[contains(@class, 'new-message-bot-commands') and .//div[text()='Wallet']]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='UXUY Wallet']]"
        self.balance_xpath = f"//div[contains(text(), 'UP') and contains(@class, 'text-[44px]')]"
        self.time_remaining_xpath = "//div[contains(text(), 'Next claim in')]"

    def __init__(self):
        self.settings_file = "variables.txt"
        self.status_file_path = "status.txt"
        self.wallet_id = ""
        self.load_settings()
        self.random_offset = random.randint(min(self.settings['lowestClaimOffset'], 0), min(self.settings['highestClaimOffset'], 0))
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
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение установленного времени ожидания.", 1)
        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 1)

    def full_claim(self):

        self.step = "100"

        self.launch_iframe()
        
        xpath = "//div/span[contains(normalize-space(.), 'Claim')]"
        success = self.move_and_click(xpath, 15, True, "проверить, готов ли клик для получения награды", self.step, "clickable")
        self.increase_step()
        if success:
            xpath = "//div/span[contains(normalize-space(.), 'Claim')]"
            self.move_and_click(xpath, 15, True, "проверить, готов ли клик для получения награды", self.step, "clickable")
            self.increase_step()
        
        xpath = "//div[normalize-space(text())='UXUY Point']/following-sibling::div[1]"
        self.move_and_click(xpath, 15, True, "перейти на страницу фарминга", self.step, "clickable")
        self.increase_step()
              
        claim_status = "pre-claim"
        
        if success:
            claim_status = "post-claim"
            update_text = "Получение награды прошло успешно"
            bal_status = True
        else:
            update_text = "Награда не получена"
            bal_status = False

        self.get_balance(self.balance_xpath, bal_status)

        remaining_wait_time = self.get_wait_time(self.time_remaining_xpath, self.step, claim_status)
        self.increase_step()

        if remaining_wait_time:
            self.random_offset = self.apply_random_offset(remaining_wait_time)
            self.output(f"СТАТУС: {update_text}. Время ожидания {self.show_time(self.random_offset)}.", 1)
            return self.random_offset
        else:
            remaining_wait_time = 60
            self.random_offset = self.apply_random_offset(remaining_wait_time)
            self.output(f"СТАТУС: Не удалось определить точное время ожидания. Возвращаемся через {self.show_time(self.random_offset)}.", 1)
            return self.random_offset

def main():
    claimer = UXUYlaimer()
    claimer.run()

if __name__ == "__main__":
    main()