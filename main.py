import logging
import asyncio
import logging
import sys
import time
import traceback

import redis.asyncio as redis
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.filters.command import CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton
from aiogram.utils.deep_linking import create_start_link
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pytonapi import AsyncTonapi
from pytonconnect import TonConnect
from pytonconnect.exceptions import UserRejectsError
from pytoniq_core import Address, Cell, StateInit
from aiogram.utils.deep_linking import decode_payload as decode_deep_link

import TonConnector
import config
import database
import models
import transactions
import utils
from config import TOKEN

Redis_client = redis.Redis(host='localhost', port=6379)
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

dsn = "postgresql://postgres:@localhost:5432/postgres"
db = database.DatabaseHandler(dsn=dsn)


async def pay_to_escrow(callback_query: types.CallbackQuery):
    offer, user_id, contract_address = await db.search_by_uid(int(callback_query.data.split(":")[1]))

    if offer is None:
        await callback_query.message.answer("Offer not found")
        await callback_query.answer()
        return

    connector = TonConnector.get_connector(callback_query.message.chat.id)
    connected = await connector.restore_connection()
    if not connected:
        await callback_query.message.answer(text='You did not connect any wallet!')
        await callback_query.answer()
        return
    if offer.currency == "Ton":
        message_to_send = transactions.get_deposit_ton_to_contrtact(contract_address, offer)
    else:
        tonapi = AsyncTonapi(api_key=config.tonapi_key)
        user_jetton_wallet = await utils.get_user_jetton_wallet(tonapi, Address(offer.jetton_master), Address(connector.account.address))

        message_to_send = transactions.get_deposit_jetton_to_contrtact(contract_address,
                                                                       Address(connector.account.address),
                                                                       user_jetton_wallet, offer)

    transaction = {
        'valid_until': int(time.time() + 60 * 5),
        'messages': [
            message_to_send
        ]
    }

    await callback_query.message.answer(text='Approve transaction in your wallet app!')
    try:
        await asyncio.wait_for(connector.send_transaction(
            transaction=transaction
        ), 60 * 5)
    except asyncio.TimeoutError:
        await callback_query.message.answer(text='Timeout error!')
        await callback_query.answer()
        return
    except UserRejectsError:
        await callback_query.message.answer(text='You rejected the transaction!')
        await callback_query.answer()
        return
    except Exception as e:
        await callback_query.message.answer(text=f'Unknown error: {e}')
        await callback_query.answer()
        return
    await callback_query.message.answer("Successfull transaction. Admin Will check everything and contact you")
    await callback_query.answer()

@dp.message(CommandStart(deep_link=True))
async def seek_for_offer(message: types.Message, command: CommandObject):
    connector = TonConnector.get_connector(message.chat.id)
    connected = await connector.restore_connection()
    if not connected:
        await message.answer(text='Connect wallet first. You can do that by pressing /start')
        return

    args = command.args
    deep_link = args

    if deep_link:

        offer, user_id, contract_address = await db.search_by_uid(int(deep_link))

        if offer is None:
            await message.answer("Offer not found")
            return

        user = await bot.get_chat(user_id)
        print(user_id, user)
        username = user.username

        await message.answer(
            f"User @{username} wants to make a deal with you. Contract address: {contract_address.to_str()}",
            parse_mode=None
        )

        mk_b = InlineKeyboardBuilder()
        mk_b.add(InlineKeyboardButton(text="Accept", callback_data=f"pay_to_escrow:{deep_link}"))
        jetton_master_str = "" if offer.jetton_master is None else offer.jetton_master

        await message.answer(f"Offer: (price in nanotons/nano Jettons): \n{offer.description} \n {offer.price} nano{offer.currency}\n {jetton_master_str}",
                             reply_markup=mk_b.as_markup())

    else:
        await message.answer("Welcome to Escrow bot! Please, use /start command to start working with bot")


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


form_fields = ['Description (400 characters max.)', 'Price (integer in nanotons/nano jettons) ', 'Currency (Ton or Jetton)',
               "JettonMaster (for Jetton)"]


class FormStates(StatesGroup):
    WAITING_FOR_INPUT = State()


