import asyncio
import re

import requests
from requests import ConnectTimeout

from fastapi import APIRouter, Depends, Form, Request, status, Query
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi_login.exceptions import InvalidCredentialsException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
import pydantic
import aiohttp
from python_socks import _errors

from bypass import bypass, bypass_async
from arizona import ArizonaAPI, ReactJSException
from security import *
from operations import *
from api_models import *

router = APIRouter(prefix="/api")

resp = {
    "token": JSONResponse({"status": "error", "message": "Уазанный API токен не существует"}, 401),
    "limit": JSONResponse({"status": "error", "message": "Достигнут лимит использование API для этого аккаунта"}, 426),
    "no_auth": JSONResponse({"status": "error", "message": "Форумный аккаунт не авторизован!"}, 406),
    "cred": JSONResponse({"status": "error", "message": "Неправильный логин или пароль!"}, 404),
    "aes": JSONResponse({"status": "error", "message": "Необходимо обновить сессию ReactJS"}, 400),
    "no_conn": JSONResponse({"status": "error", "message": "Нет подключения к форуму Arizona RP"}, 503),
}

ua = "Mozilla/5.0 (Linux; Android 11; V2109 Build/RP1A.200720.012; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/94.0.4606.85 Mobile Safari/537.36 GSA/12.39.19.23.arm64"

responses = {
    401: {"model": Message},
    426: {"model": Message},
    406: {"model": Message},
    400: {"model": Message},
    404: {"model": Message},
    503: {"model": Message},
}


@router.get("/test", tags=["unarizona"], description="Проверка работоспособности API", responses=responses,
            response_model=TestModel)
async def test(api_key: str = Query(None, description="Access token")):
    user = get_token(api_key)
    if user:
        return {"details": "works"}
    return resp["token"]


@router.get("/limit", tags=["unarizona"], description="Получить сводку по лимитам", responses=responses,
            response_model=LimitsModel)
async def limit_information(api_key: str = Query(None, description="Access token")):
    user = get_token(api_key)
    if user:
        count = len(get_daily_user_logs(user))
        return {
            "used": count,
            "limit": user.daily_limit,
            "remained": user.daily_limit - count,
        }
    return resp["token"]


@router.get("/proxy", tags=["unarizona"], description="Установить прокси для запросов", responses=responses,
            response_model=ResultModel)
async def setup_proxy(
        proxy_url: str = Query(None, description="Ссылка на прокси, i.e. socks5://log:pass@ip:port"),
        api_key: str = Query(None, description="Access token")):
    user = get_token(api_key)
    if user:
        try:
            async with ArizonaAPI("", ua, proxy_url) as arz:
                test = await arz.test()
                proxy, created = Proxy.get_or_create(user=user, defaults={'user': user, 'url': ""})
                proxy.url = proxy_url
                proxy.save()
                if test:
                    return {"status": "success", "result": "Прокси рабочий и успешно установлен"}
                return {"status": "error", "result": "Не доступен сайт с данного прокси"}
        except TypeError:
            return {"status": "error", "result": "Невалидный тип прокси"}
        except _errors.ProxyConnectionError:
            return {"status": "error", "result": "Не удаётся подключиться к прокси"}
        except _errors.ProxyTimeoutError:
            return {"status": "error", "result": "Не удаётся подключиться к прокси"}
        except:
            return {"status": "error", "result": "Не доступен сайт с данного прокси"}

    return resp["token"]


@router.get("/remove.proxy", tags=["unarizona"], description="Удаляет прокси", responses=responses,
            response_model=ResultModel)
async def remove_proxy(
        api_key: str = Query(None, description="Access token")):
    user = get_token(api_key)
    if user:
        proxy = Proxy.get_or_none(user=user)
        if proxy:
            proxy.delete_instance()
            return {"status": "success", "result": "Прокси успешно удалён"}
        return {"status": "error", "result": "Прокси не был установлен для этого аккаунта"}
    return resp["token"]


@router.get("/auth", tags=["Авторизация форумного аккаунта"],
            description="Авторизирует форумный аккаунт на определенный API ключ", responses=responses,
            response_model=SuccessModel)
async def auth(
        login: str = Query(None, description="Логин форумного аккаунта"),
        password: str = Query(None, description="Пароль от форумного аккаунта"),
        api_key: str = Query(None, description="Access token")
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "auth", 200)

            try:
                code = await bypass_async(ua, get_proxy(user))
                async with ArizonaAPI(code[0], ua, get_proxy(user)) as arz:
                    cookie = await arz.login(login, password, code[0])

                    if cookie:
                        user.cookie = crypt_string(cookie, user.username)
                        user.save()
                        return {"status": "success"}
                    return resp["cred"]
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
            except ConnectTimeout:
                return resp["no_conn"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/two-factor", tags=["Авторизация форумного аккаунта"],
            description="Авторизирует сессию, если есть доп. привязка", responses=responses,
            response_model=SuccessModel)
