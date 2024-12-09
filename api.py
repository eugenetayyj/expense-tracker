from fastapi import FastAPI, Request, BackgroundTasks
from telegram import Update
import logging
import asyncio
from main import start_bot

app = FastAPI()

# Initialize the Telegram bot
bot_app = None


@app.on_event("startup")
async def startup():
    global bot_app
    try:
        bot_app = await start_bot()
        if bot_app is None:
            raise RuntimeError("Bot failed to initialize.")
        logging.info("Bot started successfully.")
    except Exception as e:
        logging.error(f"Startup error: {e}")
        raise
@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming updates from Telegram."""
    update_data = await request.json()
    update = Update.de_json(update_data, bot_app.bot)
    background_tasks.add_task(bot_app.process_update, update)
    return {"status": "ok"}


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "running"}