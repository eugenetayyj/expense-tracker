from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from telegram import Update
import logging
from main import start_web_bot

app = FastAPI()

# Initialize the Telegram bot
bot_app = None


@app.on_event("startup")
async def startup():
    global bot_app
    try:
        logging.info("Initializing bot...")
        bot_app = await start_web_bot()
        if bot_app is None:
            logging.error("Bot failed to initialize.")
        else:
            logging.info("Bot initialized successfully.")
    except Exception as e:
        logging.error(f"Error during startup: {e}")

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming updates from Telegram."""
    try:
        update_data = await request.json()

        if bot_app is None or bot_app.bot is None:
            logging.error("Bot is not initialized!")
            raise HTTPException(status_code=500, detail="Bot is not initialized!")

        update = Update.de_json(update_data, bot_app.bot)

        # Process the update asynchronously
        background_tasks.add_task(bot_app.process_update, update)
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "running"}