async def two_factor_auth(
        fa_code: str = Query(None, description="Код"),
        provider: str = Query(None, description="Метод привязки: приложение - totp/почта - email"),
        api_key: str = Query(None, description="Access token"),
):
    if provider in ["totp", "email"]:
        pass
    else:
        return {"status": "success", "message": "Выбранного провайдера не существует"}

    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "two-factor", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        new = await arz.two_step(fa_code, provider)
                    except ReactJSException:
                        return resp['aes']

                    user.cookie = crypt_string(new, user.username)
                    user.save()
                    return {"status": "success"}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/session", tags=["Авторизация форумного аккаунта"], description="Обновление сессии ReactJS",
            responses=responses, response_model=SuccessModel)
async def update_session(
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "session", 200)

            try:
                code = await bypass_async(ua, get_proxy(user))
                user.cookie = crypt_string(code[0] + ";", user.username)
                user.save()
                return {"status": "success"}
            except ConnectTimeout:
                return resp["no_conn"]
            except IndexError:
                return resp["no_conn"]
            except:
                return resp["no_conn"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/categories", tags=["Категории"], description="Возвращает категории раздела", responses=responses,
            response_model=ResultModel)
async def get_categories(
        url: str = Query(None, description="Ссылка на раздел"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "get_categories", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.get_categories(url)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success", "result": r}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/category", tags=["Категории"], description="Возвращает название категории", responses=responses,
            response_model=ResultModel)
async def get_category(
        url: str = Query(None, description="Ссылка на раздел"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "get_category", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.get_category(url)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success", "result": r}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/threads", tags=["Темы"], description="Возвращает все темы на странице", responses=responses,
            response_model=ResultModel)
async def get_threads(
        url: str = Query(None, description="Ссылка на раздел"),
        page: int = Query(1, description="Страница"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "get_threads", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.get_threads(url, page)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success", "result": r}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/get.thread", tags=["Темы"], description="Возвращает информацию о теме", responses=responses,
            response_model=ResultModel)
async def get_thread(
        url: str = Query(None, description="Ссылка на пост"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "get_thread", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.get_thread(url)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success", "result": r}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/close.thread", tags=["Темы"], description="Закрывает/открывает тему", responses=responses,
            response_model=SuccessModel)
async def close_thread(
        url: str = Query(None, description="Ссылка на тему"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "close_thread", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        await arz.close_thread(url)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success"}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/pin.thread", tags=["Темы"], description="Закрепляет/открепляет тему", responses=responses,
            response_model=SuccessModel)
async def pin_thread(
        url: str = Query(None, description="Ссылка на тему"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "pin_thread", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        await arz.pin_thread(url)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success"}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/get.post", tags=["Посты"], description="Возвращает информацию о посте", responses=responses,
            response_model=ResultModel)
async def get_post(
        url: str = Query(None, description="Ссылка на пост"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "get_post", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.get_post(url)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success", "result": r}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/edit.post", tags=["Посты"], description="Редактирует пост", responses=responses,
            response_model=SuccessModel)
async def edit_post(
        pid: str = Query(None, description="ID поста"),
        html: str = Query(None, description="HTML код, на который будет заменен пост"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "edit_post", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.edit_post(pid, html)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success"}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/set.viewed", tags=["Категории"], description="Отмечает все посты в категории просмотренными",
            responses=responses, response_model=SuccessModel)
async def make_viewed(
        url: str = Query(None, description="Ссылка на категорию"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "set_unread", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.set_unread(url)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success"}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/get.reactions", tags=["Другое"], description="Выводит всех, кто поставил реакцию на пост",
            responses=responses, response_model=ResultModel)
async def get_reactions(
        url: str = Query(None, description="Ссылка на пост"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "get_reactions", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.get_reactions(url)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success", "result": r}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/get.posts", tags=["Посты"], description="Выводит все посты пользователя",
            responses=responses, response_model=ResultModel)
async def get_posts(
        username: str = Query(None, description="Логин"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "get_posts", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.get_user_threads(username)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success", "result": r}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/get.profile", tags=["Другое"], description="Выводит информацию по профилю",
            responses=responses, response_model=ResultModel)
async def get_profile(
        uid: str = Query(None, description="ID пользователя"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "get_profile", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.get_profile(uid)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success", "result": r}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/message", tags=["Посты"], description="Опубликовывает пост в теме", responses=responses,
            response_model=SuccessModel)
async def send_message(
        url: str = Query(None, description="Ссылка на тему"),
        message: str = Query(None, description="Тело поста"),
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "send_message", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.send_message(url, message)
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success"}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/reaction", tags=["Другое"], description="Ставит реакцию на тему/пост", responses=responses,
            response_model=ResultModel)
async def make_reaction(
        url: str = Query(None, description="Ссылка на цель"),
        rid: str = Query(None, description="ID реакции"),
        api_key: str = Query(None, description="Access token"),
):
    if rid in ["1", "2", "3", "4", "5", "6", "8"]:
        pass
    else:
        return {"status": "success", "message": "Выбранной реакции не существует"}

    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "reaction", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        reacted = await arz.make_reaction(url, rid)
                    except ReactJSException:
                        return resp['aes']

                    if reacted:
                        return {"status": "success", "result": True}
                    return {"status": "success", "result": False}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


@router.get("/get.account", tags=["Другое"], description="Возвращает информацию об аккаунте", responses=responses,
            response_model=ResultModel)
async def get_account(
        api_key: str = Query(None, description="Access token"),
):
    user = get_token(api_key)
    if user:
        if len(get_daily_user_logs(user)) < user.daily_limit:
            add_log(user, "get_account", 200)

            cookie = decrypt_string(user.cookie, user.username)
            try:
                async with ArizonaAPI(cookie, ua, get_proxy(user)) as arz:
                    try:
                        r = await arz.get_account()
                    except ReactJSException:
                        return resp['aes']

                    return {"status": "success", "result": r}
            except aiohttp.client_exceptions.ClientConnectorError:
                return resp["no_conn"]
            except IndexError:
                return resp["no_auth"]
        else:
            return resp["limit"]
    return resp["token"]


log_cooldown = 0


@router.get("/info", tags=["Admin Tools"], description="Вывод информации об аккаунте из логов", responses=responses)
async def get_account_info(account_id: str = Query(None, description="Ник или ID аккаунта"),
                            server: str = Query(None, description="Номер сервера"),
                            api_key: str = Query(None, description="Access token")):
    user = get_token(api_key)
    global log_cooldown
    if user and api_key in []:
        if datetime.datetime.now().timestamp() - log_cooldown >= 30:
            payload = {
                "random_id": random.randint(1, 10000000),
                "peer_id": "-172773148",
                "message": f"!info {account_id} {server if server != '16' else ''}",
                "dont_parse_links": "0",
                "disable_mentions": "0",
                "intent": "default",
                "access_token": "",
                "v": "5.131",
            }
            requests.post("https://api.vk.com/method/messages.send", data=payload)
            log_cooldown = datetime.datetime.now().timestamp()
            found = False
            raw_msg = ""
            for i in range(1, 5):
                await asyncio.sleep(1)
                payload = {
                    "peer_id": "",
                    "count": 1,
                    "access_token": "",
                    "v": "5.131",
                }
                r = requests.post("https://api.vk.com/method/messages.getHistory", data=payload)
                history = r.json()['response']['items']
                if "Дата регистрации" in history[0]['text']:
                    found = True
                    raw_msg = history[0]['text']
                    break
                elif "Аккаунт" in history[0]['text'] and "не найден!" in history[0]['text']:
                    return {"status": "error", "message": "Account does not exist"}
                else:
                    pass

            if not found:
                return {"status": "error", "message": "Waiting time exceeded"}

            regex = re.compile(r"""Ник: (.*)\[(.*)]
Уровень: (.*)
Фракция: (.*)
Ранг: (.*)
Доп. слотов: (.*)
Az-Coin: (.*)
На руках: (.*)
Банк: (.*)
Депозит: (.*)
Личный счет 1: (.*)
Личный счет 2: (.*)
Личный счет 3: (.*)
Всего денег: (.*)
Евро: (.*)
По курсу 6к: \~(.*)
Биткоин: (.*)
По курсу 40к: ~(.*)
Фишки казино: (.*)
По курсу 90: ~(.*)
Общее кол-во вирт: ~(.*)
Почта: (.*)
ВК в игре: (.*)
Дата регистрации: (.*)
Последний вход: (.*)
R-IP: (.*)
L-IP: (.*)""", re.MULTILINE)
            result = regex.findall(re.compile("Уровень адм: .\n").sub(r"", raw_msg.replace("$", "")))[0]
            return {
                "nickname": result[0],
                "id": result[1],
                "level": result[2],
                "faction": result[3],
                "rank": result[4],
                "slots": result[5],
                "az_coins": result[6].replace(".", ""),
                "money_hand": result[7].replace(".", ""),
                "money_bank": result[8].replace(".", ""),
                "money_deposit": result[9].replace(".", ""),
                "money_bank1": result[10].replace(".", ""),
                "money_bank2": result[11].replace(".", ""),
                "money_bank3": result[12].replace(".", ""),
                "money_total": result[13].replace(".", ""),
                "euro": result[14].replace(".", ""),
                "euro_money": result[15].replace(".", ""),
                "bitcoin": result[16].replace(".", ""),
                "bitcoin_money": result[17].replace(".", ""),
                "casino": result[18].replace(".", ""),
                "casino_money": result[19].replace(".", ""),
                "total_money": result[20].replace(".", ""),
                "email": result[21],
                "vk": result[22],
                "reg_date": result[23],
                "last_date": result[24],
                "reg_ip": result[25],
                "last_ip": result[26],
            }

        else:
            return {"status": "error",
                    "message": f"Wait {int(60 - (datetime.datetime.now().timestamp() - log_cooldown))} sec to call this method again"}
    return resp["token"]
