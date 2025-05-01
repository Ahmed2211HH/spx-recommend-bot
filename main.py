import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters

# Constants (provided in the prompt)
TOKEN = '7737113763:AAF2XR_qUMIFwbMUz37imbJZP22wYh4ulDQ'
OWNER_ID = 7123756100
CHANNEL_ID_VIP = -1002529600259

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for ConversationHandler
SELECT_TICKER, SELECT_TYPE, SELECT_EXPIRY, INPUT_STRIKE, INPUT_THRESHOLD, CONFIRM = range(6)

# Global variables for monitoring
monitor_job = None         # Job for the price monitoring
monitor_active = False     # Flag to indicate an active monitor
play = None                # Playwright instance
browser = None             # Browser instance
page = None                # Page instance

# Utility: keep_alive function to keep bot running on Render
def keep_alive():
    import threading, http.server, socketserver
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"Bot is alive!")
    server = socketserver.TCPServer(('', 8080), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

async def start_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Command handler to start the monitoring setup conversation (owner only)."""
    global monitor_active
    # Only allow if from owner in private chat
    if update.effective_user.id != OWNER_ID or update.effective_chat.type != 'private':
        # Ignore or send a message if a non-owner tries this command
        return ConversationHandler.END
    if monitor_active:
        await update.message.reply_text("⚠️ Contract monitoring is already active. Please stop it before starting a new one.")
        return ConversationHandler.END

    # Prompt for ticker symbol
    await update.message.reply_text("🎯 <b>Select Contract Ticker</b>\n\nPlease enter the ticker of the index option (e.g. <code>SPXW</code> for weekly S&P 500 options).", parse_mode='HTML')
    return SELECT_TICKER

async def ticker_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the chosen ticker and asks for Call or Put selection."""
    ticker = update.message.text.strip().upper()
    # Basic validation: ticker should be non-empty
    if not ticker:
        await update.message.reply_text("❌ Invalid ticker. Please enter a valid ticker (e.g. SPXW).")
        return SELECT_TICKER
    context.user_data['ticker'] = ticker
    # Ask for option type (Call or Put) with buttons
    buttons = [
        [InlineKeyboardButton("Call 📈", callback_data="type_call"), InlineKeyboardButton("Put 📉", callback_data="type_put")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("➡️ <b>Select Option Type</b>\nChoose Call or Put:", reply_markup=reply_markup, parse_mode='HTML')
    return SELECT_TYPE

async def type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the chosen option type and asks for expiration date selection."""
    query = update.callback_query
    await query.answer()  # acknowledge the button press
    # Determine type from callback data
    chosen_type = "C" if query.data == "type_call" else "P"
    context.user_data['option_type'] = chosen_type

    # Compute upcoming expiration dates (nearest Monday, Wednesday, Friday)
    from datetime import datetime, timedelta
    today = datetime.now().date()
    # List to collect next few expiration dates (Mon, Wed, Fri)
    upcoming_dates = []
    # Weekday numbers for Mon=0, Tue=1, ..., Sun=6
    target_weekdays = [0, 2, 4]  # Monday, Wednesday, Friday
    # Find the next occurrences for each target weekday
    # We will find up to the next 3 upcoming dates (not necessarily all in the same week).
    date = today
    # If today is one of target days and market likely still open, we include it as an option as well.
    count_added = 0
    while count_added < 3:
        if date.weekday() in target_weekdays:
            # Only include if it's not a past date (shouldn't happen since we start at today)
            if date >= today:
                upcoming_dates.append(date)
                count_added += 1
        date += timedelta(days=1)
    # Now we have up to 3 dates (today or future Mon/Wed/Fri)
    # Prepare buttons for these dates
    buttons = []
    for d in upcoming_dates:
        # Format as e.g. "Mon 5/05"
        label = d.strftime("%a %m/%d")
        # Use ISO format in callback data for easy parsing
        data = f"date_{d.isoformat()}"
        buttons.append([InlineKeyboardButton(label, callback_data=data)])
    reply_markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text="📅 <b>Select Expiration Date</b>\nChoose one of the upcoming expiration dates:", reply_markup=reply_markup, parse_mode='HTML')
    return SELECT_EXPIRY

async def expiry_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the chosen expiration date and asks for strike price input."""
    query = update.callback_query
    await query.answer()
    # Parse date from callback data (format "date_YYYY-MM-DD")
    try:
        date_str = query.data.split("_", 1)[1]
        from datetime import datetime
        expiry_date = datetime.fromisoformat(date_str).date()
    except Exception as e:
        logger.error(f"Failed to parse expiry date: {e}")
        await query.edit_message_text("❌ Failed to parse the selected date. Please try /monitor again.")
        return ConversationHandler.END

    context.user_data['expiry_date'] = expiry_date
    # Ask user for strike price
    await query.edit_message_text(f"✍️ <b>Enter Strike Price</b>\n\nPlease send the strike price for the contract (e.g. <code>4200</code>).", parse_mode='HTML')
    return INPUT_STRIKE

async def strike_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the strike price and asks for price difference threshold."""
    text = update.message.text.strip()
    # Validate that strike is a number
    try:
        strike_val = float(text)
        if strike_val <= 0:
            raise ValueError("Strike must be positive.")
    except Exception as e:
        await update.message.reply_text("❌ Invalid strike price. Please enter a positive number (e.g. 4200).")
        return INPUT_STRIKE
    # Use a decimal to avoid floating issues when formatting the contract code
    from decimal import Decimal, getcontext
    getcontext().prec = 10
    strike_decimal = Decimal(str(text))
    context.user_data['strike'] = strike_decimal  # store Decimal
    # Ask for price difference threshold
    await update.message.reply_text("🔔 <b>Set Price Difference Threshold</b>\n\nEnter the price difference (in $) at which the bot should send an update (e.g. <code>5</code> for $5 moves).", parse_mode='HTML')
    return INPUT_THRESHOLD

async def threshold_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the threshold and asks for confirmation to activate monitoring."""
    text = update.message.text.strip()
    # Validate threshold as positive number
    try:
        threshold_val = float(text)
        if threshold_val <= 0:
            raise ValueError("Threshold must be positive.")
    except Exception as e:
        await update.message.reply_text("❌ Invalid threshold. Please enter a positive number (e.g. 5).")
        return INPUT_THRESHOLD
    context.user_data['threshold'] = threshold_val

    # Prepare a summary for confirmation
    ticker = context.user_data.get('ticker')
    opt_type = context.user_data.get('option_type')
    expiry_date = context.user_data.get('expiry_date')
    strike_decimal = context.user_data.get('strike')
    threshold_val = context.user_data.get('threshold')
    # Human-readable type
    type_text = "Call" if opt_type == "C" else "Put"
    expiry_text = expiry_date.strftime("%d %b %Y")  # e.g. 05 May 2025
    strike_text = str(strike_decimal).rstrip('0').rstrip('.')  # format strike nicely
    summary = (f"📃 <b>Confirm Contract Selection</b>\n"
               f"Ticker: <code>{ticker}</code>\n"
               f"Type: <b>{type_text}</b>\n"
               f"Expiration: <b>{expiry_text}</b>\n"
               f"Strike: <b>{strike_text}</b>\n"
               f"Threshold: <b>${threshold_val:.2f}</b>\n\n"
               f"✅ Start monitoring this contract?")
    # Show confirm and cancel buttons
    buttons = [
        [InlineKeyboardButton("✅ Confirm", callback_data="confirm"), InlineKeyboardButton("🚫 Cancel", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(summary, reply_markup=reply_markup, parse_mode='HTML')
    return CONFIRM

async def confirm_or_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the confirmation or cancellation of the monitoring activation."""
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        # User chose to cancel activation
        await query.edit_message_text("❌ Monitoring setup canceled.")
        # Clean up user_data
        context.user_data.clear()
        return ConversationHandler.END

    # If confirmed, start monitoring
    # Build the option contract symbol (OPRA code) from user selections
    ticker = context.user_data.get('ticker')
    opt_type = context.user_data.get('option_type')  # "C" or "P"
    expiry_date = context.user_data.get('expiry_date')  # datetime.date
    strike_decimal = context.user_data.get('strike')    # Decimal
    threshold_val = context.user_data.get('threshold')  # float

    # Format expiration date as YYMMDD
    expiry_code = expiry_date.strftime("%y%m%d")
    # Format strike price: strike * 1000, zero-pad to 8 digits
    strike_int = int(strike_decimal * 1000)  # Decimal * 1000 -> int
    strike_code = f"{strike_int:08d}"
    # Full OPRA symbol code
    option_symbol = f"{ticker} {expiry_code}{opt_type}{strike_code}"
    context.user_data['option_symbol'] = option_symbol

    # Initialize Playwright browser for Webull
    global play, browser, page, monitor_job, monitor_active
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        await query.edit_message_text("⚠️ Playwright is not installed. Please ensure `playwright` is installed in the environment.")
        return ConversationHandler.END

    # Launch browser (Chromium headless)
    try:
        play = await async_playwright().start()
        browser = await play.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context_browser = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context_browser.new_page()
    except Exception as e:
        logger.error(f"Browser launch failed: {e}")
        await query.edit_message_text("⚠️ Failed to launch browser for scraping. Make sure the environment supports headless browser.")
        return ConversationHandler.END

    # Navigate to Webull page for the option
    # (Using the SPX index page as a starting point, then searching for the option symbol)
    target_url = "https://www.webull.com/quote/idxsp-inx"
    try:
        await page.goto(target_url)
        # Try to search for the option using the search bar (if available)
        # The Webull site has a search input for symbols; we'll attempt to use it.
        search_input_selector = "input[placeholder='Symbol/Name']"
        await page.fill(search_input_selector, option_symbol)
        await page.wait_for_timeout(500)  # small delay for suggestions to appear
        await page.keyboard.press("Enter")
        # Wait a moment for the option quote page to load (if it exists)
        await page.wait_for_timeout(2000)
    except Exception as e:
        logger.warning(f"Navigation/search on Webull failed: {e}")
        # Even if search fails, continue to set up monitoring (we will still attempt screenshots)
    # At this point, we have attempted to load the option quote. The page variable holds the current page.

    # Set up monitoring job
    monitor_active = True
    # Determine initial price via Yahoo Finance option chain (to set baseline)
    initial_price = None
    try:
        import aiohttp
        # Yahoo Finance option chain API for ^SPX
        exp_timestamp = int(expiry_date.strftime("%s"))  # seconds since epoch for expiry date
        yahoo_url = f"https://query1.finance.yahoo.com/v7/finance/options/^SPX?date={exp_timestamp}"
        async with aiohttp.ClientSession() as session:
            async with session.get(yahoo_url) as resp:
                data = await resp.json()
                # Traverse JSON to find the specific contract
                options = data["optionChain"]["result"][0]["options"][0]
                chain = options['calls'] if opt_type == "C" else options['puts']
                strike_val = float(str(strike_decimal))
                for contract in chain:
                    if contract.get('strike') and abs(contract['strike'] - strike_val) < 1e-6:
                        # Found matching strike
                        last_price = contract.get('lastPrice')
                        bid = contract.get('bid')
                        ask = contract.get('ask')
                        # Use lastPrice if available, otherwise mid of bid/ask
                        if last_price is not None:
                            initial_price = float(last_price)
                        elif bid is not None and ask is not None:
                            initial_price = (bid + ask) / 2.0
                        elif bid is not None:
                            initial_price = float(bid)
                        elif ask is not None:
                            initial_price = float(ask)
                        else:
                            initial_price = None
                        break
    except Exception as e:
        logger.error(f"Yahoo Finance API error: {e}")
    if initial_price is None:
        initial_price = 0.0  # Fallback if we couldn't get a price (will trigger immediate update likely)

    # Define the asynchronous job callback for monitoring
    async def check_price(context: ContextTypes.DEFAULT_TYPE) -> None:
        """Job callback to check the option price and send update if threshold crossed."""
        global page, monitor_job, monitor_active
        try:
            import aiohttp
            # Fetch current price via Yahoo Finance
            exp_timestamp = int(context.job.context['expiry_date'].strftime("%s"))
            yahoo_url = f"https://query1.finance.yahoo.com/v7/finance/options/^SPX?date={exp_timestamp}"
            async with aiohttp.ClientSession() as session:
                async with session.get(yahoo_url) as resp:
                    data = await resp.json()
                    options = data["optionChain"]["result"][0]["options"][0]
                    chain = options['calls'] if context.job.context['option_type'] == "C" else options['puts']
                    strike_val = float(str(context.job.context['strike']))
                    current_price = None
                    for contract in chain:
                        if contract.get('strike') and abs(contract['strike'] - strike_val) < 1e-6:
                            last_price = contract.get('lastPrice')
                            bid = contract.get('bid')
                            ask = contract.get('ask')
                            if last_price is not None:
                                current_price = float(last_price)
                            elif bid is not None and ask is not None:
                                current_price = (bid + ask) / 2.0
                            elif bid is not None:
                                current_price = float(bid)
                            elif ask is not None:
                                current_price = float(ask)
                            else:
                                current_price = None
                            break
            if current_price is None:
                # If we could not get a price (e.g., after hours), skip
                return
            last_price = context.job.context['last_price']
            threshold = context.job.context['threshold']
            # Check if price moved beyond threshold
            if abs(current_price - last_price) >= threshold:
                # Update last_price baseline for next time
                context.job.context['last_price'] = current_price
                # Take screenshot of the Webull page
                try:
                    await page.reload()
                    # Wait briefly for content to update/render
                    await page.wait_for_timeout(1500)
                except Exception as e:
                    logger.warning(f"Page reload error: {e}")
                image_bytes = await page.screenshot()  # take screenshot as bytes
                # Prepare caption with contract info and price
                symbol_text = context.job.context['symbol_text']
                caption = f"{symbol_text} – Price: ${current_price:.2f}"
                # Send image to the VIP channel
                await context.bot.send_photo(chat_id=CHANNEL_ID_VIP, photo=image_bytes, caption=caption)
        except Exception as e:
            logger.error(f"Error in monitoring job: {e}")

    # Schedule the job to run periodically (e.g., every 30 seconds)
    job_context = {
        'symbol_text': f"{ticker} {expiry_date.strftime('%d%b%y')} {float(str(strike_decimal)):.2f}{opt_type}",  # e.g. "SPXW 05May25 4200.00C"
        'option_type': opt_type,
        'expiry_date': expiry_date,
        'strike': strike_decimal,
        'threshold': threshold_val,
        'last_price': initial_price
    }
    monitor_job = context.job_queue.run_repeating(check_price, interval=30, first=5, context=job_context)

    # Edit the confirmation message to indicate activation and show a Deactivate button
    stop_button = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Deactivate", callback_data="deactivate")]])
    await query.edit_message_text(f"✅ Monitoring started for <b>{ticker} {type_text} {expiry_date.strftime('%d %b %Y')} {strike_decimal}</b>.\nPrice threshold: ${threshold_val:.2f}\n\nUse the button below to stop updates.", reply_markup=stop_button, parse_mode='HTML')
    return ConversationHandler.END

async def deactivate_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback for deactivation button to stop the monitoring."""
    global monitor_job, monitor_active, play, browser, page
    query = update.callback_query
    await query.answer()
    # Cancel the job if active
    if monitor_job:
        monitor_job.schedule_removal()
        monitor_job = None
    monitor_active = False
    # Close the browser if open
    try:
        if page:
            await page.close()
        if browser:
            await browser.close()
        if play:
            await play.stop()
    except Exception as e:
        logger.error(f"Error closing browser: {e}")
    page = browser = play = None
    # Acknowledge the deactivation to the user
    await query.edit_message_text("⏹️ Monitoring stopped.")
    # Clear any stored user_data (if in a private chat context)
    context.user_data.clear()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Fallback handler for /cancel command to abort the conversation."""
    await update.message.reply_text("🚫 Canceled the operation.")
    context.user_data.clear()
    return ConversationHandler.END

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Optional /start handler (if needed for your bot to greet or show help)."""
    if update.effective_user.id == OWNER_ID:
        await update.message.reply_text("Welcome! Use /monitor to set up contract monitoring.")
    else:
        await update.message.reply_text("Welcome!")

def main():
    # Create the application instance
    application = Application.builder().token(TOKEN).build()

    # Set up conversation handler for monitoring setup
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("monitor", start_monitor)],
        states={
            SELECT_TICKER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticker_chosen)],
            SELECT_TYPE: [CallbackQueryHandler(type_chosen, pattern=r"^type_")],
            SELECT_EXPIRY: [CallbackQueryHandler(expiry_chosen, pattern=r"^date_")],
            INPUT_STRIKE: [MessageHandler(filters.TEXT & ~filters.COMMAND, strike_chosen)],
            INPUT_THRESHOLD: [MessageHandler(filters.TEXT & ~filters.COMMAND, threshold_chosen)],
            CONFIRM: [CallbackQueryHandler(confirm_or_cancel, pattern=r"^(confirm|cancel)$")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # Handlers for deactivate and possibly start command
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(deactivate_monitor, pattern=r"^deactivate$"))
    application.add_handler(CommandHandler("start", start_cmd))

    # Start the webhook keep-alive server and run the bot
    keep_alive()
    application.run_polling(timeout=60)

if __name__ == "__main__":
    main()
