import io
import logging
import asyncio
import traceback
import html
import json
from datetime import datetime
import openai

import telegram
from telegram import (
    Update,
    User,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    AIORateLimiter,
    filters,
)
from telegram.constants import ParseMode, ChatAction

import config
import database
import openai_utils

print(config.allowed_telegram_usernames)
import base64
from analyze_func import analyze_trader

# setup
db = database.Database()
logger = logging.getLogger(__name__)
user_semaphores = {}
user_tasks = {}


HELP_MESSAGE = """Commands:
⚪ /retry – Regenerate last bot answer
⚪ /new – Start new dialog
⚪ /mode – Select chat mode
⚪ /strategy – Select strategy
⚪ /settings – Show settings
⚪ /help – Show help


"""


def split_text_into_chunks(text, chunk_size):
    for i in range(0, len(text), chunk_size):
        yield text[i : i + chunk_size]


async def start_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id

    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.start_new_dialog(user_id)

    reply_text = "Hi! I'm <b>ChatGPT</b> bot implemented with OpenAI API 🤖\n\n"
    reply_text += HELP_MESSAGE

    await update.message.reply_text(reply_text, parse_mode=ParseMode.HTML)
    await show_chat_modes_handle(update, context)


async def show_chat_modes_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
        return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_chat_mode_menu(0)
    await update.message.reply_text(
        text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
    )


async def show_chat_strategy_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
        return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_chat_strategy_menu(0)
    await update.message.reply_text(
        text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
    )


def get_chat_mode_menu(page_index: int):
    n_chat_modes_per_page = config.n_chat_modes_per_page
    text = f"Select <b>chat mode</b> ({len(config.chat_modes)} modes available):"

    # buttons
    chat_mode_keys = list(config.chat_modes.keys())
    page_chat_mode_keys = chat_mode_keys[
        page_index * n_chat_modes_per_page : (page_index + 1) * n_chat_modes_per_page
    ]

    keyboard = []
    for chat_mode_key in page_chat_mode_keys:
        name = config.chat_modes[chat_mode_key]["name"]
        keyboard.append(
            [InlineKeyboardButton(name, callback_data=f"set_chat_mode|{chat_mode_key}")]
        )

    # pagination
    if len(chat_mode_keys) > n_chat_modes_per_page:
        is_first_page = page_index == 0
        is_last_page = (page_index + 1) * n_chat_modes_per_page >= len(chat_mode_keys)

        if is_first_page:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "»", callback_data=f"show_chat_modes|{page_index + 1}"
                    )
                ]
            )
        elif is_last_page:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "«", callback_data=f"show_chat_modes|{page_index - 1}"
                    ),
                ]
            )
        else:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "«", callback_data=f"show_chat_modes|{page_index - 1}"
                    ),
                    InlineKeyboardButton(
                        "»", callback_data=f"show_chat_modes|{page_index + 1}"
                    ),
                ]
            )

    reply_markup = InlineKeyboardMarkup(keyboard)

    return text, reply_markup


def get_chat_strategy_menu(page_index: int):
    n_strategy_per_page = config.n_strategy_per_page
    text = f"Select <b>strategy </b> ({len(config.strategy)} you want):"

    # buttons
    strategy_keys = list(config.strategy.keys())
    page_strategy_keys = strategy_keys[
        page_index * n_strategy_per_page : (page_index + 1) * n_strategy_per_page
    ]

    keyboard = []
    for strategy_key in page_strategy_keys:
        name = config.strategy[strategy_key]["name"]
        keyboard.append(
            [InlineKeyboardButton(name, callback_data=f"set_strategy|{strategy_key}")]
        )

    # pagination
    if len(strategy_keys) > n_strategy_per_page:
        is_first_page = page_index == 0
        is_last_page = (page_index + 1) * n_strategy_per_page >= len(strategy_keys)

        if is_first_page:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "»", callback_data=f"show_strategy|{page_index + 1}"
                    )
                ]
            )
        elif is_last_page:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "«", callback_data=f"show_strategy|{page_index - 1}"
                    ),
                ]
            )
        else:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "«", callback_data=f"show_strategy|{page_index - 1}"
                    ),
                    InlineKeyboardButton(
                        "»", callback_data=f"show_strategy|{page_index + 1}"
                    ),
                ]
            )

    reply_markup = InlineKeyboardMarkup(keyboard)

    return text, reply_markup


