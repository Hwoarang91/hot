import os
import re
import subprocess
import sys
import time

# Попытка импортировать httpx, установка при необходимости
try:
    import httpx
except ImportError:
    print("httpx не установлен. Выполняется установка...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])
        import httpx
    except Exception as e:
        print(f"Не удалось установить httpx: {e}")
        sys.exit(1)

PROXY_DIR = os.path.abspath("./proxy")
START_SCRIPT_PATH = os.path.join(PROXY_DIR, 'start_mitmproxy.sh')
PROXY_LOCK_FILE = "./start_proxy.txt"
PM2_PROCESS_NAME = "http-proxy"

def read_start_script():
    if not os.path.exists(START_SCRIPT_PATH):
        print(f"{START_SCRIPT_PATH} не существует.")
        return None

    with open(START_SCRIPT_PATH, 'r') as file:
        return file.read()

def check_upstream_proxy(script_content):
    proxy_pattern = re.compile(
        r'--mode upstream:(http[s]?)://(.*?):(\d+)(?:\s+--upstream-auth\s+(\S+):(\S+))?',
        re.DOTALL
    )
    match = proxy_pattern.search(script_content)
    if match:
        scheme, host, port, username, password = match.groups()
        return {
            "scheme": scheme,
            "host": host,
            "port": port,
            "username": username,
            "password": password
        }
    return None

def prompt_user_for_proxy_details():
    host = input("Введите хост upstream прокси (IP или URL): ").strip()
    port = input("Введите порт upstream прокси: ").strip()
    username = input("Введите имя пользователя upstream прокси (оставьте пустым, если не требуется): ").strip()
    password = input("Введите пароль upstream прокси (оставьте пустым, если не требуется): ").strip()

    if not (host and port):
        print("Требуется указать хост и порт.")
        return None

    return host, port, username or None, password or None

def prompt_insecure_credential_validation():
    allow_insecure = input("Разрешить небезопасную проверку учетных данных VPN (y/N): ").strip().lower()
    if allow_insecure == 'y':
        confirm = input("Это позволит другим видеть ваши учетные данные и должно использоваться только в крайнем случае - продолжить (y/N): ").strip().lower()
        return confirm == 'y'
    return False

def test_proxy_connection(host, port, username, password, use_https):
    scheme = "https" if use_https else "http"
    if username and password:
        proxy_url = f"{scheme}://{username}:{password}@{host}:{port}"
    else:
        proxy_url = f"{scheme}://{host}:{port}"
    test_url = 'https://web.telegram.org'
    test_proxy_anonymity(proxy_url)
    expected_word_count = 3
    print(f"Проверка учетных данных прокси с использованием {scheme.upper()}...")

    proxies = {
        'http://': proxy_url,
        'https://': proxy_url,
    }

    try:
        with httpx.Client(proxies=proxies, timeout=10) as client:
            result = client.get(test_url, follow_redirects=False)
            if result.status_code == 200:
                telegram_count = result.text.count("Telegram")
                if telegram_count > expected_word_count:
                    print("Подключение к прокси успешно.")
                    print(f"Ответ: 200, количество слов 'Telegram': {telegram_count}")
                    return True
                else:
                    print(f"Подключение к прокси не удалось: неожиданный контент. Количество 'Telegram' равно {telegram_count}.")
                    return False
            else:
                print(f"Подключение к прокси не удалось с кодом статуса: {result.status_code}")
                return False
    except httpx.RequestError as e:
        print(f"Подключение к прокси не удалось: {e}")
        return False

def update_start_script(host, port, username, password, use_https):
    scheme = "https" if use_https else "http"
    upstream_auth = f" --upstream-auth {username}:{password}" if username and password else ""
    start_script_content = f"""#!/bin/bash
./venv/bin/mitmdump --mode upstream:{scheme}://{host}:{port}{upstream_auth} -s {os.path.join(PROXY_DIR, 'modify_requests_responses.py')} > /dev/null 2>&1
"""
    with open(START_SCRIPT_PATH, 'w') as file:
        file.write(start_script_content)
    os.chmod(START_SCRIPT_PATH, 0o755)

def stop_and_delete_pm2_process():
    try:
        subprocess.run(['pm2', 'stop', PM2_PROCESS_NAME], check=True)
        subprocess.run(['pm2', 'delete', PM2_PROCESS_NAME], check=True)
        subprocess.run(['pm2', 'save'], check=True)  # Сохранить состояние PM2 после удаления процесса
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при остановке/удалении процесса PM2: {e}")

def lock_file():
    with open(PROXY_LOCK_FILE, "w") as lock_file:
        lock_file.write(f"Настройка прокси в процессе: {time.ctime()}\n")

def unlock_file():
    if os.path.exists(PROXY_LOCK_FILE):
        os.remove(PROXY_LOCK_FILE)

def restart_proxy():
    try:
        subprocess.run(['pm2', 'start', START_SCRIPT_PATH, '--name', PM2_PROCESS_NAME], check=True)
        subprocess.run(['pm2', 'save'], check=True)
        print("http-proxy успешно перезапущен.")
    except subprocess.CalledProcessError as e:
        print(f"Не удалось перезапустить http-proxy: {e}")

def test_proxy_anonymity(proxy_url):
    test_url = 'https://httpbin.org/get'
    try:
        # Сначала получить реальный IP клиента, сделав прямой запрос
        real_ip = None
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(test_url)
                data = response.json()
                real_ip = data.get('origin', '')
        except Exception as e:
            print(f"Не удалось получить реальный IP-адрес: {e}")
            return None

        # Теперь сделать запрос через прокси
        proxies = {
            'http://': proxy_url,
            'https://': proxy_url,
        }
        with httpx.Client(proxies=proxies, timeout=10) as client:
            response = client.get(test_url)
            data = response.json()
            headers = data.get('headers', {})
            origin = data.get('origin', '')

            # Проверка анонимности
            if origin == real_ip:
                print("Прокси является прозрачным (NOA)")
                print("Объяснение: Прокси передает ваш реальный IP-адрес серверу. Ваш IP раскрыт.")
                return 'NOA'
            elif 'X-Forwarded-For' in headers or 'Via' in headers:
                print("Прокси является анонимным (ANM)")
                print("Объяснение: Прокси скрывает ваш IP-адрес, но раскрывает факт использования прокси.")
                return 'ANM'
            else:
                print("Прокси является элитным (HIA)")
                print("Объяснение: Прокси скрывает ваш IP-адрес и не раскрывает использование прокси.")
                return 'HIA'
    except Exception as e:
        print(f"Не удалось проверить анонимность прокси: {e}")
        return None

def main():
    script_content = read_start_script()
    if script_content is None:
        return

    print("Вы можете получить бесплатный аккаунт с ограниченным трафиком на https://www.webshare.io/?referral_code=yat0oxfcqbpd")

    upstream_proxy = check_upstream_proxy(script_content)
    if upstream_proxy:
        print("Текущая конфигурация upstream прокси:")
        print(f"Схема: {upstream_proxy['scheme']}")
        print(f"Хост: {upstream_proxy['host']}")
        print(f"Порт: {upstream_proxy['port']}")
        print(f"Имя пользователя: {upstream_proxy['username']}")
        print(f"Пароль: {upstream_proxy['password']}")
    else:
        print("Конфигурация upstream прокси в данный момент не установлена.")

    if upstream_proxy:
        choice = input("Upstream прокси уже настроен. Введите 'y' для удаления или нажмите Enter для ввода новых данных: ").strip().lower()
        if choice == 'y':
            lock_file()
            stop_and_delete_pm2_process()
            update_start_script("", "", "", "", True)  # Удалить конфигурацию upstream
            subprocess.run(['pm2', 'save'], check=True)  # Сохранить состояние PM2 после удаления конфигурации
            unlock_file()
            print("Upstream прокси удален.")
            return

    while True:
        proxy_details = prompt_user_for_proxy_details()
        if proxy_details:
            host, port, username, password = proxy_details
            use_https = not prompt_insecure_credential_validation()
            if test_proxy_connection(host, port, username, password, use_https):
                lock_file()
                stop_and_delete_pm2_process()
                update_start_script(host, port, username, password, use_https)
                restart_proxy()
                unlock_file()
                break
            else:
                print("Проверка прокси не удалась. Пожалуйста, введите данные прокси заново.")
        else:
            print("Неверный ввод. Пожалуйста, предоставьте все необходимые данные.")

if __name__ == "__main__":
    main()