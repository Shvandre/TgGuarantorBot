from models import Offer
from pytoniq_core import Address


#We will use postgresql to store Offers and Escrows. We will use asyncpg library to work with postgresql.
class DatabaseHandler:
    def __init__(self):
        self.pool = None
        # Create offers table if it doesn't exist
        self.create_table = """
        CREATE TABLE IF NOT EXISTS offers (
            id SERIAL PRIMARY KEY,
            user_id INT,
            str_address TEXT,
            description TEXT,
            price INT,
            currency TEXT,
            jetton_master TEXT
        );
        """

    async def create_table_if_not_exists(self):
        async with self.pool.acquire() as connection:
            await connection.execute(self.create_table)

    async def save_offer(self, offer: Offer, offer_addres: Address, user_id: int):
        str_address = offer_addres.to_str(is_user_friendly=False)
        await self.create_table_if_not_exists()
        async with self.pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO offers (user_id, str_address, description, price, currency, jetton_master) VALUES ($1, $2, $3, $4 $5, $6)",
                user_id, str_address, offer.description, offer.price, offer.currency, offer.jetton_master
            )

    async def search_offer(self, user_id: int, contract_address: Address):
        str_address = contract_address.to_str(is_user_friendly=False)
        await self.create_table_if_not_exists()
        async with self.pool.acquire() as connection:
            #create Offer from row in database
            row = await connection.fetchrow(
                "SELECT * FROM offers WHERE user_id = $1 AND str_address = $2",
                user_id, str_address
            )
            # return None if there is no such offer
            if row is None:
                return None
            offer = Offer(description=row['description'], price=row['price'], currency=row['currency'],
                          jetton_master=row['jetton_master'])
            return offer
