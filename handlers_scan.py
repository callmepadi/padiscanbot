# handlers_scan.py

from telegram import Update
from telegram.ext import ContextTypes
from web3.exceptions import InvalidAddress
from utils import w3, deep_scan_contract, human_format, escape_markdown_v2
import asyncio # Diperlukan untuk asyncio.to_thread

# handlers_scan.py

from telegram import Update
from telegram.ext import ContextTypes
from web3.exceptions import InvalidAddress
# PENTING: Import fungsi escape_markdown_v2 dari utils
from utils import w3, deep_scan_contract, human_format, escape_markdown_v2 
import asyncio # Diperlukan untuk asyncio.to_thread

async def padiscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /padiscan command."""
    if not context.args:
        await update.message.reply_text("Usage: `/padiscan <contract address>`", parse_mode='Markdown')
        return

    ca = context.args[0].strip()

    if not w3 or not w3.is_connected():
        await update.message.reply_text("⚠️ RPC Connection Failed. The bot cannot fetch On-Chain data.", parse_mode='Markdown')
        return

    try:
        checksum_addr = w3.to_checksum_address(ca)
        
        # Cek kode: Jika alamat TIDAK memiliki kode (yaitu, itu adalah Wallet/EOA), tolak.
        code = await asyncio.to_thread(lambda: w3.eth.get_code(checksum_addr))
        
        if not code or code == b'0x' or code == b'\x00':
             # Kriteria 1: Jika yang diinput BUKAN contract address
             await update.message.reply_text("❌ That’s not a contract address.", parse_mode='Markdown')
             return
             
    except InvalidAddress:
        await update.message.reply_text("❌ Invalid address format.")
        return
    except Exception as e:
        await update.message.reply_text(f"⚠️ Failed to check address type (RPC Error: {e.__class__.__name__}). Try again.")
        return

    msg = await update.message.reply_text("⏳ *PADISCAN* is scanning... Please wait..", parse_mode='Markdown')

    deep_scan_results = await deep_scan_contract(ca)

    metadata = deep_scan_results.pop('metadata', {})
    market_data = deep_scan_results.pop('market_data', {})
    safe_market_data = {k: market_data.get(k, 0.0) for k in ['Price', 'Liquidity', 'Price_Change', 'Volume']}
    lp_source_name = deep_scan_results.get('LP_Source_Name', 'Unknown DEX')

    v2_tax_data = deep_scan_results.pop('V2_Tax', {})
    v1_tax_data = deep_scan_results.pop('V1_Tax', {})
    
    best_tax_data = v2_tax_data if lp_source_name == "PulseX V2" else (v1_tax_data if lp_source_name == "PulseX V1" else v2_tax_data)

    honeypot_ui = "❌ No LP or trading not enabled yet"
    if best_tax_data.get('Honeypot') == '✅ OK':
        honeypot_ui = "✅ Not a Honeypot"
    elif best_tax_data.get('Honeypot', '').startswith('🚨'):
        honeypot_ui = "❌ Honeypot"

    # --- PENERAPAN MARKDOWN ESCAPE DIMULAI DI SINI ---
    
    # 1. Escape Metadata (Nama dan Ticker)
    metadata_name = escape_markdown_v2(metadata['Name'])
    metadata_ticker = escape_markdown_v2(metadata['Ticker'])
    
    # 2. Escape Owner Address
    owner_address_escaped = escape_markdown_v2(deep_scan_results['Owner'])
    
    # 3. Escape Sus_Features (yang mungkin mengandung karakter aneh)
    sus_features_input = deep_scan_results['Sus_Features']
    if sus_features_input:
        # Pisahkan baris, escape setiap baris, lalu gabungkan kembali
        sus_features_list = sus_features_input.split('\n')
        sus_features_escaped = '\n'.join([escape_markdown_v2(line) for line in sus_features_list])
    else:
        sus_features_escaped = sus_features_input
    
    # Catatan: Variabel ca tidak perlu di-escape karena selalu berada di code block backtick tunggal (`ca`).
    
    report = f"""
*{metadata_name}* *(${metadata_ticker})*
`{ca}`
*Owner:*
`{owner_address_escaped}`

*[PulseChain] - {lp_source_name}*
---------------------------------------
{deep_scan_results['Verify']}
{deep_scan_results['Upgradeable']}
{honeypot_ui}

🅑 Buy Tax: {best_tax_data.get('BuyTax', 'N/A')}
🅢 Sell Tax: {best_tax_data.get('SellTax', 'N/A')}
---------------------------------------
*LP Burn:* {deep_scan_results['LP_burnt']}
*Supply Left:* {deep_scan_results['Supply_in_Pool']}
---------------------------------------
💰 *Price:* ${safe_market_data['Price']:.10f}
💧 *Liquidity:* ${safe_market_data['Liquidity']:,.2f}
🔄 *Price Change (24h):* {safe_market_data['Price_Change']:.2f}%
🔊 *Volume (24h):* ${safe_market_data['Volume']:,.2f}
---------------------------------------
*Non-standard Functions:*
{sus_features_escaped}
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
        await update.message.reply_text(f"⚠️ Failed to send full report (Error: {e.__class__.__name__}). Try again or check logs")