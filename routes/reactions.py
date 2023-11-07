import asyncio

import aiohttp
from pathlib import Path
from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from arizona import ArizonaAPI
from bypass import bypass_async
from security import *
from operations import *
import pyotp

router = APIRouter(
    prefix="/reactions",
    include_in_schema=False
)
ua = "Mozilla/5.0 (Linux; Android 11; V2109 Build/RP1A.200720.012; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/94.0.4606.85 Mobile Safari/537.36 GSA/12.39.19.23.arm64"
api = "https://unarizona.pw/api"
token = ""
first_run = True
session = aiohttp.ClientSession()


async def init_acc():
    link = "{}/session?api_key={}".format(api, token)
    await session.get(link)
    link = "{}/auth?api_key={}&login={}&password={}".format(api, token, "", "")
    await session.get(link)


async def parse_posts(username, fid):
    filename = "./profiles/{}.txt".format(fid)
    link = "{}/get.posts?api_key={}&username={}".format(api, token, username)
    async with session.get(link) as resp:
        json = await resp.json()
        save = []
        for url in json['result']:
            save.append("{}|0".format(url))
        with open(filename, "w") as fp:
            fp.write("``".join(save))


def find_job(username):
    filename = "./profiles/{}.txt".format(username)
    found = "not_found"
    with open(filename, "r") as fp:
        posts = fp.read().split("``")
        for i in range(len(posts)):
            post = posts[i].split("|")
            if post[1] == "0":
                found = post[0]
                posts[i] = post[0] + "|1"
                break
        if found != "not_found":
            with open(filename, "w") as fp2:
                fp2.write("``".join(posts))
        return found


def find_post(username):
    filename = "./profiles/1005690.txt"
    found = "not_found"
    with open(filename, "r") as fp:
        posts = fp.read().split("``")
        for i in range(len(posts)):
            post = posts[i].split("|", 1)
            done = post[1].split("~?~")
            if username not in done:
                found = post[0]
                posts[i] = post[0] + "|" + "~?~".join(done + [username])
                break
        if found != "not_found":
            with open(filename, "w") as fp2:
                fp2.write("``".join(posts))
        return found


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    global first_run
    if first_run:
        await init_acc()
        first_run = False

    return templates.TemplateResponse("reactions.html", {"request": request})


@router.get("/manual")
async def manual(url, fid, skip="0"):
    link = "{}/get.profile?uid={}&api_key={}".format(api, int(fid), token)
    async with session.get(link) as resp:
        body = await resp.json()
        username = body['result']['username']
    new = False
    if skip == "0":
        link = "{}/get.reactions?api_key={}&url={}".format(api, token, url)
        async with session.get(link) as resp:
            json = await resp.json()
            for user in json['result']:
                if user['username'] == username:
                    new = True
                    break
    else:
        new = True

    if new:
        filename = "./profiles/{}.txt".format(fid)
        file = Path(filename)
        if not file.exists():
            await parse_posts(username, fid)

        url = find_job(fid)
        if url != "not_found":
            link = "{}/reaction?api_key={}&url={}&rid={}".format(api, token, url, 2)
            await session.get(link)

        job = find_post(fid)

        if "post-" in job:
            job = "https://forum.arizona-rp.com/posts/{}/".format(job.split("post-")[1])

        return job
    else:
        return "false"


async def add_reaction(_arz, _url):
    await _arz.make_reaction(_url, 2)


async def add_reaction_api(_session, _url):
    link = "{}/reaction?api_key={}&url={}&rid=2".format(api, token, _url)
    await _session.get(link)


@router.get("/auto")
async def automatic(username, password):
    my_posts = {}
    other_posts = {}
    link = "{}/get.posts?api_key={}&username={}".format(api, token, "Lee Dohyeon")
    async with session.get(link) as resp:
        json = await resp.json()
        my_posts = json['result']
    link = "{}/get.posts?api_key={}&username={}".format(api, token, username)
    async with session.get(link) as resp:
        json = await resp.json()
        other_posts = json['result']

    try:
        code = await bypass_async(ua)
        async with ArizonaAPI(code[0], ua) as arz:
            cookie = await arz.login(username, password, code[0])
            arz.setup(ua, cookie)
            await asyncio.gather(*[add_reaction(arz, url) for url in my_posts], return_exceptions=False)
            await asyncio.gather(*[add_reaction_api(session, url) for url in other_posts], return_exceptions=False)

            return "Задача успешно выполнена"
    except IndexError:
        return "Неверный логин или пароль"
    except:
        return "Нет подключения к сайту Arizona Role Play"
