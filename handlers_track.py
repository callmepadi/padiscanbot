# handlers_track.py

from telegram import Update
from telegram.ext import ContextTypes
from web3.exceptions import InvalidAddress
# UBAH: Ganti 'get_token_balances' dengan 'get_token_balances_graph'
from utils import w3, get_pls_balance, get_token_balances_graph, human_format, classify_wallet, escape_markdown_v2 
import asyncio # Diperlukan untuk asyncio.to_thread
async def paditrack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /paditrack command."""
    if not context.args:
        await update.message.reply_text("Usage: `/paditrack <wallet address>`", parse_mode='MarkdownV2')
        return

    wallet_address = context.args[0].strip()

    if not w3 or not w3.is_connected():
        await update.message.reply_text("⚠️ RPC Connection Failed\\. The bot cannot fetch On\\-Chain data\\.", parse_mode='MarkdownV2')
        return

    try:
        checksum_addr = w3.to_checksum_address(wallet_address)
        code = await asyncio.to_thread(lambda: w3.eth.get_code(checksum_addr))
        
        if code and code != b'0x' and code != b'\x00':
             await update.message.reply_text("❌ That’s not a wallet address\\.", parse_mode='MarkdownV2')
             return
             
    except InvalidAddress:
        await update.message.reply_text("❌ Invalid wallet address\\.", parse_mode='MarkdownV2')
        return
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed to check address type \\(RPC Error: {escape_markdown_v2(e.__class__.__name__)}\\)\\. Try again\\.", parse_mode='MarkdownV2')
        return


    msg = await update.message.reply_text("⏳ *PADISCAN* is tracking wallet balance\\.\\.\\. Please wait\\.\\.", parse_mode='MarkdownV2')

    pls_raw_balance, pls_balance, pls_value_usd, pls_price_usd, pls_price_display = await get_pls_balance(wallet_address)

    if pls_raw_balance is None:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=msg.message_id,
            text="❌ Failed to fetch PLS balance\\. Check address or RPC connection\\.",
            parse_mode='MarkdownV2'
        )
        return

    token_data = await get_token_balances_graph(wallet_address, pls_price_usd)

    total_token_value_usd = sum(t.get('usd_value', 0) for t in token_data if isinstance(t.get('usd_value'), (int, float)))
    total_wallet_value_usd = pls_value_usd + total_token_value_usd

    wallet_class = escape_markdown_v2(classify_wallet(total_wallet_value_usd))

    api_error = any(t.get('token', '').endswith('Error') or t.get('token', '').endswith('Failed') for t in token_data)

    if api_error:
        token_list_string = f"❌ Error: {escape_markdown_v2(token_data[0]['token'])}"
    elif not token_data:
        token_list_string = "No ERC\\-20 tokens with balance > 0 found\\."
    else:
        basic_lines = []
        pt_lines = []
        for t in token_data:
            # value_display sudah di-escape di utils.py
            value_display = escape_markdown_v2(t.get('usd_value_str', "N/A"))
            clean_symbol = escape_markdown_v2(t['token'])
            
            # Escape balance format
            balance_formatted = escape_markdown_v2(human_format(t['balance'], decimals=2))
            formatted_line = f"{clean_symbol:<12} {balance_formatted:>15} {value_display:>10}"
            
            if t.get('group') == 'PT':
                pt_lines.append(formatted_line)
            else:
                basic_lines.append(formatted_line)

        token_output_parts = []
        
        if basic_lines:
            token_output_parts.append("*ERC 20 Tokens*")
            # Menggunakan code block `...`
            token_output_parts.append("```\nTOKEN         BALANCE           VALUE (USD)")
            token_output_parts.append('\n'.join(basic_lines))
            token_output_parts.append("```")
        if pt_lines:
            token_output_parts.append("*Pump Tires Tokens*")
            token_output_parts.append("```\nTOKEN         BALANCE           VALUE (USD)")
            token_output_parts.append('\n'.join(pt_lines))
            token_output_parts.append("```")
            
        token_list_string = '\n'.join(token_output_parts)

    
    pls_balance_formatted = escape_markdown_v2(f"{pls_balance:,.2f}")
    
    total_wallet_value_usd_escaped = escape_markdown_v2(human_format(total_wallet_value_usd))
    pls_value_usd_escaped = escape_markdown_v2(human_format(pls_value_usd))
    total_token_value_usd_escaped = escape_markdown_v2(human_format(total_token_value_usd))
    
    social_handle_escaped = escape_markdown_v2("@padicalls")

    separator_line = "\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\"
    
    report = f"""
*Total Value:* ${total_wallet_value_usd_escaped}
`{wallet_address}`

\\[{wallet_class} \\- PulseChain\\]
{separator_line}
*PLS Balance*
*Balance:* {pls_balance_formatted} PLS
*Value:* ${pls_value_usd_escaped}
{separator_line}
*Assets*
*Total Value:* ${total_token_value_usd_escaped}

{token_list_string}
{separator_line}
*Subscribe my channel and follow my X* {social_handle_escaped}\\

*Tip Jar:*
`0x13C8D0a575aFaFc9948e70D017d8F748A1eD0D89`
"""

    try:
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=msg.message_id,
            text=report,
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed to send report \\(Error: {escape_markdown_v2(e.__class__.__name__)}\\)\\. Please try again or check logs", parse_mode='MarkdownV2')
