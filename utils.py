from pytonapi import AsyncTonapi
from pytoniq_core import Cell, Slice, Address


async def parse_stack(stack: list):
    ton_stack = []
    for el in stack:
        if el["type"] == "num":
            ton_stack.append(int(el["num"]))
        elif el["type"] == "cell":
            ton_stack.append(Cell.one_from_boc(el["cell"]))
        else:
            raise ValueError(f"Unknown type while stack parsing: {el['type']}")


async def run_get_method(tonapi: AsyncTonapi, account_id: str, method_id: str, args: list) -> list[int | Cell]:

    get_method = f"v2/accounts/{account_id}/methods/{method_id}"
    response = await tonapi._get(method=get_method, params={"args": args})
    if not response.get("success", 1):
        stack = response.get("stack", [])
        stack = await parse_stack(stack)
        return stack


async def get_user_jetton_wallet(tonapi: AsyncTonapi, jetton_master: Address, user_adress: Address):
    responce = await tonapi.blockchain.execute_get_method(jetton_master.to_str().strip(), "get_wallet_address",
                                                          user_adress.to_str())
    if not responce.success:
        return None

    user_jetton_wallet = Cell.one_from_boc(responce.stack[0].cell).begin_parse().load_address()
    return user_jetton_wallet
