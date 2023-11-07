import datetime
import random
import string

from peewee import *

db = SqliteDatabase('database.db')


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    username = CharField(unique=True)
    password = TextField()
    email = CharField()
    ip_address = CharField()
    join_date = DateTimeField(default=datetime.datetime.now())
    daily_limit = IntegerField(default=10)
    status = IntegerField(default=1)
    api_key = CharField(default='')
    cookie = TextField(default='')


class Log(BaseModel):
    user = ForeignKeyField(User, field="username")
    method = CharField()
    code = IntegerField(default=200)
    date = DateTimeField(default=datetime.datetime.now())


class Confirmation(BaseModel):
    user = ForeignKeyField(User)
    code = CharField()
    date = DateTimeField(default=datetime.datetime.now())


class Proxy(BaseModel):
    user = ForeignKeyField(User)
    url = TextField()