async def is_previous_message_not_answered_yet(
    update: Update, context: CallbackContext
):
    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id
    if user_semaphores[user_id].locked():
        text = "⏳ Please <b>wait</b> for a reply to the previous message\n"
        text += "Or you can /cancel it"
        await update.message.reply_text(
            text, reply_to_message_id=update.message.id, parse_mode=ParseMode.HTML
        )
        return True
    else:
        return False


async def help_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    await update.message.reply_text(HELP_MESSAGE, parse_mode=ParseMode.HTML)


async def register_user_if_not_exists(
    update: Update, context: CallbackContext, user: User
):
    if not db.check_if_user_exists(user.id):
        db.add_new_user(
            user.id,
            update.message.chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        db.start_new_dialog(user.id)

    if db.get_user_attribute(user.id, "current_dialog_id") is None:
        db.start_new_dialog(user.id)

    if user.id not in user_semaphores:
        user_semaphores[user.id] = asyncio.Semaphore(1)

    if db.get_user_attribute(user.id, "current_model") is None:
        db.set_user_attribute(
            user.id, "current_model", config.models["available_text_models"][0]
        )

    # back compatibility for n_used_tokens field
    n_used_tokens = db.get_user_attribute(user.id, "n_used_tokens")
    if isinstance(n_used_tokens, int) or isinstance(n_used_tokens, float):  # old format
        new_n_used_tokens = {
            "gpt-4o-mini": {"n_input_tokens": 0, "n_output_tokens": n_used_tokens}
        }
        db.set_user_attribute(user.id, "n_used_tokens", new_n_used_tokens)

    # # voice message transcription
    # if db.get_user_attribute(user.id, "n_transcribed_seconds") is None:
    #     db.set_user_attribute(user.id, "n_transcribed_seconds", 0.0)

    # # image generation
    # if db.get_user_attribute(user.id, "n_generated_images") is None:
    #     db.set_user_attribute(user.id, "n_generated_images", 0)


async def retry_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
        return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
    if len(dialog_messages) == 0:
        await update.message.reply_text("No message to retry 🤷‍♂️")
        return

    last_dialog_message = dialog_messages.pop()
    db.set_dialog_messages(
        user_id, dialog_messages, dialog_id=None
    )  # last message was removed from the context

    await message_handle(
        update,
        context,
        message=last_dialog_message["user"],
        use_new_dialog_timeout=False,
    )


async def message_handle(
    update: Update, context: CallbackContext, message=None, use_new_dialog_timeout=True
):
    # check if bot was mentioned (for group chats)
    # if not await is_bot_mentioned(update, context):
    #     return

    # check if message is edited
    # if update.edited_message is not None:
    #     await edited_message_handle(update, context)
    #     return

    _message = message or update.message.text

    # remove bot mention (in group chats)
    if update.message.chat.type != "private":
        _message = _message.replace("@" + context.bot.username, "").strip()

    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
        return

    user_id = update.message.from_user.id
    chat_mode = db.get_user_attribute(user_id, "current_chat_mode")

    # if chat_mode == "artist":
    #     await generate_image_handle(update, context, message=message)
    #     return

    current_model = db.get_user_attribute(user_id, "current_model")

    async def message_handle_fn():
        # new dialog timeout
        if use_new_dialog_timeout:
            if (
                datetime.now() - db.get_user_attribute(user_id, "last_interaction")
            ).seconds > config.new_dialog_timeout and len(
                db.get_dialog_messages(user_id)
            ) > 0:
                db.start_new_dialog(user_id)
                await update.message.reply_text(
                    f"Starting new dialog due to timeout (<b>{config.chat_modes[chat_mode]['name']}</b> mode) ✅",
                    parse_mode=ParseMode.HTML,
                )
        db.set_user_attribute(user_id, "last_interaction", datetime.now())

        # in case of CancelledError
        n_input_tokens, n_output_tokens = 0, 0

        try:
            # send placeholder message to user
            placeholder_message = await update.message.reply_text("...")

            # send typing action
            await update.message.chat.send_action(action="typing")

            if _message is None or len(_message) == 0:
                await update.message.reply_text(
                    "🥲 You sent <b>empty message</b>. Please, try again!",
                    parse_mode=ParseMode.HTML,
                )
                return

            dialog_messages = db.get_dialog_messages(user_id, dialog_id=None)
            parse_mode = {"html": ParseMode.HTML, "markdown": ParseMode.MARKDOWN}[
                config.chat_modes[chat_mode]["parse_mode"]
            ]

            chatgpt_instance = openai_utils.ChatGPT(model=current_model)
            if config.enable_message_streaming:
                gen = chatgpt_instance.send_message_stream(
                    _message, dialog_messages=dialog_messages, chat_mode=chat_mode
                )
            else:
                (
                    answer,
                    (n_input_tokens, n_output_tokens),
                    n_first_dialog_messages_removed,
                ) = await chatgpt_instance.send_message(
                    _message, dialog_messages=dialog_messages, chat_mode=chat_mode
                )

                async def fake_gen():
                    yield "finished", answer, (
                        n_input_tokens,
                        n_output_tokens,
                    ), n_first_dialog_messages_removed

                gen = fake_gen()

            prev_answer = ""

            async for gen_item in gen:
                (
                    status,
                    answer,
                    (n_input_tokens, n_output_tokens),
                    n_first_dialog_messages_removed,
                ) = gen_item

                answer = answer[:4096]  # telegram message limit

                # update only when 100 new symbols are ready
                if abs(len(answer) - len(prev_answer)) < 100 and status != "finished":
                    continue

                try:
                    await context.bot.edit_message_text(
                        answer,
                        chat_id=placeholder_message.chat_id,
                        message_id=placeholder_message.message_id,
                        parse_mode=parse_mode,
                    )
                except telegram.error.BadRequest as e:
                    if str(e).startswith("Message is not modified"):
                        continue
                    else:
                        await context.bot.edit_message_text(
                            answer,
                            chat_id=placeholder_message.chat_id,
                            message_id=placeholder_message.message_id,
                        )

                await asyncio.sleep(0.01)  # wait a bit to avoid flooding

                prev_answer = answer

            # update user data
            new_dialog_message = {
                "user": [{"type": "text", "text": _message}],
                "bot": answer,
                "date": datetime.now(),
            }

            db.set_dialog_messages(
                user_id,
                db.get_dialog_messages(user_id, dialog_id=None) + [new_dialog_message],
                dialog_id=None,
            )

            db.update_n_used_tokens(
                user_id, current_model, n_input_tokens, n_output_tokens
            )

        except asyncio.CancelledError:
            # note: intermediate token updates only work when enable_message_streaming=True (config.yml)
            db.update_n_used_tokens(
                user_id, current_model, n_input_tokens, n_output_tokens
            )
            raise

        except Exception as e:
            error_text = f"Something went wrong during completion. Reason: {e}"
            logger.error(error_text)
            await update.message.reply_text(error_text)
            return

        # send message if some messages were removed from the context
        if n_first_dialog_messages_removed > 0:
            if n_first_dialog_messages_removed == 1:
                text = "✍️ <i>Note:</i> Your current dialog is too long, so your <b>first message</b> was removed from the context.\n Send /new command to start new dialog"
            else:
                text = f"✍️ <i>Note:</i> Your current dialog is too long, so <b>{n_first_dialog_messages_removed} first messages</b> were removed from the context.\n Send /new command to start new dialog"
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async with user_semaphores[user_id]:
        # if current_model == "gpt-4-vision-preview" or current_model == "gpt-4o" or update.message.photo is not None and len(update.message.photo) > 0:

        #     logger.error(current_model)
        #     # What is this? ^^^

        #     if current_model != "gpt-4o" and current_model != "gpt-4-vision-preview":
        #         current_model = "gpt-4o"
        #         db.set_user_attribute(user_id, "current_model", "gpt-4o")
        #     task = asyncio.create_task(
        #         _vision_message_handle_fn(update, context, use_new_dialog_timeout=use_new_dialog_timeout)
        #     )
        # else:
        task = asyncio.create_task(message_handle_fn())

        user_tasks[user_id] = task

        try:
            await task
        except asyncio.CancelledError:
            await update.message.reply_text("✅ Canceled", parse_mode=ParseMode.HTML)
        else:
            pass
        finally:
            if user_id in user_tasks:
                del user_tasks[user_id]


async def new_dialog_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
        return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())
    db.set_user_attribute(user_id, "current_model", "gpt-4o-mini")

    db.start_new_dialog(user_id)
    await update.message.reply_text("Starting new dialog ✅")

    chat_mode = db.get_user_attribute(user_id, "current_chat_mode")
    await update.message.reply_text(
        f"{config.chat_modes[chat_mode]['welcome_message']}", parse_mode=ParseMode.HTML
    )


