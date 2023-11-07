import datetime

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_login.exceptions import InvalidCredentialsException
from fastapi.responses import HTMLResponse, RedirectResponse

from operations import *
from security import manager, sha224

router = APIRouter(
    prefix="/auth"
)


@router.post("/login", include_in_schema=False)
def login(data: OAuth2PasswordRequestForm = Depends()):
    username = data.username
    password = data.password

    user = get_user(username)
    if not user:
        raise InvalidCredentialsException
    elif sha224(password) != user.password:
        raise InvalidCredentialsException
    access_token = manager.create_access_token(
        data={"sub": username},
        expires=datetime.timedelta(hours=72)
    )
    resp = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    manager.set_cookie(resp, access_token)
    return resp


@router.post("/register", include_in_schema=False)
def register(request: Request, username: str = Form(), email: str = Form(), password: str = Form(), password2: str = Form()):
    if username and email and password and password2:
        if password2 == password and len(password) > 7:
            if not get_user(username):
                user = create_user(username, sha224(password), email, request.client.host, ''.join(random.choices(string.ascii_lowercase + string.digits, k=32)))
                code = Confirmation.create(user=user, code=sha224(user.username + "bgdfnsdr"))
                code.save()
                send_mail(user.email, api_url + "/confirm?c=" + str(code.code))
                resp = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
                return resp
            else:
                raise InvalidCredentialsException
        else:
            raise InvalidCredentialsException
    else:
        raise InvalidCredentialsException
