import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

pool = None


# =========================
# DATABASE
# =========================

async def init_db():
    global pool

    pool = await asyncpg.create_pool(DATABASE_URL)

    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                thread_id BIGINT NOT NULL
            )
            """
        )


# =========================
# HELPERS
# =========================

async def get_or_create_thread(user):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT thread_id FROM users WHERE user_id = $1",
            user.id
        )

        if row:
            return row["thread_id"]

        topic = await bot.create_forum_topic(
            chat_id=GROUP_ID,
            name=f"{user.full_name} | {user.id}"
        )

        thread_id = topic.message_thread_id

        await conn.execute(
            "INSERT INTO users (user_id, thread_id) VALUES ($1, $2)",
            user.id,
            thread_id
        )

        return thread_id


async def send_to_thread(user, text):
    thread_id = await get_or_create_thread(user)

    await bot.send_message(
        chat_id=GROUP_ID,
        message_thread_id=thread_id,
        text=(
            f"👤 {user.full_name}
"
            f"🆔 {user.id}

"
            f"{text}"
        )
    )


# =========================
# USER MESSAGES
# =========================

@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Здравствуйте! Напишите ваше сообщение."
    )


@dp.message(F.chat.type == ChatType.PRIVATE)
async def private_message_handler(message: Message):
    if not message.text:
        await message.answer("Пока поддерживаются только текстовые сообщения.")
        return

    await send_to_thread(message.from_user, message.text)

    await message.answer(
        "✅ Сообщение отправлено в поддержку."
    )


# =========================
# ADMIN REPLIES
# =========================

@dp.message(F.chat.id == GROUP_ID)
async def admin_reply_handler(message: Message):
    if not message.message_thread_id:
        return

    if not message.reply_to_message:
        return

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT user_id FROM users WHERE thread_id = $1",
            message.message_thread_id
        )

    if not row:
        return

    user_id = row["user_id"]

    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"💬 Ответ поддержки:

{message.text}"
        )
    except Exception as e:
        logging.error(e)


# =========================
# START
# =========================

async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
