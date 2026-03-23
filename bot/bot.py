from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from telegram.constants import ParseMode, ChatAction
import logging
from deepSeekAgent import main as deepseek_response

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "TOKEN"


async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("Как это работает?", callback_data='help')],
        [InlineKeyboardButton("Пример запроса", callback_data='example')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"📖 <b>Привет, {update.effective_user.first_name}!</b>\n\n"
        "Я твой персональный книжный ассистент!\n\n"
        "• Проанализирую твои предпочтения\n"
        "• Подберу неочевидные рекомендации\n"
        "• Учту стиль и тематику\n"
        "• Предложу разные жанры\n\n"
        "Просто напиши мне авторов или книги, которые тебе нравятся!"
    )
    await update.message.reply_text(welcome_text,
                                    parse_mode=ParseMode.HTML,
                                    reply_markup=reply_markup)


async def handle_help(update: Update, context: CallbackContext):
    help_text = (
        "🛠 <b>Как работать с ботом:</b>\n\n"
        "1. Отправь список любимых книг/авторов\n"
        "2. Подожди 10-15 секунд пока ищу рекомендации\n"
        "3. Получи персональную подборку\n\n"
        "Примеры запросов:\n"
        "• Люблю Харуки Мураками и антиутопии\n"
        "• Нравятся детективы Агаты Кристи\n"
        "• Посоветуй что-то похожее на 'Мастера и Маргариту'"
    )
    keyboard = [
        [InlineKeyboardButton("Как это работает?", callback_data='help')],
        [InlineKeyboardButton("Пример запроса", callback_data='example')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.message.edit_text(help_text,
                                                  parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def handle_example(update: Update, context: CallbackContext):
    example_text = (
        "📝 <b>Пример запроса:</b>\n\n"
        "<i>«Мне нравятся:\n"
        "- Харуки Мураками\n"
        "- Рэй Брэдбери\n"
        "- Сергей Лукьяненко\n"
        "- Книги о космических путешествиях»</i>"
    )
    keyboard = [
        [InlineKeyboardButton("Как это работает?", callback_data='help')],
        [InlineKeyboardButton("Пример запроса", callback_data='example')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.message.edit_text(example_text,
                                                  parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def handle_books(update: Update, context: CallbackContext) -> None:
    try:
        user_input = update.message.text

        if len(user_input) < 4:
            await update.message.reply_text(
                "✏️ Пожалуйста, напиши немного подробнее о своих предпочтениях (хотя бы 2 книги или автора)")
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )
        await update.message.reply_text(
            "🔍 <b>Анализирую твои предпочтения...</b>\n"
            "⏳ Примерное время ожидания: 10-20 секунд\n\n"
            "<i>Пока я ищу, можешь вспомнить последнюю книгу, которая тебя впечатлила</i> 📖",
            parse_mode=ParseMode.HTML
        )

        response = deepseek_response(user_input)

        if not response:
            raise Exception("API Error")

        # Форматирование ответа
        formatted_response = format_recommendations(response)

        keyboard = [
            [InlineKeyboardButton("Как это работает?", callback_data='help')],
            [InlineKeyboardButton("Пример запроса", callback_data='example')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"📚 <b>Вот твоя персональная подборка:</b>\n\n{formatted_response}",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        error_text = (
            "⚠️ <b>Что-то пошло не так</b>\n\n"
            "Попробуй:\n"
            "1. Проверить интернет-соединение\n"
            "2. Сформулировать запрос иначе\n"
            "3. Повторить попытку через минуту"
        )
        await update.message.reply_text(error_text, parse_mode=ParseMode.HTML)


def format_recommendations(text: str) -> str:
    lines = text.split('\n')
    formatted = []
    for i, line in enumerate(lines, 1):
        if '—' in line:
            author, title = line.split('—', 1)
            formatted.append(f"<b>{author.strip()}</b> — {title.strip()}")
        else:
            formatted.append(f"{line.strip()}")

    formatted_text = '\n'.join(formatted)
    formatted_text = formatted_text.replace("*", "")
    return formatted_text


async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == 'help':
        await handle_help(update, context)
    elif query.data == 'example':
        await handle_example(update, context)


def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_books))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()


if __name__ == "__main__":
    main()