async def cancel_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    if user_id in user_tasks:
        task = user_tasks[user_id]
        task.cancel()
    else:
        await update.message.reply_text(
            "<i>Nothing to cancel...</i>", parse_mode=ParseMode.HTML
        )


async def set_chat_mode_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(
        update.callback_query, context, update.callback_query.from_user
    )
    user_id = update.callback_query.from_user.id

    query = update.callback_query
    await query.answer()

    chat_mode = query.data.split("|")[1]

    db.set_user_attribute(user_id, "current_chat_mode", chat_mode)
    db.start_new_dialog(user_id)

    await context.bot.send_message(
        update.callback_query.message.chat.id,
        f"{config.chat_modes[chat_mode]['welcome_message']}",
        parse_mode=ParseMode.HTML,
    )


async def set_strategy_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(
        update.callback_query, context, update.callback_query.from_user
    )
    user_id = update.callback_query.from_user.id

    query = update.callback_query
    await query.answer()

    strategy = query.data.split("|")[1]

    if strategy == "day_trading":
        list_traders = db.get_day_trading()
    elif strategy == "scalping":
        list_traders = db.get_scalping()
    html_links = [
        f'<a href="https://app.copin.io/trader/{doc["account"]}">{doc["account"]}</a>'
        for doc in list_traders
    ]

    reply_text = "Here is top 10 traders in this strategy: 🤖\n\n"
    for trader in html_links:
        reply_text += f"Account: {trader}\n\n"
    reply_text = reply_text[:4096]  # telegram message limit
    db.start_new_dialog(user_id)
    await context.bot.send_message(
        update.callback_query.message.chat.id,
        reply_text,
        parse_mode=ParseMode.HTML,
    )

    # db.set_user_attribute(user_id, "current_chat_mode", chat_mode)
    # db.start_new_dialog(user_id)

    # await context.bot.send_message(
    #     update.callback_query.message.chat.id,
    #     f"{config.chat_modes[chat_mode]['welcome_message']}",
    #     parse_mode=ParseMode.HTML,
    # )


