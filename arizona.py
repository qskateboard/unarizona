import re
import datetime
from sqlite3 import connect
import bs4
import aiohttp
from yarl import URL
from aiohttp_socks import ProxyType, ProxyConnector, ChainProxyConnector


class ReactJSException(Exception):
    pass


class ArizonaAPI:
    def __init__(self, cookie, user_agent, proxy_url=""):
        self.session = None
        self.timeout = 3
        self.proxy = proxy_url
        self.headers = {
            "user-agent": user_agent,
            "cookie": cookie
        }

    async def __aenter__(self):
        if len(self.proxy) > 1:
            connector = ProxyConnector.from_url(self.proxy)
            self.session = aiohttp.ClientSession(connector=connector)
            self.session.headers.update(self.headers)
            return self

        self.session = aiohttp.ClientSession()
        self.session.headers.update(self.headers)
        return self

    async def __aexit__(self, *err):
        await self.session.close()
        self._session = None

    async def setup(self, user_agent, cookie):
        self.headers = {
            "user-agent": user_agent,
            "cookie": cookie
        }
        self.session.headers.update(self.headers)

    async def test(self):
        async with self.session.get("https://forum.arizona-rp.com/") as resp:
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in await resp.text():
                return True
        return False

    async def login(self, username, password, code=""):
        uri = "https://forum.arizona-rp.com/login/login"
        async with self.session.get(uri) as resp:
            body = await resp.text()
            token = re.compile("name=\"_xfToken\" value=\"(.*)\" />").findall(body)[0]
            payload = {
                "login": username,
                "password": password,
                "remember": "1",
                "_xfRedirect": "https://forum.arizona-rp.com/account/",
                "_xfToken": token
            }
            async with self.session.post(uri, params=payload) as resp:
                body = await resp.text()
                if username in body:
                    cookies = code + "; "
                    for key, cookie in self.session.cookie_jar.filter_cookies(
                            URL('https://forum.arizona-rp.com/')).items():
                        cookies += "{}; ".format(str(cookie).replace("Set-Cookie: ", ""))
                    return cookies
                return False

    async def two_step(self, code, provider):
        uri = "https://forum.arizona-rp.com/login/two-step"
        async with self.session.get(uri) as resp:
            body = await resp.text()
            print(body)
            token = re.compile("name=\"_xfToken\" value=\"(.*)\" />").findall(body)[0]
            payload = {
                "code": code,
                "trust": "1",
                "confirm": "1",
                "provider": provider,
                "remember": "1",
                "_xfRedirect": "https://forum.arizona-rp.com/account/",
                "_xfToken": token
            }
            async with self.session.post(uri, params=payload) as resp:
                body = await resp.text()
                if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                    raise ReactJSException
                cookies = code + "; "
                for key, cookie in self.session.cookie_jar.filter_cookies(URL('https://forum.arizona-rp.com/')).items():
                    cookies += "{}; ".format(str(cookie).replace("Set-Cookie: ", ""))
                return cookies

    async def get_threads(self, url, page=1):
        if page > 1:
            if url[-1] == "/":
                url = url + "page-" + str(page)
            else:
                url = url + "/page-" + str(page)
        async with self.session.get(url) as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException

            soup = bs4.BeautifulSoup(body, "lxml")
            result = []
            for thread in soup.find_all('div', re.compile('structItem structItem--thread.*')):
                link = object
                unread = False
                closed = False
                pinned = False
                title_element = thread.find_all('div', "structItem-title")[0]
                for el in title_element.find_all("a"):
                    if "threads" in el['href']:
                        link = el

                if "structItem-status structItem-status--locked" in str(thread):
                    closed = True
                if "structItem-status structItem-status--sticky" in str(thread):
                    pinned = True
                if "unread" in link['href']:
                    unread = True

                creator = thread.find('a').text
                try:
                    creator = thread.find('img')['alt']
                except:
                    pass
                try:
                    creator = creator.replace("\n", "")
                    if len(creator) < 2:
                        creator = thread.find_all("a", {"data-xf-init": "member-tooltip"})[1].text
                except:
                    pass

                seo = thread.find_all("dd")

                result.append({
                    "title": link.text,
                    "link": "https://forum.arizona-rp.com" + link['href'].replace("unread", ""),
                    "creator": creator,
                    "latest": thread.find('div', re.compile('structItem-cell structItem-cell--latest')).find_all("a")[
                        1].text,
                    "closed_date": thread.find('time', re.compile('structItem-latestDate u-dt'))['data-time'],
                    "unread": unread,
                    "pinned": pinned,
                    "closed": closed,
                    "views": seo[2].text,
                    "replies": seo[1].text
                })
            return result

    async def get_category(self, url):
        async with self.session.get(url) as resp:
            soup = bs4.BeautifulSoup(await resp.text(), "lxml")
            return soup.find("h1", re.compile("p-title-value")).text

    async def get_categories(self, url):
        async with self.session.get(url) as resp:
            soup = bs4.BeautifulSoup(await resp.text(), "lxml")
            result = []
            for category in soup.find_all('div', re.compile('.*node--depth2 node--forum.*')):
                result.append({
                    "name": category.find("a").text,
                    "link": "https://forum.arizona-rp.com" + category.find("a")['href'],
                })
            return result

    async def get_post(self, url):
        async with self.session.get(url) as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException

            soup = bs4.BeautifulSoup(body, "lxml")
            post_id = str(int(url.split("post-")[1]))

            message = soup.find_all("article", {"id": "js-post-" + post_id})[0]

            async with self.session.get(f"https://forum.arizona-rp.com/posts/{post_id}/edit") as resp:
                body = await resp.text()
                soup2 = bs4.BeautifulSoup(body, "lxml")
                try:
                    result = {
                        "post_id": post_id,
                        "author": message['data-author'],
                        "timestamp": message.find("time", "u-dt")['data-time'],
                        "content": soup2.find("textarea", {"name": "message"}).text,
                        "content_html": soup2.find("textarea", {"name": "message_html"}).text,
                    }
                    return result
                except:
                    result = {
                        "post_id": post_id,
                        "author": message['data-author'],
                        "timestamp": message.find("time", "u-dt")['data-time'],
                        "message": message.find("article", "message-body").text
                    }
                    return result

    async def edit_post(self, uid, html):
        async with self.session.get(f"https://forum.arizona-rp.com/posts/{uid}/edit") as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException

            token = re.compile("name=\"_xfToken\" value=\"(.*)\" />").findall(body)[0]
            body = {
                "message_html": html,
                "message": html,
                "_xfToken": token,
            }
            async with self.session.post(f"https://forum.arizona-rp.com/posts/{uid}/edit", params=body):
                pass

    async def set_unread(self, url):
        symbol = "/"
        if url[-1] == "/":
            symbol = ""
        url = "{}{}mark-read?date={}".format(url, symbol, datetime.datetime.now().timestamp())
        async with self.session.get(url) as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException

            token = re.compile("name=\"_xfToken\" value=\"(.*)\" />").findall(body)[0]
            async with self.session.post(url, params={"_xfToken": token, "_xfWithData": "1",
                                                      "_xfResponseType": "json"}) as resp:
                pass

    async def send_message(self, url, message):
        async with self.session.get(url) as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException

            soup = bs4.BeautifulSoup(body, "lxml")
            form = soup.find_all("form")[6]

            action = "https://forum.arizona-rp.com" + form['action']
            token = re.compile("name=\"_xfToken\" value=\"(.*)\" />").findall(body)[0]
            json = {
                "message": message,
                "_xfToken": token,
                "last_date": form.find_all("input", {"name": "last_date"})[0]['value'],
                "last_known_date": form.find_all("input", {"name": "last_known_date"})[0]['value'],
            }
            async with self.session.post(action, params=json) as resp:
                pass

    async def get_thread(self, url):
        async with self.session.get(url) as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException

            soup = bs4.BeautifulSoup(body, "lxml")

            title = soup.find("h1", re.compile("p-title-value")).text
            post = soup.find_all('article', re.compile('message-threadStarterPost'))[0]
            return [title, post.find("div", "bbWrapper").text]

    async def close_thread(self, url):
        async with self.session.get(url) as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException

            token = re.compile("name=\"_xfToken\" value=\"(.*)\" />").findall(body)[1]
            query = {
                "_xfRequestUri": str(url).replace("https://forum.arizona-rp.com", ""),
                "_xfWithData": 1,
                "_xfToken": token,
                "_xfResponseType": "json",
            }
            async with self.session.post(url + "quick-close", params=query) as resp:
                pass

    async def pin_thread(self, url):
        async with self.session.get(url) as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in fbody:
                raise ReactJSException

            token = re.compile("name=\"_xfToken\" value=\"(.*)\" />").findall(body)[1]
            query = {
                "_xfRequestUri": str(url).replace("https://forum.arizona-rp.com", ""),
                "_xfWithData": 1,
                "_xfToken": token,
                "_xfResponseType": "json",
            }
            async with self.session.post(url + "quick-stick", params=query) as resp:
                pass

    async def get_account(self):
        async with self.session.get("https://forum.arizona-rp.com/account/") as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException

            email = re.compile("<dd>(.*)<a href=\"/account/email").findall(body.replace("\n", ""))[0]
            return email

    async def get_reactions(self, link):
        async with self.session.get(link + "reactions") as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException

            soup = bs4.BeautifulSoup(await resp.text(), "lxml")
            result = []
            for raw_user in soup.find_all("li", "block-row block-row--separated"):
                user = raw_user.find_all("a", "username")[0]
                result.append({"id": user['data-user-id'], "username": user.text})
            return result

    async def get_user_threads(self, username):
        link = "https://forum.arizona-rp.com/search/search"
        result = []
        async with self.session.get(link) as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException

            token = re.compile("name=\"_xfToken\" value=\"(.*)\" />").findall(body)[1]

            query = {
                "c[users]": username,
                "c[newer_than]": "",
                "order": "date",
                "search_type": "",
                "keywords": "",
                "_xfToken": token,
            }
            async with self.session.post(link, params=query, allow_redirects=False) as response:
                location = str(response).split("Location': \'")[1].split("\'")[0]
                link = location
            old_exist = True
            while old_exist:
                try:
                    for i in range(1, 6):
                        new_link = link
                        counter = 0
                        if i > 1:
                            new_link = link + "?page=" + str(i)
                        async with self.session.get(new_link) as resp2:
                            body2 = await resp2.text()
                            first_soup = bs4.BeautifulSoup(body2, "lxml")

                            for item in first_soup.find_all("li", re.compile("block-row block-row--separated.*")):
                                plink = item.find_all("div", "contentRow-main")[0].find_all("a")[0]['href']
                                plink = "https://forum.arizona-rp.com" + plink
                                result.append(plink)
                                counter += 1

                            if i >= 5:
                                another_page = first_soup.find_all("span", "block-footer-controls")
                                if another_page:
                                    link = "https://forum.arizona-rp.com" + another_page[0].find_all("a")[0]['href']
                                    async with self.session.post(link, params=query, allow_redirects=False) as response:
                                        location = str(response).split("Location': \'")[1].split("\'")[0]
                                        link = location
                                else:
                                    old_exist = False
                except:
                    old_exist = False
                    break
            return result

    async def get_profile(self, uid):
        link = "https://forum.arizona-rp.com/members/{}/".format(uid)
        async with self.session.get(link) as resp:
            body = await resp.text()
            if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                raise ReactJSException
            soup = bs4.BeautifulSoup(body, "lxml")
            block = soup.find_all("div", "memberHeader")[0]
            span = block.find_all("span", "username")[0]
            avatar = block.find_all("img", re.compile("avatar.*"))[0]['src']
            messages = block.find_all("a", "fauxBlockLink-linkRow u-concealed")[0].text
            reactions = block.find_all("dd")[1].text.replace("Реакции", "")
            data = {
                "id": span['data-user-id'],
                "username": span.text,
                "avatar": "https://forum.arizona-rp.com" + avatar,
                "messages": messages.replace("\n", "").replace("\t", "").replace(",", ""),
                "reactions": reactions.replace(" ", "").replace("\n", "").replace("\t", "").replace(",", "")
            }
            return data

    async def make_reaction(self, link, uid):
        reacted = False
        if "post-" in link:
            link = link.split("post-")[1].replace("/", "")
            try:
                uri = "https://forum.arizona-rp.com/posts/{}/react".format(link)
                async with self.session.get(
                        "https://forum.arizona-rp.com/posts/" + link + "/react?reaction_id=" + str(uid)) as resp:
                    body = await resp.text()
                    if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                        raise ReactJSException

                    if "Вы действительно хотите оставить эту реакцию?" in body:
                        token = re.compile("name=\"_xfToken\" value=\"(.*)\" />").findall(body)[6]
                        async with self.session.post(uri, params={"reaction_id": uid, "_xfToken": token}) as resp:
                            pass
                        reacted = True
            except:
                return False
        else:
            if "https://forum.arizona-rp.com/threads/" in link:
                try:
                    async with self.session.get(link) as resp:
                        body = await resp.text()
                        if "<script type=\"text/javascript\" src=\"/aes.min.js\" >" in body:
                            raise ReactJSException

                        soup = bs4.BeautifulSoup(body, "lxml")
                        for post in soup.findAll('article', {'class': 'message'}):
                            hrefs = post.findAll('a')
                            for a in hrefs:
                                if "/post-" in a['href']:
                                    number = a['href'].split("post-")[1].replace("/", "")
                                    uri = "https://forum.arizona-rp.com/posts/{}/react".format(str(number))
                                    async with self.session.get(
                                            "https://forum.arizona-rp.com/posts/" + number + "/react?reaction_id=" + str(
                                                uid)) as resp:
                                        body = await resp.text()
                                        if "Вы действительно хотите оставить эту реакцию?" in body:
                                            token = re.compile("name=\"_xfToken\" value=\"(.*)\" />").findall(body)[6]
                                            async with self.session.post(uri, params={"reaction_id": uid,
                                                                                      "_xfToken": token}) as resp:
                                                pass
                                            reacted = True
                                    break
                                if reacted:
                                    break
                            if reacted:
                                break
                except:
                    return False
        return reacted
