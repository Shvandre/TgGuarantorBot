from typing import Optional, Tuple

import asyncpg
from models import Offer
from pytoniq_core import Address  # Убедитесь, что модуль правильно назван
import logging

# Настройка логирования (опционально)
logging.basicConfig(level=logging.INFO)


class DatabaseHandler:
    def __init__(self, dsn: str):
        """
        Инициализирует DatabaseHandler с DSN для подключения к PostgreSQL.

        :param dsn: Строка подключения к базе данных PostgreSQL.
        """
        self.pool = None
        self.dsn = dsn
        self.create_table_query = """
        CREATE TABLE IF NOT EXISTS offers (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            str_address TEXT,
            description TEXT,
            price BIGINT,
            currency TEXT,
            jetton_master TEXT
        );
        """

    async def initialize(self):
        """
        Инициализирует пул соединений и создаёт таблицу, если она не существует.
        """
        try:
            self.pool = await asyncpg.create_pool(dsn=self.dsn)
            async with self.pool.acquire() as connection:
                await connection.execute(self.create_table_query)
            logging.info("Пул соединений успешно инициализирован и таблица создана (если отсутствовала).")
        except Exception as e:
            logging.error(f"Ошибка при инициализации пула соединений: {e}")
            raise

    async def close(self):
        """
        Закрывает пул соединений.
        """
        if self.pool:
            await self.pool.close()
            logging.info("Пул соединений закрыт.")

    async def save_offer(self, offer: Offer, offer_address: Address, user_id: int) -> int:
        """
        Сохраняет предложение в базе данных.

        :param offer: Объект Offer.
        :param offer_address: Объект Address.
        :param user_id: ID пользователя.
        :return: ID сохранённого предложения.
        """
        if not self.pool:
            raise RuntimeError("Пул соединений не инициализирован. Вызовите метод `initialize` перед использованием.")

        str_address = offer_address.to_str(is_user_friendly=False)
        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    """
                    INSERT INTO offers (user_id, str_address, description, price, currency, jetton_master)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                    """,
                    user_id, str_address, offer.description, offer.price, offer.currency, offer.jetton_master
                )
                return row['id']
        except Exception as e:
            logging.error(f"Ошибка при сохранении предложения: {e}")
            raise

    async def search_by_uid(self, uid: int) -> Tuple[Offer, int, Address]:
        """
        Ищет предложение по ID.

        :param uid: ID предложения.
        :return: Кортеж (Offer, user_id, Address) или None.
        """
        if not self.pool:
            raise RuntimeError("Пул соединений не инициализирован. Вызовите метод `initialize` перед использованием.")

        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    "SELECT * FROM offers WHERE id = $1",
                    uid
                )
                if row is None:
                    return None
                offer = Offer(
                    description=row['description'],
                    price=row['price'],
                    currency=row['currency'],
                    jetton_master=row['jetton_master']
                )
                return offer, row["user_id"], Address(row["str_address"])
        except Exception as e:
            logging.error(f"Ошибка при поиске предложения по ID: {e}")
            raise

    async def search_offer(self, user_id: int, contract_address: Address):
        """
        Ищет предложение по user_id и адресу контракта.

        :param user_id: ID пользователя.
        :param contract_address: Объект Address.
        :return: Объект Offer или None.
        """
        if not self.pool:
            raise RuntimeError("Пул соединений не инициализирован. Вызовите метод `initialize` перед использованием.")

        str_address = contract_address.to_str(is_user_friendly=False)
        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    """
                    SELECT * FROM offers WHERE user_id = $1 AND str_address = $2
                    """,
                    user_id, str_address
                )
                if row is None:
                    return None
                offer = Offer(
                    description=row['description'],
                    price=row['price'],
                    currency=row['currency'],
                    jetton_master=row['jetton_master']
                )
                return offer
        except Exception as e:
            logging.error(f"Ошибка при поиске предложения: {e}")
            raise