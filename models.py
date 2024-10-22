from pydantic import BaseModel, constr, field_validator
from typing import ClassVar, Optional
from enum import Enum
from pytoniq_core import begin_cell, Address, Cell
import config
from opcodes import Opcodes

class CurrencyEnum(str, Enum):
    Ton = "Ton"
    Jetton = "Jetton"


class Offer(BaseModel):
    description: str
    price: int
    currency: str
    jetton_master: Optional[str]

    def __init__(self, description: str, price: int, currency: str, jetton_master: str | None = None):
        super().__init__(description=description, price=price, currency=currency, jetton_master=jetton_master)

    def recalculate_price_in_nano(self, decimals: int):
        self.price = int(self.price * 10**decimals)

    def __hash__(self):
        return hash(self.description) + self.price + hash(self.currency) + 0 if self.jetton_master is None else hash(self.jetton_master)

    #Check that description is not empty and less than 400 characters
    @field_validator('description', mode="after")
    def description_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Описание не должно быть пустым или содержать только пробелы.')
        if len(v) > 400:
            raise ValueError("Описание не должно быть длиннее 400 символов.")
        return v

    #Check that price is greater than 0
    @field_validator('price', mode="after")
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Цена должна быть больше 0.')
        return v

    @field_validator('currency', mode='after')
    def currency_must_be_jetton_or_ton(cls, v):
        if v != "Ton" and v != "Jetton":
            raise ValueError('You must enter Ton or Jetton in currency field')
        return v

    #if currency is jetton, then jetton_master must be set
    @field_validator('jetton_master', mode="after")
    def jetton_master_must_be_set(cls, v, info):
        if info.data.get('currency') == 'Jetton' and not v:
            raise ValueError('Для Jetton необходимо указать jetton_master.')
        return v



