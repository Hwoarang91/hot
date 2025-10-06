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

from xnode import XNodeClaimer

# ---------- константы уровня модуля ----------
MAX_ROI_DAYS = 31
MAX_ROI_SEC  = MAX_ROI_DAYS * 24 * 3600

UNIT = {"K":1e3, "M":1e6, "B":1e9, "T":1e12, "P":1e15}
# -------------------------------------------

class XNodeAUClaimer(XNodeClaimer):

    def initialize_settings(self):
        super().initialize_settings()
        self.script = "games/xnode-auto.py"
        self.prefix = "XNODE-Auto:"

    def __init__(self):
        super().__init__()
        self.start_app_xpath = "//div[contains(@class,'new-message-bot-commands-view')][contains(normalize-space(.),'Play')]"
        self.start_app_menu_item = "//a[.//span[contains(@class, 'peer-title') and normalize-space(text())='xNode: Core Protocol']]"
        
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

    def attempt_upgrade(self):
        self.output(f"Шаг {self.step} - Подготовка к запуску скрипта обновления - это может занять некоторое время.", 2)
        clicked = self.upgrade_all(max_passes=3, per_row_wait=6)
        if clicked > 0:
            return False
        return True
        
    def upgrade_all(self, max_passes=2, per_row_wait=4):
        """Предпочтительно обновлять по наименьшему ROI или (опционально) по наименьшему ETA = время_до_доступности + ROI.
           Добавляет отладку по каждой строке: стоимость, прибыль, ROI, время_до_доступности (если отключено), ETA.
        """
    
        # ---------- Настройки для "квантового" планирования ----------
        USE_ETA_PLANNING = True           # установить False для чистого поведения с приоритетом ROI
        ETA_DECISION_MARGIN_SEC = 0       # требовать, чтобы отключённый лучший ETA опережал лучший доступный ROI на это время для "ожидания"
        # ---------------------------------------------------
    
        # --- маленькие вспомогательные функции, локальные для этого метода ---
    
        def class_has_token(el, token: str) -> bool:
            try:
                cls = (el.get_attribute("class") or "")
                return f" {token} " in f" {cls.strip()} "
            except StaleElementReferenceException:
                return True
    
        def aria_disabled(el) -> bool:
            try:
                v = (el.get_attribute("aria-disabled") or "").strip().lower()
                return v in ("1", "true", "yes")
            except StaleElementReferenceException:
                return True
    
        def style_blocks_click(el) -> bool:
            try:
                style = (el.get_attribute("style") or "").lower()
                if "pointer-events" in style and "none" in style:
                    return True
                m = re.search(r"opacity\s*:\s*([0-9.]+)", style)
                if m:
                    try:
                        return float(m.group(1)) < 0.5
                    except Exception:
                        return False
                return False
            except StaleElementReferenceException:
                return True
    
        def find_one(root, rel_xpaths):
            for xp in rel_xpaths:
                try:
                    el = root.find_element(By.XPATH, xp)
                    if el:
                        return el
                except NoSuchElementException:
                    continue
                except StaleElementReferenceException:
                    return None
            return None
            
        def _in_game_dom(self) -> bool:
            try:
                # дешёвые, надёжные проверки DOM xNode
                if self.driver.find_elements(By.XPATH, "//div[contains(@class,'Upgrader')]"):
                    return True
                if self.driver.find_elements(By.XPATH, "//div[contains(@class,'UpgradesPage')]"):
                    return True
                return False
            except Exception:
                return False
    
        def get_title(row):
            try:
                t = row.find_element(By.XPATH, ".//h2[contains(@class,'Upgrader_text-title')]")
                txt = (t.text or "").strip()
                if not txt:
                    txt = (self.driver.execute_script("return arguments[0].textContent;", t) or "").strip()
                return txt
            except Exception:
                return ""
    
        def get_level_num(row):
            try:
                lvl_el = row.find_element(By.XPATH, ".//h3[contains(@class,'Upgrader_text-lvl')]")
                txt = (lvl_el.text or "").strip()
                if not txt:
                    txt = (self.driver.execute_script("return arguments[0].textContent;", lvl_el) or "").strip()
                m = re.search(r"(\d+)", txt)
                return int(m.group(1)) if m else None
            except Exception:
                return None
    
        def find_row_by_title_exact(title):
            try:
                # Безопасный литерал для XPath
                if "'" in title and '"' in title:
                    parts = title.split("'")
                    xp_lit = "concat(" + ", \"'\", ".join([f"'{p}'" for p in parts]) + ")"
                elif "'" in title:
                    xp_lit = f'"{title}"'
                else:
                    xp_lit = f"'{title}'"
                xp = ("//div[contains(@class,'Upgrader')]"
                      f"[.//h2[contains(@class,'Upgrader_text-title') и normalize-space()={xp_lit}]]")
                return self.driver.find_element(By.XPATH, xp)
            except Exception:
                return None
    
        def row_is_effectively_disabled(row) -> bool:
            if class_has_token(row, "disable") or aria_disabled(row) or style_blocks_click(row):
                return True
            ctrl = find_one(row, [
                ".//div[contains(@class,'Upgrader_right-wrap')]",
                ".//div[contains(@class,'Upgrader_right')]",
                ".//div[contains(@class,'Upgrader_right-price_text')]",
            ])
            if ctrl is None:
                return True
            return class_has_token(ctrl, "disable") or aria_disabled(ctrl) or style_blocks_click(ctrl)
    
        def click_ctrl(ctrl, why=""):
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", ctrl)
                ActionChains(self.driver).move_to_element(ctrl).pause(0.05).click(ctrl).perform()
                return True
            except Exception:
                try:
                    self.driver.execute_script("arguments[0].click();", ctrl)
                    return True
                except Exception:
                    return False
    
        def _norm(s: str) -> str:
            return (s or "").replace("\xa0", " ").strip()
    
        # --- 0) Войти в iframe только если мы ещё не в игре ---
        if not self._in_game_dom():
            self.output(f"Шаг {self.step} - Не в DOM игры; пытаемся войти в iframe…", 3)
            try:
                self.launch_iframe()
            except Exception as e:
                self.output(f"Шаг {self.step} - launch_iframe() завершился с ошибкой: {e}", 2)
    
        # --- 1) Ждать и собрать строки (с допусками) ---
    
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'UpgradesPage-items')]"
                " | //div[contains(@class,'Upgrader') и .//h2[contains(@class,'Upgrader_text-title')]]"
            ))
        )
    
        all_containers = self.driver.find_elements(By.XPATH, "//div[contains(@class,'UpgradesPage-items')]")
        containers = [c for c in all_containers if getattr(c, 'is_displayed', lambda: True)()]
        if not containers:
            containers = all_containers[:]
        if not containers:
            containers = [self.driver]  # искать по всему документу
    
        try:
            self.driver.execute_script("window.scrollTo(0, 0);")
        except Exception:
            pass
        for cont in containers:
            try:
                self.driver.execute_script("if (arguments[0].scrollTop !== undefined) arguments[0].scrollTop = 0;", cont)
            except Exception:
                pass
    
        row_xpath_core = (
            ".//div[contains(@class,'Upgrader') и "
            " .//h2[contains(@class,'Upgrader_text-title')] и "
            " .//div[contains(@class,'Upgrader_right-price_text')] ]"
        )
        row_xpath_fallback = (
            ".//div[contains(@class,'Upgrader') и "
            " .//h2[contains(@class,'Upgrader_text-title')] ]"
        )
    
        rows = []
        for cont in containers:
            try:
                rows.extend(cont.find_elements(By.XPATH, row_xpath_core))
            except Exception:
                pass
        if not rows:
            for cont in containers:
                try:
                    rows.extend(cont.find_elements(By.XPATH, row_xpath_fallback))
                except Exception:
                    pass
    
        snapshot = rows
    
        self.output(
            f"Шаг {self.step} - контейнеры(всего/видимых): {len(all_containers)}/{sum(1 for c in all_containers if getattr(c,'is_displayed',lambda:True)())} | строк: {len(snapshot)}",
            3
        )
    
        if not snapshot:
            self.output(f"Шаг {self.step} - В документе не найдено строк Upgrader (после допусков).", 2)
            return 0
    
        # --- 1a) Получить текущий баланс и прибыль в секунду (для времени_до_доступности) ---
    
        def _parse_profit_per_sec():
            # Предпочитать кеш, если сохранён во время "Шага 114".
            try:
                if getattr(self, "profit_per_sec", None):
                    return float(self.profit_per_sec)
            except Exception:
                pass
            # Попытаться прочитать из известного элемента прибыли (адаптируйте селекторы под ваш UI):
            try:
                el = self.driver.find_element(By.XPATH, "//*[contains(text(),'SEC') или contains(text(),'/SEC')]")
                raw = _norm(el.text or self.driver.execute_script("return arguments[0].textContent;", el) or "")
                # например "+1.4M/SEC" -> "1.4M"
                m = re.search(r'([+-]?\d+(?:\.\d+)?\s*[KMBTP]?)\s*/\s*SEC', raw, re.I)
                if m:
                    return self._parse_qty(m.group(1))
            except Exception:
                pass
            return 0.0
    
        def _parse_current_balance():
            # Адаптируйте под ваш элемент баланса, если доступен; иначе 0.
            try:
                el = self.driver.find_element(By.XPATH, "//*[contains(@class,'balance') или contains(text(),'tflops')]")
                raw = _norm(el.text or self.driver.execute_script("return arguments[0].textContent;", el) or "")
                # Попытаться взять первое большое число с размерностью
                m = re.search(r'([+-]?\d+(?:\.\d+)?\s*[KMBTP]?)\s*(?:tflops|TFLOPS)?', raw, re.I)
                if m:
                    return self._parse_qty(m.group(1))
            except Exception:
                pass
            return 0.0
    
        profit_per_sec = _parse_profit_per_sec()
        current_balance = _parse_current_balance()
    
        # --- 2) Сканировать строки → метрики, убрать дубликаты, ROI, время_до_доступности, ETA ---
    
        seen = set()
        all_rows_metrics = []
        actionable_now = []     # доступные и в пределах лимита ROI
        disabled_considered = []  # отключённые, но считаем время_до_доступности и ETA
        import math
    
        for row in snapshot:
            try:
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center', inline:'nearest'});", row
                    )
                except Exception:
                    pass
    
                title = _norm(get_title(row))
                if not title:
                    all_rows_metrics.append({
                        "title": "", "level": None, "disabled": True,
                        "cost": 0.0, "gain": 0.0, "roi_sec": float("inf"),
                        "parse_ok": False, "skip_reason": "нет заголовка"
                    })
                    continue
    
                lvl = get_level_num(row)
                disabled = row_is_effectively_disabled(row)
    
                try:
                    price_box = row.find_element(By.XPATH, ".//div[contains(@class,'Upgrader_right-price_text')]")
                    price_raw = _norm(price_box.text or self.driver.execute_script(
                        "return arguments[0].textContent;", price_box) or "")
                except Exception:
                    price_raw = ""
    
                key = (title, lvl, price_raw)
                if key in seen:
                    all_rows_metrics.append({
                        "title": title, "level": lvl, "disabled": True,
                        "cost": 0.0, "gain": 0.0, "roi_sec": float("inf"),
                        "parse_ok": False, "skip_reason": "дубликат"
                    })
                    continue
                seen.add(key)
    
                # парсим стоимость/прибыль
                try:
                    cost, gain = self._extract_cost_and_gain(row)
                    cost = float(cost or 0.0)
                    gain = float(gain or 0.0)
                    if cost <= 0:
                        raise ValueError("стоимость<=0")
                    if gain <= 0:
                        raise ValueError("прибыль<=0")
                    roi_sec = self._roi_seconds(cost, gain)
                    parse_ok = True
                    reason = ""
                except Exception as e:
                    cost = cost if 'cost' in locals() else 0.0
                    gain = gain if 'gain' in locals() else 0.0
                    roi_sec = float("inf")
                    parse_ok = False
                    reason = f"не удалось распарсить: {type(e).__name__}"
    
                # время до доступности и ETA
                if disabled:
                    # если отключено, считаем, что недостаточно баланса для стоимости
                    deficit = max(cost - current_balance, 0.0)
                    tta = (deficit / profit_per_sec) if profit_per_sec > 0 else float("inf")
                else:
                    # уже доступно: ждать не нужно
                    tta = 0.0
                eta_sec = (tta + roi_sec) if (parse_ok and math.isfinite(roi_sec)) else float("inf")
    
                m = {
                    "title": title,
                    "level": lvl,
                    "disabled": disabled,
                    "cost": cost,
                    "gain": gain,
                    "roi_sec": roi_sec,
                    "time_to_afford": tta,
                    "eta_sec": eta_sec,
                    "parse_ok": parse_ok,
                    "skip_reason": reason
                }
    
                # фильтруем по исходному лимиту ROI для "доступных сейчас"
                if disabled:
                    m["skip_reason"] = m["skip_reason"] or "отключено"
                    disabled_considered.append(m)
                elif not parse_ok:
                    pass
                elif roi_sec > MAX_ROI_SEC:
                    m["skip_reason"] = f"roi>{MAX_ROI_DAYS}д"
                    all_rows_metrics.append(m)
                else:
                    actionable_now.append(m)
                    all_rows_metrics.append(m)
                    continue
    
                all_rows_metrics.append(m)
    
            except Exception as e:
                all_rows_metrics.append({
                    "title": _norm(locals().get("title", "")),
                    "level": locals().get("lvl", None),
                    "disabled": locals().get("disabled", None),
                    "cost": 0.0,
                    "gain": 0.0,
                    "roi_sec": float("inf"),
                    "time_to_afford": float("inf"),
                    "eta_sec": float("inf"),
                    "parse_ok": False,
                    "skip_reason": f"ошибка в цикле: {type(e).__name__}"
                })
                continue
    
        # --- 3) Отладочный вывод и сортировка ---
    
        def _hrs(x):
            return (x / 3600.0) if math.isfinite(x) else float("inf")
    
        # Сортируем доступные по ROI в первую очередь (текущее поведение)
        actionable_now.sort(key=lambda m: (m["roi_sec"], m["cost"], -m["gain"], m["title"] or ""))
    
        # Сортируем отключённые по ETA в первую очередь (самая быстрая выгода)
        disabled_considered.sort(key=lambda m: (m["eta_sec"], m["cost"], -m["gain"], m["title"] or ""))
    
        # Выводим метрики (теперь с TTA и ETA)
        for m in all_rows_metrics:
            roi = m.get("roi_sec", float("inf"))
            tta = m.get("time_to_afford", float("inf"))
            eta = m.get("eta_sec", float("inf"))
            flags = []
            if not m.get("parse_ok", True):
                flags.append(m.get("skip_reason") or "не удалось распарсить")
            if m.get("disabled"):
                flags.append("отключено")
            if math.isfinite(roi) and roi > MAX_ROI_SEC:
                flags.append(f"roi>{MAX_ROI_DAYS}д")
            sr = m.get("skip_reason")
            if sr and sr not in flags:
                flags.append(sr)
            flag_txt = f" [{', '.join(flags)}]" if flags else ""
    
            self.output(
                f"Шаг {self.step} - Проверка ROI: {m.get('title') or 'Неизвестно'} (Уровень {m.get('level')}) → "
                f"Δ/сек={m.get('gain',0.0):.3g}, Стоимость={m.get('cost',0.0):.3g}, "
                f"ROI≈{_hrs(roi):.2f}ч, TTA≈{_hrs(tta):.2f}ч, ETA≈{_hrs(eta):.2f}ч{flag_txt}",
                3
            )
    
        # --- 4) Решение: покупать сейчас (с приоритетом ROI) или ждать (с приоритетом ETA)? ---
    
        if not actionable_now and not disabled_considered:
            self.output(f"Шаг {self.step} - Нет доступных или рассмотренных строк.", 2)
            return 0
    
        buy_now = True
        chosen_title = None
    
        if USE_ETA_PLANNING:
            best_disabled = disabled_considered[0] if disabled_considered else None
            best_aff_now = actionable_now[0] if actionable_now else None
    
            if best_disabled and best_aff_now:
                # Сравниваем ETA отключённых и доступный чистый ROI
                if best_disabled["eta_sec"] + ETA_DECISION_MARGIN_SEC < best_aff_now["roi_sec"]:
                    buy_now = False
                    chosen_title = best_disabled["title"]
            elif best_disabled and not best_aff_now:
                buy_now = False
                chosen_title = best_disabled["title"]
            else:
                buy_now = True
                chosen_title = best_aff_now["title"] if best_aff_now else None
        else:
            buy_now = True
            chosen_title = actionable_now[0]["title"] if actionable_now else None
    
        if not buy_now:
            # Мы ждём — чётко логируем причину.
            bd = disabled_considered[0]
            self.output(
                f"Шаг {self.step} - Стратегия: ЖДАТЬ. Лучший отключённый '{bd['title']}' ETA≈{_hrs(bd['eta_sec']):.2f}ч "
                f"лучше лучшего доступного ROI≈{_hrs(actionable_now[0]['roi_sec']) if actionable_now else float('inf'):.2f}ч.",
                2
            )
            return 0
    
        # Если мы здесь, то будем покупать в порядке лучшего сначала (список доступных)
        ranked = []
        for m in actionable_now:
            lvl_key = m["level"] if isinstance(m["level"], int) else 10**9
            ranked.append((m["roi_sec"], m["cost"], lvl_key, m["title"]))
        ranked.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    
        # целевые области клика (упорядоченные варианты)
        targets = [
            ".//div[contains(@class,'Upgrader_right-wrap')]",
            ".//div[contains(@class,'Upgrader_right-price_text')]",
            ".//div[contains(@class,'Upgrader_right')]",
            ".//button",
            ".//*[self::div или self::span][contains(@class,'price') или contains(text(),'tflops')]",
        ]
    
        effective_clicks = 0
    
        def _get_level_by_title(ttl):
            r = find_row_by_title_exact(ttl)
            return get_level_num(r) if r else None
    
        for p in range(max_passes):
            acted = False
            for _, _, _, title in ranked:
                try:
                    row = find_row_by_title_exact(title)
                    if not row:
                        continue
                    if row_is_effectively_disabled(row):
                        continue
    
                    ctrl = find_one(row, targets)
                    if not ctrl:
                        continue
    
                    lvl_before = get_level_num(row)
                    if not click_ctrl(ctrl, why="клик обновления (1)"):
                        continue
    
                    acted = True
                    time.sleep(0.3)
    
                    row_fresh = find_row_by_title_exact(title) or row
                    lvl_after = get_level_num(row_fresh)
                    became_disabled = row_is_effectively_disabled(row_fresh)
    
                    success = False
                    if (lvl_after is None or lvl_before is None or lvl_after == lvl_before) and not became_disabled:
                        ctrl2 = find_one(row_fresh, targets) or find_one(row, targets)
                        if ctrl2 and click_ctrl(ctrl2, why="клик обновления (2)"):
                            time.sleep(0.3)
                            row_fresh2 = find_row_by_title_exact(title) or row_fresh
                            lvl_after2 = get_level_num(row_fresh2)
                            became_disabled = row_is_effectively_disabled(row_fresh2)
                            success = ((lvl_after2 is not None and lvl_before is not None and lvl_after2 > lvl_before)
                                       or became_disabled)
                            if success:
                                lvl_after = lvl_after2
                    else:
                        success = True
    
                    if success:
                        effective_clicks += 1
                        lvl_print = (
                            f"{(lvl_before or 0) + 1}" if (lvl_after is None and isinstance(lvl_before, int))
                            else (f"{lvl_after}" if isinstance(lvl_after, int)
                                  else (f"{lvl_before}" if isinstance(lvl_before, int) else "?"))
                        )
                        self.output(f"Шаг {self.step} - Обновлено {title} до уровня {lvl_print}", 3)
    
                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    self.output(f"Шаг {self.step} - Ошибка в строке обновления ({title}): {e}", 3)
                    continue
    
            if not acted:
                break
            if per_row_wait:
                time.sleep(0.2)
    
        self.output(f"Шаг {self.step} - Цикл обновления завершён. Эффективных обновлений: {effective_clicks}", 2)
        return effective_clicks
        
    # --- вспомогательные функции (фиксированные) ---  
    def _parse_qty(self, text: str) -> float:
        """
        Принимает: "400.6M", "1.2B", "+260", "897.2M tflops" и т.п.
        Возвращает базовые единицы (float).
        """
        if text is None:
            return 0.0
        t = str(text).replace("\xa0", " ").strip()  # нормализуем NBSP -> пробел
    
        # Находим первое число с опциональным *однобуквенным* суффиксом величины сразу после него.
        # Примеры: "1.2B", "400.6M", "+260", "897.2M tflops"
        m = re.search(r'([+-]?\d+(?:\.\d+)?)([KMBTP])?\b', t, re.IGNORECASE)
        if not m:
            return 0.0
    
        num = float(m.group(1))
        suf = (m.group(2) or "").upper()
        if suf in UNIT:
            return num * UNIT[suf]
        return num
    
    def _extract_cost_and_gain(self, row):
        # ----- СТОИМОСТЬ -----
        price_el = row.find_element(By.XPATH, ".//div[contains(@class,'Upgrader_right-price_text')]")
        price_txt = (price_el.text or "").strip()
        if not price_txt:
            price_txt = (self.driver.execute_script("return arguments[0].textContent;", price_el) or "").strip()
        # полезная отладка
        self.output(f"Шаг {self.step} - исходный текст стоимости: '{price_txt}'", 3)
        cost = self._parse_qty(price_txt)
    
        # ----- ПРИБЫЛЬ (дельта дохода в секунду) -----
        gain_el = row.find_element(By.XPATH, ".//div[contains(@class,'Upgrader_income')]/span[2]")
        gain_txt = (gain_el.text or "").strip()
        if not gain_txt:
            gain_txt = (self.driver.execute_script("return arguments[0].textContent;", gain_el) or "").strip()
        self.output(f"Шаг {self.step} - исходный текст прибыли: '{gain_txt}'", 3)
        gain = self._parse_qty(gain_txt)
    
        return cost, gain
    
    def _roi_seconds(self, cost, gain):
        if not gain or gain <= 0:
            return float("inf")
        return cost / gain

def main():
    claimer = XNodeAUClaimer()
    claimer.run()

if __name__ == "__main__":

    main()