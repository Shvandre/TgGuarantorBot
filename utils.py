from pytonapi import AsyncTonapi
from pytoniq_core import Cell, Slice


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
