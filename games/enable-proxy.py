import os
import subprocess
import shutil
import time

PROXY_DIR = os.path.abspath("./proxy")

log_to_file = False  # Установите в False для записи логов в /dev/null

def get_log_file_path():
    return os.path.join(PROXY_DIR, 'mitmproxy.log') if log_to_file else '/dev/null'

def check_pm2_process_exists(process_name):
    try:
        result = subprocess.run(['pm2', 'list'], capture_output=True, text=True)
        return process_name in result.stdout
    except Exception as e:
        print(f"Произошла ошибка при проверке процесса PM2: {e}")
        return False

def install_wheel_if_missing():
    try:
        __import__('wheel')
    except ImportError:
        print("Устанавливается отсутствующий пакет wheel...")
        subprocess.run(['pip3', 'install', 'wheel'], check=True)

def install_mitmproxy():
    subprocess.run(['pip3', 'install', 'mitmproxy'], check=True)

def copy_certificates():
    mitmproxy_cert_path = os.path.expanduser('~/.mitmproxy/mitmproxy-ca-cert.pem')
    if os.path.exists(mitmproxy_cert_path):
        sudo_password = os.getenv('SUDO_PASSWORD')
        if shutil.which('sudo'):
            command1 = f'echo {sudo_password} | sudo -S cp {mitmproxy_cert_path} /usr/local/share/ca-certificates/mitmproxy-ca-cert.crt'
            command2 = f'echo {sudo_password} | sudo -S update-ca-certificates'
        else:
            command1 = f'cp {mitmproxy_cert_path} /usr/local/share/ca-certificates/mitmproxy-ca-cert.crt'
            command2 = 'update-ca-certificates'
        subprocess.run(command1, shell=True, check=True)
        subprocess.run(command2, shell=True, check=True)
    else:
        print(f"Сертификат не найден по пути {mitmproxy_cert_path}")

def write_modify_requests_responses_script():
    script_content = """
from mitmproxy import http, ctx
import re
import zlib
import brotli

def load(l):
    ctx.log.info("Скрипт modify_requests_responses.py запущен.")

# Изменение исходящих запросов (клиент -> сервер)
def request(flow: http.HTTPFlow) -> None:
    try:
        if flow.request:
            # Заменить 'tgWebAppPlatform=web' на 'tgWebAppPlatform=ios' во всех URL
            if "tgWebAppPlatform=web" in flow.request.url:
                ctx.log.info(f"Изменение исходящего URL: {flow.request.url}")
                flow.request.url = flow.request.url.replace("tgWebAppPlatform=web", "tgWebAppPlatform=ios")
                ctx.log.info(f"Исходящий URL изменён на: {flow.request.url}")
                
            # Определение платформы по User-Agent и перенаправление 'telegram-web-app.js'
            user_agent = flow.request.headers.get('User-Agent', '')
            if 'telegram-web-app.js' in flow.request.pretty_url:
                if any(keyword in user_agent for keyword in ['iPhone', 'iPad', 'iOS', 'iPhone OS']):
                    # Перенаправление для iOS
                    flow.request.path = flow.request.path.replace('telegram-web-app.js', 'games/utils/ios-60-telegram-web-app.js')
                    ctx.log.info("Перенаправлено на JavaScript для iOS.")
                elif 'Android' in user_agent:
                    # Перенаправление для Android
                    flow.request.path = flow.request.path.replace('telegram-web-app.js', 'games/utils/android-60-telegram-web-app.js')
                    ctx.log.info("Перенаправлено на JavaScript для Android.")
    except Exception as e:
        ctx.log.error(f"Ошибка при изменении исходящего запроса для URL {flow.request.url}: {e}")

# Изменение входящих ответов (сервер -> клиент)
def response(flow: http.HTTPFlow) -> None:
    try:
        # Удаление определённых заголовков
        headers_to_remove = ['Content-Security-Policy', 'X-Frame-Options']
        removed_headers = []
        for header in headers_to_remove:
            if header in flow.response.headers:
                del flow.response.headers[header]
                removed_headers.append(header)

        if removed_headers:
            ctx.log.info(f"Удалены заголовки из ответа для URL: {flow.request.url}")
            ctx.log.debug(f"Удалённые заголовки: {removed_headers}")

        # Изменение содержимого при необходимости
        content_type = flow.response.headers.get("content-type", "").lower()
        content_encoding = flow.response.headers.get("content-encoding", "").lower()

        # Проверка типа содержимого: HTML, JavaScript или JSON
        if any(ct in content_type for ct in ["text/html", "application/javascript", "application/json", "text/javascript"]):
            # Распаковка, если содержимое сжато
            if "gzip" in content_encoding:
                decoded_content = zlib.decompress(flow.response.content, zlib.MAX_WBITS | 16).decode('utf-8', errors='replace')
                compressed = 'gzip'
            elif "br" in content_encoding:
                decoded_content = brotli.decompress(flow.response.content).decode('utf-8', errors='replace')
                compressed = 'br'
            else:
                decoded_content = flow.response.text
                compressed = None

            # Замена 'tgWebAppPlatform=web' на 'tgWebAppPlatform=ios' в содержимом
            if "tgWebAppPlatform=web" in decoded_content:
                ctx.log.info(f"'tgWebAppPlatform=web' найдено в ответе для URL: {flow.request.url}")
                modified_content = decoded_content.replace("tgWebAppPlatform=web", "tgWebAppPlatform=ios")

                # Повторное сжатие, если необходимо
                if compressed == 'gzip':
                    flow.response.content = zlib.compress(modified_content.encode('utf-8'))
                    ctx.log.info("Содержимое повторно сжато gzip.")
                elif compressed == 'br':
                    flow.response.content = brotli.compress(modified_content.encode('utf-8'))
                    ctx.log.info("Содержимое повторно сжато Brotli.")
                else:
                    flow.response.text = modified_content

                ctx.log.info(f"Содержимое ответа изменено для URL: {flow.request.url}")

            # Обновление длины содержимого, если необходимо
            if 'content-length' in flow.response.headers:
                flow.response.headers['content-length'] = str(len(flow.response.content))

    except Exception as e:
        ctx.log.error(f"Ошибка обработки ответа для URL {flow.request.url}: {e}")
"""

    os.makedirs(PROXY_DIR, exist_ok=True)
    with open(os.path.join(PROXY_DIR, 'modify_requests_responses.py'), 'w') as file:
        file.write(script_content)

