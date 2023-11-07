from models import *
from email.header import Header
from mailer import Mailer, Message

api_url = "https://unarizona.pw"


def get_last_day():
    now = datetime.datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def get_user(username):
    return User.get_or_none(username=username)


def create_user(username, password, email, ip, api_key):
    user = User.create(username=username, password=password, email=email, ip_address=ip, api_key=api_key)
    user.save()
    return user


def get_user_logs(user):
    return Log.select().where(Log.user == user)


def get_daily_user_logs(user):
    return Log.select().where((Log.date > get_last_day()) & (Log.user == user))


def add_log(user, method, code):
    Log.create(user=user, method=method, code=code)


def get_token(token):
    return User.get_or_none(api_key=token)


def get_proxy(user):
    proxy = Proxy.get_or_none(user=user)
    if proxy:
        return proxy.url
    return ""


def send_mail(to, link):
    import smtplib

    FROM = "unarizona@skateware.win"
    TO = to if isinstance(to, list) else [to]
    SUBJECT = "Подтверждение аккаунта"
    TEXT = """Чтобы создать аккаунт на unarizona api, перейдите по следующей ссылке: {}""".format(link)

    # Prepare actual message
    message = """From: %s\nTo: %s\nSubject: %s\n\n%s
        """ % (FROM, ", ".join(TO), SUBJECT, TEXT)

    try:
        server = smtplib.SMTP("smtp.yandex.ru", 587)
        server.ehlo()
        server.starttls()
        server.login("", "")
        server.sendmail(FROM, TO, message.encode('utf-8'))
        server.close()
    except:
        pass
