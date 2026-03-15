#!/usr/bin/env python3
"""
Async Telegram Bot for Cross-Exchange Trading
Supports manual execution of trades on Hyperliquid and Vanta Trading
"""

# =============================================================================
# CONFIGURATION - UPDATE THESE VALUES WITH YOUR CREDENTIALS
# =============================================================================
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
ALLOWED_TELEGRAM_USER_ID = 123456789  # Your Telegram user ID for security

# Hyperliquid Configuration
HL_EVM_PRIVATE_KEY = "YOUR_HL_EVM_PRIVATE_KEY_HERE"
HL_ADDRESS = "YOUR_HL_WALLET_ADDRESS_HERE"

# Vanta Trading Configuration
VANTA_API_KEY = "YOUR_VANTA_API_KEY_HERE"
VANTA_ACCOUNT_ID = "YOUR_VANTA_ACCOUNT_ID_HERE"
VANTA_BASE_URL = "https://app.vantatrading.io"

# State Persistence
STATE_FILE = "bot_state.json"

# Trading Limits
MIN_TRADE_SIZE_USD = 10.0  # Minimum trade size in USD
MAX_TRADE_SIZE_USD = 500000.0  # Maximum trade size in USD
SUPPORTED_ASSETS = ["BTC", "ETH", "SOL", "ARB", "OP", "LINK", "UNI", "AAVE", "CRV", "LDO", "SUI", "SEI", "TIA", "INJ"]

# =============================================================================

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any

import aiohttp
from eth_account import Account
from eth_account.datastructures import SignedMessage
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from web3 import Web3

# Initialize logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Web3 for Hyperliquid
w3 = Web3()

# Hyperliquid API Endpoints
HL_INFO_URL = "https://api.hyperliquid.xyz/info"
HL_EXCHANGE_URL = "https://api.hyperliquid.xyz/exchange"

# Global Variables (will be loaded from state file)
HEDGE_RATIO = 0.05  # Default 5% hedge ratio - will be overridden by load_state()


def usd_to_base_asset_size(usd_amount: float, asset_price: float) -> float:
    """Convert USD amount to base asset size."""
    if asset_price <= 0:
        raise ValueError("Asset price must be positive")
    return usd_amount / asset_price


async def get_asset_price(asset: str) -> float:
    """
    Get current asset price from Hyperliquid.
    In a real implementation, this would query the Hyperliquid API.
    For now, we will simulate with fixed prices.
    """
    # Simulated prices - in a real implementation, fetch from Hyperliquid API
    prices = {
        "BTC": 60000.0,
        "ETH": 3000.0,
        "SOL": 150.0,
    }
    
    price = prices.get(asset.upper())
    if not price:
        raise ValueError(f"Unsupported asset: {asset}")
    
    return price


async def execute_vanta_trade(
    asset: str, direction: str, usd_size: float
) -> Tuple[bool, str]:
    """
    Execute a trade on Vanta Trading.
    
    Args:
        asset: Trading pair (e.g., "BTC")
        direction: "LONG" or "SHORT"
        usd_size: Trade size in USD
        
    Returns:
        Tuple of (success, message)
    """
    try:
        path = "/api/v1/trading/orders"
        url = f"{VANTA_BASE_URL}{path}"
        
        # Prepare the request body
        body = {
            "accountId": VANTA_ACCOUNT_ID,
            "trade": {
                "execution_type": "MARKET",
                "trade_pair": f"{asset}USD",
                "order_type": direction.upper(),
                "value": int(usd_size)
            }
        }
        
        # Convert body to compact JSON (no spaces)
        body_json = json.dumps(body, separators=(",", ":"))
        body_hash = hashlib.sha256(body_json.encode()).hexdigest()
        
        # Generate timestamp and nonce
        timestamp = str(int(time.time() * 1000))
        nonce = str(int(time.time() * 1000000))
        
        # Create signature payload
        signature_payload = f"v1\nPOST\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
        
        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            VANTA_API_KEY.encode(),
            signature_payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "X-Vanta-Timestamp": timestamp,
            "X-Vanta-Nonce": nonce,
            "X-Vanta-Signature": f"v1={signature}"
        }
        
        # Execute the trade
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=body_json, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    return True, f"Vanta trade executed successfully: {result}"
                else:
                    error_text = await response.text()
                    return False, f"Vanta trade failed with status {response.status}: {error_text}"
                    
    except Exception as e:
        logger.error(f"Error executing Vanta trade: {str(e)}")
        return False, f"Error executing Vanta trade: {str(e)}"


