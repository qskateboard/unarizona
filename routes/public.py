from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi_login.exceptions import InvalidCredentialsException
from fastapi.responses import HTMLResponse, RedirectResponse

from security import *
from operations import *

router = APIRouter(prefix="")


@manager.user_loader
def load_user(username):
    return get_user(username)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.get("/confirm", response_class=HTMLResponse, include_in_schema=False)
async def confirm(request: Request, c: str):
    if c:
        code = Confirmation.get_or_none(code=c)
        if code:
            if code.user.status == 1:
                user = get_user(code.user.username)
                user.status = 2
                user.save()
                code.delete()
                resp = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
                return resp


@router.get("/dashboard", include_in_schema=False)
def dashboard_page(request: Request, user=Depends(manager)):
    if user.status == 1:
        return templates.TemplateResponse("confirm.html", {"request": request})

    logs = []
    for log in get_daily_user_logs(user):
        logs.append(log)

    all_logs = []
    for log in get_user_logs(user):
        all_logs.append(log)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "logs": logs, "all_logs": all_logs[-8:]})


@router.get("/paid", include_in_schema=False)
def paid_page(request: Request, user=Depends(manager)):
    if user.status == 1:
        return templates.TemplateResponse("confirm.html", {"request": request})
    return templates.TemplateResponse("paid.html", {"request": request, "user": user})


@router.get("/user", include_in_schema=False)
def paid_page(request: Request, user=Depends(manager)):
    if user.status == 1:
        return templates.TemplateResponse("confirm.html", {"request": request})
    return templates.TemplateResponse("profile.html", {"request": request, "user": user})


@router.get("/logout", include_in_schema=False)
def logout(request: Request, _=Depends(manager)):
    resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    manager.set_cookie(resp, "")
    return resp