def get_settings_menu(user_id: int):
    current_model = db.get_user_attribute(user_id, "current_model")
    text = config.models["info"][current_model]["description"]

    text += "\n\n"
    score_dict = config.models["info"][current_model]["scores"]
    for score_key, score_value in score_dict.items():
        text += "🟢" * score_value + "⚪️" * (5 - score_value) + f" – {score_key}\n\n"

    text += "\nSelect <b>model</b>:"

    # buttons to choose models
    buttons = []
    for model_key in config.models["available_text_models"]:
        title = config.models["info"][model_key]["name"]
        if model_key == current_model:
            title = "✅ " + title

        buttons.append(
            InlineKeyboardButton(title, callback_data=f"set_settings|{model_key}")
        )
    reply_markup = InlineKeyboardMarkup([buttons])

    return text, reply_markup


async def settings_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    if await is_previous_message_not_answered_yet(update, context):
        return

    user_id = update.message.from_user.id
    db.set_user_attribute(user_id, "last_interaction", datetime.now())

    text, reply_markup = get_settings_menu(user_id)
    await update.message.reply_text(
        text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
    )


async def set_settings_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(
        update.callback_query, context, update.callback_query.from_user
    )
    user_id = update.callback_query.from_user.id

    query = update.callback_query
    await query.answer()

    _, model_key = query.data.split("|")
    db.set_user_attribute(user_id, "current_model", model_key)
    db.start_new_dialog(user_id)

    text, reply_markup = get_settings_menu(user_id)
    try:
        await query.edit_message_text(
            text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
        )
    except telegram.error.BadRequest as e:
        if str(e).startswith("Message is not modified"):
            pass