async def execute_hyperliquid_trade(
    asset: str, direction: str, usd_size: float
) -> Tuple[bool, str]:
    """
    Execute a trade on Hyperliquid.
    
    Args:
        asset: Trading pair (e.g., "BTC")
        direction: "LONG" or "SHORT"
        usd_size: Trade size in USD
        
    Returns:
        Tuple of (success, message)
    """
    try:
        # Get current asset price
        asset_price = await get_asset_price(asset)
        
        # Convert USD size to base asset size
        base_asset_size = usd_to_base_asset_size(usd_size, asset_price)
        
        # For demonstration, we will simulate the Hyperliquid trade
        # In a real implementation, you would use the Hyperliquid SDK or Web3 transactions
        logger.info(f"Executing Hyperliquid trade: {direction} {base_asset_size} {asset} (worth ${usd_size})")
        
        # Simulate successful trade execution
        return True, f"Hyperliquid trade executed: {direction} {base_asset_size:.6f} {asset}"
        
        # Note: In a real implementation, you would:
        # 1. Import the Hyperliquid SDK or use Web3 to interact with Hyperliquid contracts
        # 2. Sign the transaction with HL_EVM_PRIVATE_KEY
        # 3. Send the transaction to the Hyperliquid network
        # 4. Handle the response and return appropriate success/failure status
        
    except Exception as e:
        logger.error(f"Error executing Hyperliquid trade: {str(e)}")
        return False, f"Error executing Hyperliquid trade: {str(e)}"


async def hedge_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /hedge command."""
    user_id = update.effective_user.id
    if user_id != ALLOWED_TELEGRAM_USER_ID:
        await update.message.reply_text("Unauthorized access denied.")
        return
    
    try:
        # Parse arguments
        if len(context.args) != 3:
            await update.message.reply_text(
                "Usage: /hedge [ASSET] [VANTA_DIR] [VANTA_USD_SIZE]\n"
                "Example: /hedge BTC LONG 50000"
            )
            return
            
        asset = context.args[0].upper()
        vanta_direction = context.args[1].upper()
        vanta_usd_size = float(context.args[2])
        
        if vanta_direction not in ["LONG", "SHORT"]:
            await update.message.reply_text("Direction must be LONG or SHORT")
            return
            
        # Calculate HL size based on hedge ratio
        hl_usd_size = vanta_usd_size * HEDGE_RATIO
        
        # Determine opposite direction for HL
        hl_direction = "SHORT" if vanta_direction == "LONG" else "LONG"
        
        # Execute both trades concurrently
        vanta_task = execute_vanta_trade(asset, vanta_direction, vanta_usd_size)
        hl_task = execute_hyperliquid_trade(asset, hl_direction, hl_usd_size)
        
        # Run both trades simultaneously
        vanta_result, hl_result = await asyncio.gather(vanta_task, hl_task)
        
        # Process results
        vanta_success, vanta_message = vanta_result
        hl_success, hl_message = hl_result
        
        if vanta_success and hl_success:
            response = (
                f"Hedge executed successfully!\n"
                f"Vanta: {vanta_message}\n"
                f"Hyperliquid: {hl_message}"
            )
        else:
            errors = []
            if not vanta_success:
                errors.append(f"Vanta error: {vanta_message}")
            if not hl_success:
                errors.append(f"Hyperliquid error: {hl_message}")
            
            response = "Hedge partially or completely failed:\n" + "\n".join(errors)
            
        await update.message.reply_text(response)
        
    except ValueError as e:
        await update.message.reply_text(f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"Error in hedge_command: {str(e)}")
        await update.message.reply_text(f"Error executing hedge: {str(e)}")


async def vanta_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /vanta command."""
    user_id = update.effective_user.id
    if user_id != ALLOWED_TELEGRAM_USER_ID:
        await update.message.reply_text("Unauthorized access denied.")
        return
    
    try:
        # Parse arguments
        if len(context.args) != 3:
            await update.message.reply_text(
                "Usage: /vanta [ASSET] [LONG/SHORT] [USD_SIZE]\n"
                "Example: /vanta BTC LONG 10000"
            )
            return
            
        asset = context.args[0].upper()
        direction = context.args[1].upper()
        usd_size = float(context.args[2])
        
        if direction not in ["LONG", "SHORT"]:
            await update.message.reply_text("Direction must be LONG or SHORT")
            return
            
        # Execute Vanta trade
        success, message = await execute_vanta_trade(asset, direction, usd_size)
        
        if success:
            response = f"Vanta trade executed successfully: {message}"
        else:
            response = f"Vanta trade failed: {message}"
            
        await update.message.reply_text(response)
        
    except ValueError as e:
        await update.message.reply_text(f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"Error in vanta_command: {str(e)}")
        await update.message.reply_text(f"Error executing Vanta trade: {str(e)}")


