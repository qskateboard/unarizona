from fastapi import FastAPI, Request, Depends, status, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from routes.auth import router as auth_router
from routes.public import router as public_router
from routes.api import router as api_router
from routes.reactions import router as reactions_router

from security import manager
from models import *
from operations import *


app = FastAPI(title="unarizona api", description="Документация по работе с unarizona api<br>Данные авторизации не хранятся на наших серверах! Данные Cookie зашифрованы и хранятся частями в базе данных<br><a href='/'>Перейти на главную</a>")
app.mount("/static", StaticFiles(directory="static"), name="static")

# db.create_tables([Proxy, User, Log, Confirmation])

app.include_router(auth_router)
app.include_router(public_router)
app.include_router(api_router)
app.include_router(reactions_router)


class NotAuthenticatedException(Exception):
    pass


def exc_handler(request, exc):
    return RedirectResponse(url='/login')


manager.not_authenticated_exception = NotAuthenticatedException
app.add_exception_handler(NotAuthenticatedException, exc_handler)