# async def error_handle(update: Update, context: CallbackContext) -> None:
#     logger.error(msg="Exception while handling an update:", exc_info=context.error)

#     try:
#         # collect error message
#         tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
#         tb_string = "".join(tb_list)
#         update_str = update.to_dict() if isinstance(update, Update) else str(update)
#         message = (
#             f"An exception was raised while handling an update\n"
#             f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
#             "</pre>\n\n"
#             f"<pre>{html.escape(tb_string)}</pre>"
#         )

#         # split text into multiple messages due to 4096 character limit
#         for message_chunk in split_text_into_chunks(message, 4096):
#             try:
#                 await context.bot.send_message(update.effective_chat.id, message_chunk, parse_mode=ParseMode.HTML)
#             except telegram.error.BadRequest:
#                 # answer has invalid characters, so we send it without parse_mode
#                 await context.bot.send_message(update.effective_chat.id, message_chunk)
#     except:
#         await context.bot.send_message(update.effective_chat.id, "Some error in error handler")


async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            BotCommand("/new", "Start new dialog"),
            BotCommand("/mode", "Select chat mode"),
            BotCommand("/strategy", "Show some trader's strategy"),
            BotCommand("/retry", "Re-generate response for previous query"),
            BotCommand("/settings", "Show settings"),
            BotCommand("/help", "Show help message"),
        ]
    )


def run_bot() -> None:
    application = (
        ApplicationBuilder()
        .token(config.telegram_token)
        .concurrent_updates(True)
        .rate_limiter(AIORateLimiter(max_retries=5))
        .http_version("1.1")
        .get_updates_http_version("1.1")
        .post_init(post_init)
        .build()
    )

    # add handlers
    user_filter = filters.ALL
    if len(config.allowed_telegram_usernames) > 0:
        usernames = [x for x in config.allowed_telegram_usernames if isinstance(x, str)]
        any_ids = [x for x in config.allowed_telegram_usernames if isinstance(x, int)]
        user_ids = [x for x in any_ids if x > 0]
        group_ids = [x for x in any_ids if x < 0]
        user_filter = (
            filters.User(username=usernames)
            | filters.User(user_id=user_ids)
            | filters.Chat(chat_id=group_ids)
        )

    application.add_handler(CommandHandler("start", start_handle, filters=user_filter))
    application.add_handler(CommandHandler("help", help_handle, filters=user_filter))
    # application.add_handler(CommandHandler("help_group_chat", help_group_chat_handle, filters=user_filter))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & user_filter, message_handle)
    )
    application.add_handler(
        MessageHandler(filters.PHOTO & ~filters.COMMAND & user_filter, message_handle)
    )
    # application.add_handler(MessageHandler(filters.VIDEO & ~filters.COMMAND & user_filter, unsupport_message_handle))
    # application.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND & user_filter, unsupport_message_handle))
    application.add_handler(CommandHandler("retry", retry_handle, filters=user_filter))
    application.add_handler(
        CommandHandler("new", new_dialog_handle, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("cancel", cancel_handle, filters=user_filter)
    )

    # application.add_handler(MessageHandler(filters.VOICE & user_filter, voice_message_handle))

    application.add_handler(
        CommandHandler("mode", show_chat_modes_handle, filters=user_filter)
    )
    application.add_handler(
        CommandHandler("strategy", show_chat_strategy_handle, filters=user_filter)
    )
    # application.add_handler(CallbackQueryHandler(show_chat_modes_callback_handle, pattern="^show_chat_modes"))
    application.add_handler(
        CallbackQueryHandler(set_chat_mode_handle, pattern="^set_chat_mode")
    )
    application.add_handler(
        CallbackQueryHandler(set_strategy_handle, pattern="^set_strategy")
    )
    application.add_handler(
        CommandHandler("settings", settings_handle, filters=user_filter)
    )
    application.add_handler(
        CallbackQueryHandler(set_settings_handle, pattern="^set_settings")
    )

    # application.add_handler(CommandHandler("balance", show_balance_handle, filters=user_filter))

    # application.add_error_handler(error_handle)

    # start the bot
    application.run_polling()


if __name__ == "__main__":
    run_bot()