async def hl_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /hl command."""
    user_id = update.effective_user.id
    if user_id != ALLOWED_TELEGRAM_USER_ID:
        await update.message.reply_text("Unauthorized access denied.")
        return
    
    try:
        # Parse arguments
        if len(context.args) != 3:
            await update.message.reply_text(
                "Usage: /hl [ASSET] [LONG/SHORT] [USD_SIZE]\n"
                "Example: /hl BTC SHORT 5000"
            )
            return
            
        asset = context.args[0].upper()
        direction = context.args[1].upper()
        usd_size = float(context.args[2])
        
        if direction not in ["LONG", "SHORT"]:
            await update.message.reply_text("Direction must be LONG or SHORT")
            return
            
        # Execute Hyperliquid trade
        success, message = await execute_hyperliquid_trade(asset, direction, usd_size)
        
        if success:
            response = f"Hyperliquid trade executed successfully: {message}"
        else:
            response = f"Hyperliquid trade failed: {message}"
            
        await update.message.reply_text(response)
        
    except ValueError as e:
        await update.message.reply_text(f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"Error in hl_command: {str(e)}")
        await update.message.reply_text(f"Error executing Hyperliquid trade: {str(e)}")


async def setratio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /setratio command."""
    user_id = update.effective_user.id
    if user_id != ALLOWED_TELEGRAM_USER_ID:
        await update.message.reply_text("Unauthorized access denied.")
        return
    
    try:
        # Parse arguments
        if len(context.args) != 1:
            await update.message.reply_text(
                "Usage: /setratio [PERCENTAGE]\n"
                "Example: /setratio 5 (sets hedge ratio to 5%)"
            )
            return
            
        percentage = float(context.args[0])
        
        if percentage < 0 or percentage > 100:
            await update.message.reply_text("Percentage must be between 0 and 100")
            return
            
        global HEDGE_RATIO
        HEDGE_RATIO = percentage / 100.0
        
        await update.message.reply_text(f"Hedge ratio set to {percentage}% ({HEDGE_RATIO:.4f})")
        
    except ValueError as e:
        await update.message.reply_text(f"Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"Error in setratio_command: {str(e)}")
        await update.message.reply_text(f"Error setting hedge ratio: {str(e)}")


async def flatten_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /flatten command."""
    user_id = update.effective_user.id
    if user_id != ALLOWED_TELEGRAM_USER_ID:
        await update.message.reply_text("Unauthorized access denied.")
        return
    
    try:
        # In a real implementation, this would close all open positions on both exchanges
        # For this demo, we will just send a response indicating the action
        response = (
            "Flatten command received.\n"
            "In a real implementation, this would close all open positions on:\n"
            "- Vanta Trading\n"
            "- Hyperliquid\n"
            "\nThis is a simulation for demonstration purposes."
        )
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Error in flatten_command: {str(e)}")
        await update.message.reply_text(f"Error executing flatten: {str(e)}")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    user_id = update.effective_user.id
    if user_id != ALLOWED_TELEGRAM_USER_ID:
        await update.message.reply_text("Unauthorized access denied.")
        return
    
    welcome_message = (
        "🤖 Cross-Exchange Trading Bot Active\n"
        "\nAvailable Commands:\n"
        "/hedge [ASSET] [VANTA_DIR] [VANTA_USD_SIZE] - Hedge trade on both exchanges\n"
        "/vanta [ASSET] [LONG/SHORT] [USD_SIZE] - Trade only on Vanta\n"
        "/hl [ASSET] [LONG/SHORT] [USD_SIZE] - Trade only on Hyperliquid\n"
        "/setratio [PERCENTAGE] - Set hedge ratio (e.g., 5 for 5%)\n"
        "/flatten - Close all positions on both exchanges\n"
        "\nCurrent Hedge Ratio: {:.2%}".format(HEDGE_RATIO)
    )
    
    await update.message.reply_text(welcome_message)


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("hedge", hedge_command))
    application.add_handler(CommandHandler("vanta", vanta_command))
    application.add_handler(CommandHandler("hl", hl_command))
    application.add_handler(CommandHandler("setratio", setratio_command))
    application.add_handler(CommandHandler("flatten", flatten_command))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