# Функция для создания клавиатуры с текущими значениями полей
def get_form_keyboard(user_data):
    builder = InlineKeyboardBuilder()
    for field in form_fields:
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


@dp.message(Command("create_offer"))
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
        # if offer.currency == "Ton":
        #     offer.recalculate_price_in_nano(9)
        # else:
        #     #info = await tonapi.accounts.get_info(offer.jetton_master)
        #     #if info.status != "active" or "jetton_master" not in info.interfaces:
        #     #    await callback_query.message.answer(f"Invalid jetton_master")
        #     #offer.recalculate_price_in_nano(info.)
        #     #offer.recalculate_price_in_nano(info["metadata"]["decimals"])
    except Exception as e:
        traceback.print_exc()
        await callback_query.message.answer(f"Error in fields {e}")
        return

    try_num = 0
    while True:  #maybe this contract is already taken
        deploy_data = transactions.create_ton_escrow_data(
            (hash(offer) + abs(callback_query.message.from_user.id) + try_num) % 2 ** 64)
        deploy_code = Cell.one_from_boc(config.escrow_code)
        state_init = StateInit(code=deploy_code, data=deploy_data)
        new_contract_address = Address("0:" + state_init.serialize().hash.hex())
        info = await tonapi.accounts.get_info(new_contract_address.to_str())
        if info.status != "active":
            break
        try_num += 1
    connector = TonConnector.get_connector(callback_query.message.chat.id)
    connected = await connector.restore_connection()
    escrow_jetton_wallet = None
    if offer.currency == "Jetton":
        escrow_jetton_wallet = await utils.get_user_jetton_wallet(tonapi, Address(offer.jetton_master), new_contract_address)
    if not connected:
        await callback_query.message.answer(text='You did not connect any wallet!')
        await callback_query.answer()
        return
    else:
        transaction = {
            'valid_until': int(time.time() + 60 * 5),
            'messages': [
                transactions.get_deploy_escrow_message(state_init=state_init, offer=offer, escrow_jetton_wallet=escrow_jetton_wallet)
            ]
        }

        await callback_query.message.answer(text='Approve transaction in your wallet app!')
        try:
            pass
            await asyncio.wait_for(connector.send_transaction(
                transaction=transaction
            ), 60 * 5)
        except asyncio.TimeoutError:
            await callback_query.message.answer(text='Timeout error!')
            await callback_query.answer()
            return
        except UserRejectsError:
            await callback_query.message.answer(text='You rejected the transaction!')
            await callback_query.answer()
            return
        except Exception as e:
            await callback_query.message.answer(text=f'Unknown error: {e}')
            await callback_query.answer()
            return
    await state.set_state(None)
    address = Address("0:" + state_init.serialize().hash.hex())
    unique_id = await db.save_offer(offer, address, callback_query.from_user.id)
    print(f"Your uid {callback_query.from_user.id}")
    await callback_query.message.answer(
        f"Your offer link is \n<code>{await create_start_link(bot, str(unique_id))}</code>\n"
        f"Share it to anyone you want to make a deal :)")

    await callback_query.answer()


@dp.message(Command("disconnect"))
async def disconnect_wallet(message: types.Message):
    connector = TonConnector.get_connector(message.chat.id)
    connected = await connector.restore_connection()
    if not connected:
        await message.answer('You are not connected with any wallet')
        return
    await message.answer('You have been successfully disconnected!')
    await connector.disconnect()


async def main():
    tonapi = AsyncTonapi(api_key=config.tonapi_key)

    # Инициализируем пул соединений
    await db.initialize()
    await bot.delete_webhook(drop_pending_updates=True)  # skip_updates = True
    await dp.start_polling(bot)


if __name__ == "__main__":
    # register query handler
    dp.callback_query.register(pay_to_escrow, lambda c: c.data and c.data.startswith('pay_to_escrow'))
    dp.callback_query.register(deploy_offer, lambda c: c.data and c.data.startswith('deploy'))
    dp.callback_query.register(connect_wallet, lambda c: c.data and c.data.startswith('connect:'))
    dp.callback_query.register(process_callback_button, lambda c: c.data and c.data.startswith('field:'))
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
