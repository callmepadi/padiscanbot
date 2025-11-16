# handlers_track.py

from telegram import Update
from telegram.ext import ContextTypes
from web3.exceptions import InvalidAddress
from utils import w3, get_pls_balance, get_token_balances, human_format, classify_wallet
import asyncio # Diperlukan untuk asyncio.to_thread

async def paditrack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /paditrack command."""
    if not context.args:
        await update.message.reply_text("Usage: `/paditrack <wallet address>`", parse_mode='Markdown')
        return

    wallet_address = context.args[0].strip()

    if not w3 or not w3.is_connected():
        await update.message.reply_text("⚠️ RPC Connection Failed. The bot cannot fetch On-Chain data.", parse_mode='Markdown')
        return

    try:
        checksum_addr = w3.to_checksum_address(wallet_address)
        
        # Cek kode: Jika alamat MEMILIKI kode (yaitu, itu adalah Contract Address), tolak.
        code = await asyncio.to_thread(lambda: w3.eth.get_code(checksum_addr))
        
        if code and code != b'0x' and code != b'\x00':
             # Kriteria 2: Jika yang diinput BUKAN wallet address
             await update.message.reply_text("❌ That’s not a wallet address.", parse_mode='Markdown')
             return
             
    except InvalidAddress:
        await update.message.reply_text("❌ Invalid wallet address.")
        return
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed to check address type (RPC Error: {e.__class__.__name__}). Try again.")
        return


    msg = await update.message.reply_text("⏳ *PADISCAN* is tracking wallet balance... Please wait..", parse_mode='Markdown')

    pls_raw_balance, pls_balance, pls_value_usd, pls_price_usd, pls_price_display = await get_pls_balance(wallet_address)

    if pls_raw_balance is None:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=msg.message_id,
            text="❌ Failed to fetch PLS balance. Check address or RPC connection.",
            parse_mode='Markdown'
        )
        return

    token_data = await get_token_balances(wallet_address, pls_price_usd)

    total_token_value_usd = sum(t.get('usd_value', 0) for t in token_data if isinstance(t.get('usd_value'), (int, float)))
    total_wallet_value_usd = pls_value_usd + total_token_value_usd

    wallet_class = classify_wallet(total_wallet_value_usd)

    api_error = any(t.get('token', '').endswith('Error') or t.get('token', '').endswith('Failed') for t in token_data)

    if api_error:
        token_list_string = f"❌ Error: {token_data[0]['token']}"
    elif not token_data:
        token_list_string = "No ERC-20 tokens with balance > 0 found."
    else:
        basic_lines = []
        pt_lines = []
        for t in token_data:
            value_display = t.get('usd_value_str', "N/A")
            clean_symbol = t['token'].replace('_PT', '').replace('2', '')
            balance_formatted = human_format(t['balance'], decimals=2)
            formatted_line = f"{clean_symbol:<12} {balance_formatted:>15} {value_display:>10}"
            if t.get('group') == 'PT':
                pt_lines.append(formatted_line)
            else:
                basic_lines.append(formatted_line)

        token_output_parts = []
        if basic_lines:
            token_output_parts.append("*ERC-20 Tokens*")
            token_output_parts.append("```\nTOKEN         BALANCE           VALUE (USD)")
            token_output_parts.append('\n'.join(basic_lines))
            token_output_parts.append("```")
        if pt_lines:
            token_output_parts.append("*Pump Tires Tokens*")
            token_output_parts.append("```\nTOKEN         BALANCE           VALUE (USD)")
            token_output_parts.append('\n'.join(pt_lines))
            token_output_parts.append("```")
        token_list_string = '\n'.join(token_output_parts)

    report = f"""
*[{wallet_class} - PulseChain]*
*Total Value: ${human_format(total_wallet_value_usd)}*
`{wallet_address}`
---------------------------------------
*PLS Balance*
*Balance:* {pls_balance:,.2f} PLS
*Value:* ${human_format(pls_value_usd)}
---------------------------------------
*Assets*
*Total Value:* ${human_format(total_token_value_usd)}

{token_list_string}
---------------------------------------
Don’t forget to subscribe to my channel and follow my X account @padicalls!

If this bot helped you out, feel free to drop me a tip:
`0x13C8D0a575aFaFc9948e70D017d8F748A1eD0D89`
"""

    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=msg.message_id,
            text=report,
            parse_mode='Markdown'
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed to send report. Please try again or check logs: {e.__class__.__name__}.")