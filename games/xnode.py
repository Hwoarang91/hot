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

class XNodeClaimer(Claimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/xnode.py"
        self.prefix = "XNODE:"
        self.url = "https://web.telegram.org/k/#@xnode_bot"
        self.pot_full = "Заполнено"
        self.pot_filling = "заполняется"
        self.seed_phrase = None
        self.forceLocalProxy = False
        self.forceRequestUserAgent = False
        self.step = "01"
        self.imported_seedphrase = None
        self.start_app_xpath = "//div[contains(@class,'new-message-bot-commands-view')][contains(normalize-space(.),'Играть')]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='xNode: Core Protocol']]"

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
    
        xpath = "//button[normalize-space(text())='skip']"
        self.move_and_click(xpath, 10, True, "пропустить вступительные экраны (может отсутствовать)", self.step, "clickable")
        self.increase_step()
    
        xpath = "//button[normalize-space(text())='claim']"
        self.move_and_click(xpath, 10, True, "забрать ежедневную награду (может отсутствовать)", self.step, "clickable")
        self.increase_step()
    
        xpath = "//div[@data-title='XNode CPU']//canvas"
        self.move_and_click(xpath, 10, True, "нажать на чип (может отсутствовать)", self.step, "clickable")
        self.increase_step()
    
        xpath = "//button[normalize-space()='собрать']"
        self.move_and_click(xpath, 10, True, "собрать TFlops (может отсутствовать)", self.step, "clickable")
        self.increase_step()
    
        balance_xpath = "//span[normalize-space(.)='XPoints']/preceding-sibling::span[1]"
        self.get_balance(balance_xpath, False)
        self.increase_step()      
    
        # Получить время ожидания 
        wait_xpath = "//div[@class='TimeTracker']//span[contains(@class,'TimeTracker_text')]"
        action, minutes = self.decide_wait_or_claim(wait_xpath, label="до запроса", respect_force=True)
        
        # Затем запустить обновление
        self.get_profit_hour(False)
        skip = self.attempt_upgrade()        
        
        # Первое решение: ждать или запрашивать сейчас
        if action == "sleep":
            return minutes
         
        # Если обновление прошло, перезагрузить интерфейс.    
        if not skip:
            self.quit_driver()
            self.launch_iframe()
            self.get_profit_hour(True)
    
        # Продолжить (пере)запуск майнинга / последовательность запроса
        checkbox_wrap_xpath = ("//div[contains(@class,'AutoFarmChecker')]"
                               "//div[contains(@class,'CheckBox')]/div[contains(@class,'CheckBox_wrapper')]")
        
        if not self.is_autofarm_active():
            # полезно залогировать:
            self.output(f"Шаг {self.step} - AutoFarm выключен; включаем…", 2)
        
            def became_active():
                return self.is_autofarm_active()
        
            # используйте brute_click как запасной вариант; иначе работает move_and_click
            ok = self.brute_click(checkbox_wrap_xpath, timeout=5,
                                  action_description="переключить AutoFarm", state_check=became_active)
            if not ok and not self.is_autofarm_active():
                # ещё один прямой JS клик по центру, если нужно
                try:
                    el = self.driver.find_element(By.XPATH, checkbox_wrap_xpath)
                    self.driver.execute_script("""
                        const el = arguments[0];
                        const r = el.getBoundingClientRect();
                        const x = r.left + r.width/2, y = r.top + r.height/2;
                        for (const t of ['pointerdown','mousedown','pointerup','mouseup','click']) {
                          el.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,clientX:x,clientY:y}));
                        }
                    """, el)
                except Exception:
                    pass
        
            self.output(f"Шаг {self.step} - AutoFarm активен? {self.is_autofarm_active()}", 3)
        else:
            self.output(f"Шаг {self.step} - AutoFarm уже включен; клик не требуется.", 3)
    
        # Второе решение после клика
        action2, minutes2 = self.decide_wait_or_claim(wait_xpath, label="после перезапуска", respect_force=False)
        if action2 == "sleep":
            return minutes2
    
        # Если всё ещё не можем получить положительное время ожидания, безопаснее попробовать снова через час
        return 60
        
    def autofarm_checkbox_root(self):
        return self.driver.find_element(By.XPATH,
            "//div[contains(@class,'AutoFarmChecker')]//div[contains(@class,'CheckBox')]"
        )
    
    def is_autofarm_active(self):
        try:
            root = self.autofarm_checkbox_root()
            cls = " " + (root.get_attribute("class") or "") + " "
            return " active " in cls
        except Exception:
            return False
    
    def decide_wait_or_claim(self, wait_xpath, label="до запроса", respect_force=True):
        mins = self.get_wait_time(wait_xpath, timeout=12, label=label)
        self.increase_step()
    
        if mins is False:
            self.output(f"Шаг {self.step} - Время ожидания недоступно; по умолчанию 60 минут.", 2)
            return ("sleep", 60)
    
        remaining = float(mins)
    
        # Если осталось время, всегда ждать пока оно не истечёт +1 минута
        if remaining > 0 and not (respect_force and self.settings.get("forceClaim")):
            sleep_minutes = self.apply_random_offset(remaining + 1)
            self.output(
                f"СТАТУС: {label} ожидание {remaining:.1f} мин; "
                f"спим {sleep_minutes:.1f} мин (гарантируем +1 мин после таймера).",
                1
            )
            return ("sleep", sleep_minutes)
    
        # Таймер уже истёк → запрашиваем сейчас
        if respect_force:
            self.settings['forceClaim'] = True
        self.output(
            f"Шаг {self.step} - {label}: таймер уже истёк; продолжаем запрос.",
            3
        )
        return ("claim", 0)
            
    def get_wait_time(self, wait_time_xpath, timeout=12, label="таймер ожидания"):
        import re
    
        def _read_text():
            # Сначала пробуем монитор
            t = self.monitor_element(wait_time_xpath, timeout, label)
            if t and not isinstance(t, bool) and str(t).strip():
                return str(t)
            # Запасной вариант: textContent из DOM
            try:
                els = self.driver.find_elements(By.XPATH, wait_time_xpath)
                for el in els:
                    t = self.driver.execute_script("return arguments[0].textContent;", el)
                    if t and str(t).strip():
                        return str(t)
            except Exception:
                pass
            return ""
    
        try:
            self.output(f"Шаг {self.step} - Получаем время ожидания...", 3)
    
            raw = _read_text()
            if not raw:
                self.output(f"Шаг {self.step} - Текст времени ожидания не найден.", 3)
                return False

            # нормализуем
            text = " ".join(raw.split()).replace(",", ".")
            txt = text.lower()
            self.output(f"Шаг {self.step} - Извлечён текст времени ожидания: '{text}'", 3)

            total_minutes = 0.0
            found_any = False

            # A) форматы с токенами, например "7.8ч", "1ч 30м", "540с", "1д 2ч"
            for mult, pat in [
                (1440.0, r'(\d+(?:\.\d+)?)\s*d'),
                (  60.0, r'(\d+(?:\.\d+)?)\s*h'),
                (   1.0, r'(\d+(?:\.\d+)?)\s*m(?!s)'),
                (1/60.0, r'(\d+(?:\.\d+)?)\s*s\b'),
            ]:
                for m in re.findall(pat, txt, flags=re.I):
                    try:
                        total_minutes += float(m) * mult
                        found_any = True
                    except Exception:
                        pass

            # B) HH:MM[:SS] если токены не найдены
            if not found_any:
                m = re.search(r'\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b', txt)
                if m:
                    h  = int(m.group(1) or 0)
                    mn = int(m.group(2) or 0)
                    s  = int(m.group(3) or 0)
                    total_minutes = h * 60 + mn + s / 60.0
                    found_any = True

            # ✅ принимаем ноль минут как валидное значение
            if found_any:
                total_minutes = max(0.0, round(total_minutes, 1))
                self.output(f"Шаг {self.step} - Общее время ожидания в минутах: {total_minutes}", 3)
                return total_minutes

            self.output(f"Шаг {self.step} - Шаблон времени ожидания не совпал с текстом: '{text}'", 3)
            return False
    
        except Exception as e:
            self.output(f"Шаг {self.step} - Ошибка в get_wait_time: {type(e).__name__}: {e}", 3)
            return False
            
    def get_profit_hour(self, claimed=False):
        prefix = "После" if claimed else "До"
        default_priority = 2 if claimed else 3
        priority = max(self.settings['verboseLevel'], default_priority)

        profit_xpath = "//div[contains(@class,'ItemGrout_subChildren')]//span[contains(text(),'/sec')]"

        try:
            text = self.monitor_element(profit_xpath, 15, "прибыль в секунду")
            if not text or isinstance(text, bool):
                self.output(f"Шаг {self.step} - Не удалось найти текст прибыли.", priority)
                return False

            raw = text.strip()
            self.output(f"Шаг {self.step} - {prefix} строка ПРИБЫЛИ: '{raw}'", priority)
            return raw

        except NoSuchElementException:
            self.output(f"Шаг {self.step} - Элемент прибыли не найден.", priority)
            return False
        except Exception as e:
            self.output(f"Шаг {self.step} - Ошибка в get_profit_hour: {e}", priority)
            return False
        finally:
            self.increase_step()
            
    def attempt_upgrade(self):
        # пропустить, если это не версия с автообновлением
        return True

def main():
    claimer = XNodeClaimer()
    claimer.run()

if __name__ == "__main__":
    main()