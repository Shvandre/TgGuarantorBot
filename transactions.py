from pytoniq_core import begin_cell, Cell, Address, StateInit
from base64 import urlsafe_b64encode
import config

from models import Offer
from opcodes import Opcodes


def toNano(value: float) -> int:
    return int(value * 10 ** 9)


def create_ton_escrow_data(contract_id: int) -> Cell:
    return (begin_cell()
            .store_uint(0, 1)
            .store_uint(0, 2)
            .store_coins(0)
            .store_address(Address(config.admin_address))
            .store_uint(0, 2)
            .store_uint(0, 1)
            .store_uint(contract_id, 64)
            .store_ref(begin_cell()
                       .store_uint(0, 2)
                       .end_cell())
            .end_cell())


def get_deposit_ton_to_contrtact(contract_address: Address, offer: Offer) -> dict:
    payload_cell = (begin_cell().store_uint(Opcodes.deposit_ton, 32).store_uint(0, 64).end_cell())
    data = {
        'address': contract_address.to_str(is_user_friendly=False),
        'amount': offer.price,
        'payload': urlsafe_b64encode(payload_cell.to_boc()).decode()
    }
    return data


def get_deposit_jetton_to_contrtact(contract_address: Address, user_address: Address, user_jetton_wallet: Address,
                                    offer: Offer) -> dict:
    payload_cell = (begin_cell()
                    .store_uint(Opcodes.jetton_trasfer, 32)
                    .store_uint(0, 64)
                    .store_coins(offer.price)
                    .store_address(contract_address)
                    .store_address(user_address)
                    .store_uint(0, 1)
                    .store_coins(1)
                    .store_uint(0, 1)
                    .end_cell())
    data = {
        'address': user_jetton_wallet.to_str(is_user_friendly=False),
        'amount': toNano(0.1),
        'payload': urlsafe_b64encode(payload_cell.to_boc()).decode()
    }
    return data

def get_deploy_escrow_message(state_init: StateInit, offer: Offer) -> dict:
    if offer.currency == "Jetton":

        payload_cell = (begin_cell()
                        .store_uint(Opcodes.init_jetton_escrow, 32)
                        .store_uint(0, 64)
                        .store_address("") #TODO fix this. Here must me user's jetton_wallet
                        .store_coins(offer.price)
                        .end_cell())
    else:
        payload_cell = (begin_cell()
                        .store_uint(Opcodes.init_ton_escrow, 32)
                        .store_uint(0, 64)
                        .store_coins(offer.price)
                        .end_cell())
    data = {
        'address': Address("0:" + state_init.serialize().hash.hex()).to_str(is_user_friendly=False),
        'stateInit': urlsafe_b64encode(state_init.serialize().to_boc()).decode(),
        'amount': toNano(1.2),
        'payload': urlsafe_b64encode(payload_cell.to_boc()).decode()  # convert it to boc  # encode it to urlsafe base64
    }

    return data
