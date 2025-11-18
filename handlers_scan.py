# handlers_scan.py

from telegram import Update
from telegram.ext import ContextTypes
from web3.exceptions import InvalidAddress
from utils import w3, deep_scan_contract, human_format, escape_markdown_v2
import asyncio # Diperlukan untuk asyncio.to_thread

async def padiscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /padiscan command."""
    if not context.args:
        await update.message.reply_text("Usage: `/padiscan <contract address>`", parse_mode='MarkdownV2')
        return

    ca = context.args[0].strip()

    if not w3 or not w3.is_connected():
        await update.message.reply_text("⚠️ RPC Connection Failed\\. The bot cannot fetch On\\-Chain data\\.", parse_mode='MarkdownV2')
        return

    try:
        checksum_addr = w3.to_checksum_address(ca)
        code = await asyncio.to_thread(lambda: w3.eth.get_code(checksum_addr))
        
        if not code or code == b'0x' or code == b'\x00':
             await update.message.reply_text("❌ That’s not a contract address\\.", parse_mode='MarkdownV2')
             return
             
    except InvalidAddress:
        await update.message.reply_text("❌ Invalid address format\\.", parse_mode='MarkdownV2')
        return
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed to check address type \\(RPC Error: {escape_markdown_v2(e.__class__.__name__)}\\)\\. Try again\\.", parse_mode='MarkdownV2')
        return

    msg = await update.message.reply_text("⏳ *PADISCAN* is scanning\\.\\.\\. Please wait\\.\\.", parse_mode='MarkdownV2')

    deep_scan_results = await deep_scan_contract(ca)

    metadata = deep_scan_results.pop('metadata', {})
    market_data = deep_scan_results.pop('market_data', {})
    safe_market_data = {k: market_data.get(k, 0.0) for k in ['Price', 'Liquidity', 'Price_Change', 'Volume']}
    lp_source_name_escaped = escape_markdown_v2(deep_scan_results.get('LP_Source_Name', 'Unknown DEX'))

    v2_tax_data = deep_scan_results.pop('V2_Tax', {})
    v1_tax_data = deep_scan_results.pop('V1_Tax', {})
    
    best_tax_data = v2_tax_data if deep_scan_results.get('LP_Source_Name') == "PulseX V2" else (v1_tax_data if deep_scan_results.get('LP_Source_Name') == "PulseX V1" else v2_tax_data)

    honeypot_ui = "❌ No LP or trading not enabled yet"
    if best_tax_data.get('Honeypot') == '✅ OK':
        honeypot_ui = "✅ Not a Honeypot"
    elif best_tax_data.get('Honeypot', '').startswith('🚨'):
        honeypot_ui = "❌ Honeypot"

    # --- PENERAPAN MARKDOWN ESCAPE YANG LENGKAP ---
    metadata_name = escape_markdown_v2(metadata.get('Name', 'Unknown Token'))
    metadata_ticker = escape_markdown_v2(metadata.get('Ticker', 'TOKEN'))
    owner_address_escaped = escape_markdown_v2(deep_scan_results.get('Owner', 'N/A'))
    
    sus_features_input = deep_scan_results.get('Sus_Features', 'N/A')
    if sus_features_input:
        sus_features_list = sus_features_input.split('\n')
        sus_features_escaped = '\n'.join([escape_markdown_v2(line) for line in sus_features_list])
    else:
        sus_features_escaped = escape_markdown_v2(sus_features_input)
        
    verify_escaped = escape_markdown_v2(deep_scan_results.get('Verify', 'N/A'))
    upgradeable_escaped = escape_markdown_v2(deep_scan_results.get('Upgradeable', 'N/A'))
    honeypot_ui_escaped = escape_markdown_v2(honeypot_ui)
    
    # LP Burn dan Supply Left di-escape di sini (sudah mengandung % non-escaped)
    lp_burnt_escaped = escape_markdown_v2(deep_scan_results.get('LP_burnt', 'N/A'))
    supply_in_pool_escaped = escape_markdown_v2(deep_scan_results.get('Supply_in_Pool', 'N/A'))
    
    # Harga
    price_escaped = escape_markdown_v2(f"{safe_market_data['Price']:.10f}")
    liquidity_escaped = escape_markdown_v2(human_format(safe_market_data['Liquidity'], decimals=2))
    volume_escaped = escape_markdown_v2(human_format(safe_market_data['Volume'], decimals=2))
    price_change_escaped = escape_markdown_v2(f"{safe_market_data['Price_Change']:.2f}")

    # Tax data sudah di-escape di utils.py
    buy_tax_escaped = best_tax_data.get('BuyTax', 'N/A')
    sell_tax_escaped = best_tax_data.get('SellTax', 'N/A')

    social_handle_escaped = escape_markdown_v2("@padicalls")
    
    separator_line = "\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\"

    # Template dengan MarkdownV2
    report = f"""
*{metadata_name}* \\(\\${metadata_ticker}\\)
`{ca}`
*Owner:*
`{owner_address_escaped}`

\\[PulseChain\\] \\- {lp_source_name_escaped}
{separator_line}
{verify_escaped}
{upgradeable_escaped}
{honeypot_ui_escaped}

🅑 *Buy Tax:* {buy_tax_escaped}
🅢 *Sell Tax:* {sell_tax_escaped}
{separator_line}
*LP Burn:* {lp_burnt_escaped}
*Supply Left:* {supply_in_pool_escaped}
{separator_line}
💰 *Price:* \\${price_escaped}
💧 *Liquidity:* \\${liquidity_escaped}
🔄 *Price Change \\(24h\\):* {price_change_escaped}\\%
🔊 *Volume \\(24h\\):* \\${volume_escaped}
{separator_line}
*Non Standard Functions:*
{sus_features_escaped}
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
        await update.message.reply_text(f"⚠️ Failed to send full report \\(Error: {escape_markdown_v2(e.__class__.__name__)}\\)\\. Try again or check logs", parse_mode='MarkdownV2')
