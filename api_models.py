from pydantic import BaseModel


class Message(BaseModel):
    status: str
    message: str


class TestModel(BaseModel):
    details: str


class LimitsModel(BaseModel):
    used: int
    limit: int
    remained: int

    class Config:
        schema_extra = {
            "example": {
                "used": 3,
                "limit": 10,
                "remained": 7,
            }
        }


class SuccessModel(BaseModel):
    status: str = "success"


class ResultModel(BaseModel):
    status: str = "success"
    result: object