def write_start_script():
    start_script_content = f"""#!/bin/bash
./venv/bin/mitmdump -s {os.path.join(PROXY_DIR, 'modify_requests_responses.py')} > {get_log_file_path()} 2>&1
"""
    os.makedirs(PROXY_DIR, exist_ok=True)
    with open(os.path.join(PROXY_DIR, 'start_mitmproxy.sh'), 'w') as file:
        file.write(start_script_content)
    os.chmod(os.path.join(PROXY_DIR, 'start_mitmproxy.sh'), 0o755)

def start_pm2_app(script_path, app_name):
    command = f"NODE_NO_WARNINGS=1 pm2 start {script_path} --name {app_name} --interpreter bash --watch {script_path} --output /dev/null --error /dev/null --log-date-format 'YYYY-MM-DD HH:mm Z'"
    subprocess.run(command, shell=True, check=True)

def main():
    process_name = "http-proxy"

    # Проверяем, существует ли процесс PM2
    pm2_process_exists = check_pm2_process_exists(process_name)

    # Если процесс PM2 не существует, продолжаем настройку
    if not pm2_process_exists:
        install_wheel_if_missing()

        print("Устанавливается mitmproxy...")
        install_mitmproxy()

        print("Копирование сертификатов...")
        copy_certificates()

        print("Запись modify_requests_responses.py...")
        write_modify_requests_responses_script()

        print("Запись start_mitmproxy.sh...")
        write_start_script()

        print("Создание процесса PM2...")
        start_pm2_app(os.path.join(PROXY_DIR, 'start_mitmproxy.sh'), 'http-proxy')

        print("Сохранение списка процессов PM2...")
        subprocess.run(['pm2', 'save'], check=True)

        print("Настройка завершена. Процесс http-proxy запущен.")

        time.sleep(5)

    else:
        print("Процесс PM2 запущен. Настройка пропущена.")

if __name__ == "__main__":
    main()