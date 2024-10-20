import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pytoniq_core import Address, Cell, StateInit
import sys
import redis.asyncio as redis

import config
import transactions
from config import TOKEN

import TonConnector
from pytonconnect import TonConnect
import models
from pytonapi import AsyncTonapi

Redis_client = redis.Redis(host='localhost', port=6379)
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    chat_id = message.chat.id
    connector = TonConnector.get_connector(chat_id)
    connected = await connector.restore_connection()
    await message.answer(text=f'Welcome to Escrow bot!, {message.from_user.first_name}!')
    if connected:
        wallet_address = Address(connector.account.address).to_str(is_bounceable=False)
        await message.answer(text=f"You are already connected with wallet {wallet_address}")
    else:
        await message.answer(text='Welcome to Escrow bot! This bot will help you to safely exchange anything you want '
                                  'to tons or jettons')
        wallets_list = TonConnect.get_wallets()
        mk_b = InlineKeyboardBuilder()
        for wallet in wallets_list:
            mk_b.button(text=wallet['name'], callback_data=f'connect:{wallet["name"]}')
        mk_b.adjust(1, )
        await message.answer(text='Choose wallet to connect', reply_markup=mk_b.as_markup())


async def connect_wallet(callback_query: types.CallbackQuery):
    message = callback_query.message
    connector = TonConnector.get_connector(message.chat.id)
    wallet_name = callback_query.data.split(':')[1]
    wallets_list = connector.get_wallets()
    wallet = None

    for w in wallets_list:
        if w['name'] == wallet_name:
            wallet = w

    if wallet is None:
        raise Exception(f'Unknown wallet: {wallet_name}')

    generated_url = await connector.connect(wallet)

    mk_b = InlineKeyboardBuilder()
    mk_b.button(text='Connect', url=generated_url)

    await message.answer(text='Connect wallet within 3 minutes', reply_markup=mk_b.as_markup())

    for i in range(1, 180):
        await asyncio.sleep(1)
        if connector.connected:
            if connector.account.address:
                wallet_address = connector.account.address
                wallet_address = Address(wallet_address).to_str(is_bounceable=False)
                await message.answer(f'You are connected with address <code>{wallet_address}</code>')
                logging.info(f'Connected with address: {wallet_address}')
            return

    await message.answer(f'Timeout error!', reply_markup=mk_b.as_markup())
    await callback_query.answer()


form_fields = ['Description (400 characters max.)', 'Price (float)', 'Currency (Ton or Jetton)']


class FormStates(StatesGroup):
    WAITING_FOR_INPUT = State()


# Функция для создания клавиатуры с текущими значениями полей
def get_form_keyboard(user_data):
    builder = InlineKeyboardBuilder()
    for field in form_fields:
        print(user_data)
        value = user_data.get(field, 'Undefined')
        builder.add(
            InlineKeyboardButton(
                text=f"{field}: {value}",
                callback_data=f"field:{field}"
            )
        )
    builder.add(InlineKeyboardButton(text="Deploy this offer", callback_data="deploy"))
    builder.adjust(1, )
    return builder.as_markup()


@dp.message(Command("CreateOffer"))
async def cmd_sell(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    await message.answer(
        "Fill this form:",
        reply_markup=get_form_keyboard(user_data)
    )


@dp.message(FormStates.WAITING_FOR_INPUT)
async def handle_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data.get('current_field')
    value = message.text

    await state.set_state(None)
    if value != "cancel":
        await state.update_data({field: value})
        # Получаем обновленные данные
        user_data = await state.get_data()
        await message.answer(
            f"Value {field} is updated!",
            reply_markup=get_form_keyboard(user_data)
        )


async def process_callback_button(callback_query: types.CallbackQuery, state: FSMContext):
    field = callback_query.data.split(":")[1]  # Получаем название поля из callback_data
    await state.update_data(current_field=field)
    await bot.send_message(
        callback_query.from_user.id,
        f"Enter value {field}: or cancel to return"
    )
    await state.set_state(FormStates.WAITING_FOR_INPUT)
    await callback_query.answer()


async def deploy_offer(callback_query: types.CallbackQuery, state: FSMContext):
    tonapi = AsyncTonapi(api_key=config.tonapi_key)
    data = await state.get_data()
    try:
        offer = models.Offer(*[data.get(field, None) for field in form_fields])
        jetton_meta = await tonapi.jettons.get_info(offer.jetton_master)
        offer.price = int(offer.price * 10 ** jetton_meta["metadata"]["decimals"])
    except Exception as e:
        await callback_query.answer(f"Error in fields {e}")
        return

    try_num = 0
    while True:  #maybe this contract is already taken
        deploy_data = transactions.create_ton_escrow_data(
            hash(offer) + callback_query.message.from_user.id + try_num % 2 ** 64)
        deploy_code = Cell.one_from_boc(config.escrow_code)
        state_init = StateInit(code=deploy_code, data=deploy_data)
        new_contract_address = Address("0:" + state_init.serialize().hash.hex())
        info = await tonapi.accounts.get_info(new_contract_address.to_str())
        if info["status"] != "active":
            break
        try_num += 1
    init_message = transactions.get_deploy_escrow_message(state_init=state_init, offer=offer)

    await state.set_state(None)

    await callback_query.answer()
    await callback_query.message.answer("Accept transaction in your wallet app")
    # Здесь можно использовать данные из data для создания оффера


async def main():
    tonapi = AsyncTonapi(api_key=config.tonapi_key)

    await bot.delete_webhook(drop_pending_updates=True)  # skip_updates = True
    await dp.start_polling(bot)


if __name__ == "__main__":
    # register query handler
    dp.callback_query.register(connect_wallet, lambda c: c.data and c.data.startswith('connect:'))
    dp.callback_query.register(process_callback_button, lambda c: c.data and c.data.startswith('field:'))
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
