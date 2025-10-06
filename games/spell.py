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

import requests
import urllib.request
from claimer import Claimer

class SpellClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/spell.py"
        self.prefix = "Spell:"
        self.url = "https://web.telegram.org/k/#@spell_wallet_bot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.allow_early_claim = False
        self.start_app_xpath = "//div[@class='reply-markup-row']//span[contains(text(),'Open Spell')]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='Spell Wallet']]"

    def charge_until_complete(self, max_seconds: float = 10.0, pause: float = 0.25) -> bool:
        """
        Многократно нажимает кнопку 'Зарядка…' в течение max_seconds.
        Останавливается раньше, если прогресс достигает 100% или появляется интерфейс 'Крутить колесо'.
        Возвращает True, если зарядка, вероятно, завершена, иначе False.
        """
        start = time.time()
    
        # надежные селекторы для той же кнопки/состояния
        charging_xpaths = [
            # Кнопка с явным текстом "Зарядка..."
            "//button[.//p[normalize-space()='Charging...']]",
    
            # Кнопка с индикатором прогресса + меткой 'Charging'
            "//button[.//div[@role='progressbar'] и .//p[contains(normalize-space(),'Charging')]]",
    
            # Кнопка, владеющая индикатором прогресса с числовым значением (1..99)
            "//div[@role='progressbar' и number(@aria-valuenow) >= 1 и number(@aria-valuenow) < 100]/ancestor::button[1]",
    
            # Кнопка с отображением процента (например, 20%)
            "//button[.//div[@role='progressbar'] и .//div[contains(normalize-space(.), '%')]]",
        ]
    
        # быстрые проверки "завершения"
        spin_xpath   = "//p[contains(normalize-space(.), 'Spin the Wheel')]"
        percent_node = "//div[@role='progressbar' и @aria-valuenow]"
    
        def read_progress() -> float | None:
            try:
                el = self.driver.find_element(By.XPATH, percent_node)
                val = el.get_attribute("aria-valuenow")
                return float(val) if val is not None else None
            except Exception:
                return None
    
        while time.time() - start < max_seconds:
            # уже закончено?
            try:
                if self.driver.find_elements(By.XPATH, spin_xpath):
                    self.output(f"Шаг {self.step} - Появилось колесо; зарядка завершена.", 3)
                    return True
            except Exception:
                pass
    
            prog = read_progress()
            if prog is not None and prog >= 100:
                self.output(f"Шаг {self.step} - Прогресс {prog:.0f}% достигнут; зарядка завершена.", 3)
                return True
    
            # пробуем каждый селектор и кликаем один раз
            clicked_this_cycle = False
            for xp in charging_xpaths:
                try:
                    btn = self.driver.find_element(By.XPATH, xp)
                    # делаем просто и быстро: сначала нативный клик, потом JS
                    try:
                        ActionChains(self.driver).move_to_element(btn).pause(0.02).click(btn).perform()
                        clicked_this_cycle = True
                        break
                    except Exception:
                        try:
                            self.driver.execute_script("arguments[0].click();", btn)
                            clicked_this_cycle = True
                            break
                        except Exception:
                            continue
                except Exception:
                    continue
    
            if not clicked_this_cycle:
                # небольшая диагностика (низкий уровень шума)
                if self.settings.get('debugIsOn'):
                    self.debug_information("Кнопка зарядки не найдена в этом цикле", "warning")
            time.sleep(pause)
    
        self.output(f"Шаг {self.step} - Цикл зарядки завершился после {max_seconds}с без явного завершения.", 2)
        return False

    def spell_accept_and_continue(self):
        checkbox_xpath = "//span[@aria-hidden='true' и содержит(@class,'chakra-checkbox__control')]"
        btn_xpath      = "//button[contains(@class,'chakra-button') и normalize-space()='Начать']"
    
        try:
            # Ищем чекбокс без исключений (0/1 элементов)
            boxes = self.driver.find_elements(By.XPATH, checkbox_xpath)
            if not boxes:
                # Чекбокс уже отсутствует → продолжаем
                self.output(f"Шаг {self.step} - Чекбокс отсутствует; предполагается, что уже принят. Продолжаем.", 2)
                try:
                    btns = self.driver.find_elements(By.XPATH, btn_xpath)
                    if btns:
                        self.driver.execute_script("arguments[0].click();", btns[0])
                        self.output(f"Шаг {self.step} - Нажата кнопка 'Начать'.", 2)
                except Exception:
                    pass
                return True
    
            checkbox = boxes[0]
    
            # Прокрутка до видимости и имитация реального клика
            self.driver.execute_script("""
                const el = arguments[0];
                el.scrollIntoView({block:'center', inline:'center'});
                const r = el.getBoundingClientRect();
                const x = r.left + r.width/2, y = r.top + r.height/2;
                for (const t of ['pointerdown','mousedown','mouseup','click']) {
                  el.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, clientX:x, clientY:y}));
                }
            """, checkbox)
            time.sleep(0.5)
    
            # Проверяем переключение (или просто продолжаем, если кнопка стала активной)
            if checkbox.get_attribute("data-checked") is not None:
                self.output(f"Шаг {self.step} - Чекбокс успешно отмечен.", 2)
            else:
                self.output(f"Шаг {self.step} - Чекбокс не сообщил data-checked; продолжаем в любом случае.", 2)
    
            # Пытаемся нажать "Начать", если есть
            btns = self.driver.find_elements(By.XPATH, btn_xpath)
            if btns:
                self.driver.execute_script("arguments[0].click();", btns[0])
                self.output(f"Шаг {self.step} - Нажата кнопка 'Начать'.", 2)
            else:
                self.output(f"Шаг {self.step} - Кнопка 'Начать' отсутствует (нормально).", 3)
    
            return True
    
        except Exception as e:
            # Плавное восстановление: не прерываем поток, если этот UI уже пройден
            self.output(f"Шаг {self.step} - Последовательность чекбокса/продолжения: {type(e).__name__}: {e}. Продолжаем.", 2)
            if self.settings.get('debugIsOn'):
                self.debug_information(f"Последовательность чекбокса Spell (нефатальная ошибка): {e}")
            return True

    def next_steps(self):
        if self.step:
            pass
        else:
            self.step = "01"

        try:
            self.launch_iframe()
            self.increase_step()

            self.spell_accept_and_continue()
            
            # Получить баланс
            balance_xpath = "//h2[contains(@class, 'chakra-heading css-1ougcld')]"
            self.get_balance(balance_xpath, False)

            # Финальная уборка
            self.set_cookies()

        except TimeoutException:
            self.output(f"Шаг {self.step} - Не удалось найти или переключиться на iframe в течение времени ожидания.", 1)

        except Exception as e:
            self.output(f"Шаг {self.step} - Произошла ошибка: {e}", 1)

    def full_claim(self):
        # Инициализировать status_text
        status_text = ""
        balance_xpath = "//div[contains(@class, 'css-6e4jug')]"

        # Запустить iframe
        self.step = "100"
        self.launch_iframe()

        self.spell_accept_and_continue()

        # Захватить баланс до запроса
        before_balance = self.get_balance(balance_xpath, False)

        # Получить таймер ожидания, если есть
        self.increase_step()
        remaining_wait_time = self.get_wait_time(self.step, "post-claim")
            
        # Получить таймер ожидания, если есть
        self.increase_step()
        pre_wait_min = self.get_wait_time(before_after="pre-claim")

        if pre_wait_min > 0:
            # Соблюдаем таймер и выходим раньше
            wait_with_jitter = self.apply_random_offset(pre_wait_min)
            self.output(
                f"СТАТУС: Исходное время ожидания {pre_wait_min} минут, спим "
                f"{wait_with_jitter} минут с учетом случайного смещения.", 1
            )
            return max(wait_with_jitter, 60)
            
        # Предварительный запрос
        pre_claim = "//button[contains(normalize-space(.), 'Нажмите, чтобы получить') и содержит(normalize-space(.), 'MANA')]"
        self.brute_click(pre_claim, 12, "нажать предварительную кнопку 'Получить'")
        self.increase_step()
        
        # Быстрая зарядка около 10 секунд (клики около 4 раз в секунду)
        self.charge_until_complete(max_seconds=10, pause=0.25)
        self.increase_step()
        
        # Перезагрузить браузер после запроса
        self.quit_driver()
        self.launch_driver()
            
        # Баланс не получен ранее из-за приоритета вывода
        if not before_balance:
            after_balance = self.get_balance(balance_xpath, True)
        
        # Получить таймер ожидания, если есть
        self.increase_step()
        post_wait_min = self.get_wait_time(before_after="post-claim")  # правильный вызов

        # Ежедневная головоломка (опционально)
        if self.daily_reward():
            status_text += "Ежедневная головоломка отправлена"

        # Если таймер отсутствует или равен нулю, предполагаем задержку / повтор позже
        if not post_wait_min:
            self.output("СТАТУС: Таймер ожидания все еще показывает: Заполнено.", 1)
            self.output(f"Шаг {self.step} - Это означает, что либо запрос не удался, либо в игре задержка.", 1)
            self.output(f"Шаг {self.step} - Проверим снова через 1 час, и если запрос не обработан, попробуем снова.", 2)
            return 60

        wait_with_jitter = self.apply_random_offset(post_wait_min)
        if status_text == "":
            self.output("СТАТУС: Запрос или Ежедневная головоломка отсутствуют в этот раз", 3)
        else:
            self.output(f"СТАТУС: {status_text}", 3)

        self.output(
            f"СТАТУС: Исходное время ожидания {post_wait_min} минут, спим "
            f"{wait_with_jitter} минут с учетом случайного смещения.", 1
        )
        return max(wait_with_jitter, 60)

    def daily_reward(self):
        return
        # Переключиться на вкладку Квесты и проверить, решена ли головоломка
        xpath = "//p[contains(., 'Квесты')]"
        success = self.move_and_click(xpath, 10, True, "нажать на вкладку 'Квесты'", self.step, "кликабельно")
        self.increase_step()
        
        if not success:
            self.quit_driver()
            self.launch_iframe()
            self.move_and_click(xpath, 10, True, "нажать на вкладку 'Квесты'", self.step, "кликабельно")
            self.increase_step()

        xpath = "//div[contains(@class, 'css-ehjmbb')]//p[contains(text(), 'Выполнено')]"
        success = self.move_and_click(xpath, 10, True, "проверить, решена ли головоломка", self.step, "кликабельно")
        self.increase_step()
        if success:
            return False

        xpath = "//p[contains(., 'Ежедневная головоломка')]"
        self.move_and_click(xpath, 10, True, "нажать на ссылку 'Ежедневная головоломка'", self.step, "кликабельно")
        self.increase_step()

        # Получить 4-значный код из файла на GitHub с помощью urllib
        url = "https://raw.githubusercontent.com/thebrumby/HotWalletClaimer/main/extras/rewardtest"
        try:
            with urllib.request.urlopen(url) as response:
                content = response.read().decode('utf-8').strip()
            self.output(f"Шаг {self.step} - Получен код с GitHub: {content}", 3)
        except Exception as e:
            # Обработка ошибки получения кода
            self.output(f"Шаг {self.step} - Не удалось получить код с GitHub: {str(e)}", 2)
            return False

        self.increase_step()

        # Переводим цифры с GitHub в символы в игре
        for index, digit in enumerate(content):
            xpath = f"//div[@class='css-k0i5go'][{digit}]"
            
            if self.move_and_click(xpath, 30, True, f"нажать на путь, соответствующий цифре {digit}", self.step, "кликабельно"):
                self.output(f"Шаг {self.step} - Нажат элемент, соответствующий цифре {digit}.", 2)
            else:
                # Обработка ошибки клика по элементу
                self.output(f"Шаг {self.step} - Элемент, соответствующий цифре {digit}, не найден или не кликабелен.", 1)

        self.increase_step()

        # Завершаем с проверкой ошибок
        invalid_puzzle_xpath = "//div[contains(text(), 'Неверный код головоломки')]/ancestor::div[contains(@class, 'chakra-alert')]"
        if self.move_and_click(invalid_puzzle_xpath, 30, True, "проверить наличие предупреждения", self.step, "видимый"):
            # Предупреждение о неверном коде головоломки присутствует
            self.output(f"Шаг {self.step} - Предупреждение о неверном коде головоломки присутствует.", 2)
        else:
            # Предупреждение о неверном коде головоломки отсутствует
            self.output(f"Шаг {self.step} - Предупреждение о неверном коде головоломки отсутствует.", 1)

        self.output(f"Шаг {self.step} - Последовательность ежедневной награды успешно завершена.", 2)
        return True

    def get_wait_time(self, before_after="pre-claim", timeout=10):
        """
        Считывает таймер вида '5ч 47м' из интерфейса и возвращает общее количество минут (int).
        Если элемент отсутствует или текст не соответствует формату, возвращает 0.
        """
        try:
            self.output(f"Шаг {self.step} - Получение времени ожидания ({before_after})...", 3)

            # безопасное преобразование timeout
            try:
                to = float(timeout)
            except Exception:
                to = 10.0  # разумное значение по умолчанию

            xpath = "//div[contains(@class,'css-lwfv40')]"
            wait_time_text = self.monitor_element(xpath, to, "таймер запроса")

            if not wait_time_text or isinstance(wait_time_text, bool):
                self.output(f"Шаг {self.step} - Элемент/текст времени ожидания не найден; предполагается 0м.", 3)
                return 0

            raw = str(wait_time_text).strip()
            self.output(f"Шаг {self.step} - Извлечён текст времени ожидания: '{raw}'", 3)

            # Принимаем '5ч 47м', '5ч', '47м', допускаем лишние пробелы/регистр
            m = re.fullmatch(r'\s*(?:(\d+)\s*ч)?\s*(?:(\d+)\s*м)?\s*', raw, flags=re.I)
            if not m:
                self.output(f"Шаг {self.step} - Шаблон времени ожидания не совпал с текстом: '{raw}'. Предполагается 0м.", 3)
                return 0

            hours = int(m.group(1) or 0)
            minutes = int(m.group(2) or 0)
            total_minutes = hours * 60 + minutes

            self.output(f"Шаг {self.step} - Общее время ожидания в минутах: {total_minutes}", 3)
            return total_minutes

        except Exception as e:
            self.output(f"Шаг {self.step} - Ошибка при разборе времени ожидания: {e}. Предполагается 0м.", 3)
            return 0

def main():
    claimer = SpellClaimer()
    claimer.run()

if __name__ == "__main__":
    main()