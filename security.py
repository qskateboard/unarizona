import base64
import hashlib

import cryptocode
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi_login import LoginManager
from fastapi.templating import Jinja2Templates

from operations import get_user

SECRET = ""
salt = ""

templates = Jinja2Templates(directory="templates")
manager = LoginManager(SECRET, token_url="/auth/login", use_cookie=True)
manager.cookie_name = "auth"


def b64_encode(string):
    sample_string_bytes = string.encode("ascii")
    base64_bytes = base64.b64encode(sample_string_bytes)
    return base64_bytes.decode("ascii")


def b64_decode(string):
    sample_string_bytes = base64.b64decode(string)
    return sample_string_bytes.decode("ascii")


def crypt_string(string, key):
    password = b64_encode(salt + key)
    encoded = cryptocode.encrypt(string, password)
    return encoded


def decrypt_string(string, key):
    password = b64_encode(salt + key)
    decrypted = cryptocode.decrypt(string, password)
    return decrypted


def sha224(string):
    encrypted = hashlib.sha224(string.encode("ascii")).hexdigest()
    return encrypted
