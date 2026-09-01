#!/usr/bin/env python3
import os
import shlex
import subprocess
import logging

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

# --- Configuración ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PON_AQUI_TU_TOKEN")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 0))
COMMAND_TIMEOUT = 30  # segundos
MAX_MSG_LEN = 4000  # límite de Telegram es 4096, dejamos margen

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("shell_bot")


def is_authorized(update: Update) -> bool:
    return update.effective_user is not None and update.effective_user.id == ALLOWED_USER_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "Bot activo. Envíame cualquier mensaje y lo ejecutaré como comando en la terminal."
    )


async def run_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        log.warning("Intento de acceso no autorizado de user_id=%s", update.effective_user.id)
        return

    command = update.message.text.strip()
    if not command:
        return

    await update.message.chat.send_action("typing")

    try:
        result = subprocess.run(
            "ia " + command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            cwd=os.path.expanduser("~"),
        )
        output = (result.stdout or "") + (result.stderr or "")
        if not output.strip():
            output = f"(sin salida, código de salida: {result.returncode})"
    except subprocess.TimeoutExpired:
        output = f"⏱ El comando superó el tiempo límite de {COMMAND_TIMEOUT}s."
    except Exception as e:
        output = f"⚠️ Error al ejecutar el comando: {e}"

    # Telegram limita la longitud de los mensajes; se divide en trozos si hace falta
    for i in range(0, len(output), MAX_MSG_LEN):
        chunk = output[i:i + MAX_MSG_LEN]
        await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="MarkdownV2_disabled" if False else None)


def main():
    if BOT_TOKEN == "PON_AQUI_TU_TOKEN" or ALLOWED_USER_ID == 0:
        raise SystemExit(
            "Configura TELEGRAM_BOT_TOKEN y TELEGRAM_ALLOWED_USER_ID "
            "(como variables de entorno o directamente en el script) antes de ejecutar."
        )

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, run_command))

    log.info("Bot iniciado. Esperando comandos...")
    app.run_polling()


if __name__ == "__main__":
    main()