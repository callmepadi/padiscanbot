# handlers_track.py

import asyncio
import httpx
import logging
from typing import List, Dict, Any, Set
from telegram import Update
from telegram.ext import ContextTypes
from web3.exceptions import InvalidAddress

from utils import (
    w3,
    PULSESCAN_API_BASE_URL,
    PULSESCAN_API_KEY,
    DEXSCREENER_API_URL,
    WPLS_ADDRESS,
    PT_TOKENS_LIST,
    human_format,
    classify_wallet,
    escape_markdown_v2
)

async def get_prices_dexscreener_batch(addresses: List[str]) -> Dict[str, float]:
    """
    Mengambil harga token (priceUsd) dari DexScreener secara batch.
    Mengembalikan dictionary {address_lowercase: price_float}.
    """
    prices = {}
    if not addresses:
        return prices

    # DexScreener mendukung hingga 30 alamat per request
    chunk_size = 30
    chunks = [addresses[i:i + chunk_size] for i in range(0, len(addresses), chunk_size)]

    async with httpx.AsyncClient(timeout=10) as client:
        for chunk in chunks:
            url = f"{DEXSCREENER_API_URL}/{','.join(chunk)}"
            try:
                response = await client.get(url)
                data = response.json()
                
                # DexScreener mengembalikan 'pairs'. Kita ambil pair dengan likuiditas tertinggi
                # atau update harga jika token ditemukan.
                if data and 'pairs' in data:
                    for pair in data['pairs']:
                        # DexScreener bisa mengembalikan banyak pair untuk token yang sama.
                        # Kita prioritaskan pair di PulseChain (chain id: pulsechain)
                        if pair.get('chainId') != 'pulsechain':
                            continue

                        base_token = pair.get('baseToken', {})
                        quote_token = pair.get('quoteToken', {})
                        price_usd = float(pair.get('priceUsd', 0) or 0)

                        if price_usd <= 0:
                            continue

                        # Simpan harga untuk baseToken
                        base_addr = base_token.get('address', '').lower()
                        if base_addr and base_addr not in prices:
                             prices[base_addr] = price_usd
                        
                        # Simpan harga untuk quoteToken (opsional, tapi membantu kelengkapan)
                        quote_addr = quote_token.get('address', '').lower()
                        if quote_addr and quote_addr not in prices:
                            prices[quote_addr] = price_usd

            except Exception as e:
                logging.error(f"DexScreener batch fetch error: {e}")
    
    return prices

async def get_wallet_data_optimized(wallet_address: str):
    """
    Fungsi utama yang dioptimalkan:
    1. Ambil saldo PLS.
    2. Ambil daftar Token API.
    3. Ambil Harga Batch dari DexScreener.
    4. Hitung Nilai.
    """
    checksum_addr = w3.to_checksum_address(wallet_address)
    
    # 1. Ambil PLS Balance (Native)
    try:
        pls_wei = await asyncio.to_thread(lambda: w3.eth.get_balance(checksum_addr))
        pls_balance = float(w3.from_wei(pls_wei, 'ether'))
    except Exception:
        pls_balance = 0.0

    # 2. Ambil Daftar Token dari PulseScan
    token_list = []
    url_tokenlist = f"{PULSESCAN_API_BASE_URL}?module=account&action=tokenlist&address={checksum_addr}"
    if PULSESCAN_API_KEY: url_tokenlist += f"&apikey={PULSESCAN_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url_tokenlist)
            data = response.json()
            if data.get('status') == '1' and isinstance(data.get('result'), list):
                token_list = data['result']
    except Exception:
        logging.warning("PulseScan API Tokenlist fetch failed.")

    # 3. Siapkan daftar alamat untuk DexScreener
    # Kita butuh WPLS untuk menghitung nilai PLS native
    addresses_to_fetch = {WPLS_ADDRESS.lower()} 
    
    parsed_tokens = []

    # Filter token yang saldonya > 0
    for t in token_list:
        raw_bal = int(t.get('Balance', 0))
        if raw_bal > 0:
            contract_addr = t.get('ContractAddress')
            if contract_addr:
                addresses_to_fetch.add(contract_addr.lower())
                
                # Parse decimals
                decimals = t.get('TokenDecimal')
                if not decimals: decimals = 18
                else: decimals = int(decimals)
                
                real_bal = raw_bal / (10 ** decimals)
                
                parsed_tokens.append({
                    "address": contract_addr.lower(),
                    "symbol": t.get('TokenSymbol', 'UNK'),
                    "name": t.get('TokenName', 'Unknown'),
                    "balance": real_bal,
                    "type": "ERC20"
                })

    # 4. Ambil Harga (Batch)
    price_map = await get_prices_dexscreener_batch(list(addresses_to_fetch))

    # 5. Hitung Nilai PLS Native
    pls_price = price_map.get(WPLS_ADDRESS.lower(), 0.0)
    pls_value_usd = pls_balance * pls_price

    # 6. Hitung Nilai Token
    final_token_data = []
    total_token_usd = 0.0

    # Cek grup token PT
    pt_map = {t['address'].lower(): t['group'] for t in PT_TOKENS_LIST}

    for token in parsed_tokens:
        addr = token['address']
        price = price_map.get(addr, 0.0)
        
        value_usd = 0.0
        value_str = "N/A"

        if price > 0:
            value_usd = token['balance'] * price
            total_token_usd += value_usd
            if value_usd < 0.01 and value_usd > 0:
                value_str = f"≈ ${value_usd:.4f}"
            else:
                value_str = f"≈ ${human_format(value_usd)}"
        
        # Tentukan Grup
        group = pt_map.get(addr, "BASIC")

        final_token_data.append({
            "symbol": token['symbol'],
            "balance": token['balance'],
            "value_usd": value_usd, # Float untuk sorting
            "value_str": value_str, # String untuk display
            "group": group
        })

    # Sort berdasarkan nilai USD tertinggi
    final_token_data.sort(key=lambda x: x['value_usd'], reverse=True)

    return {
        "pls_balance": pls_balance,
        "pls_value": pls_value_usd,
        "total_token_value": total_token_usd,
        "tokens": final_token_data
    }

async def paditrack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /paditrack command (OPTIMIZED)."""
    if not context.args:
        await update.message.reply_text("Usage: `/paditrack <wallet address>`", parse_mode='MarkdownV2')
        return

    wallet_address = context.args[0].strip()

    # Cek koneksi
    if not w3 or not w3.is_connected():
        await update.message.reply_text("⚠️ RPC Connection Failed\\. Bot cannot fetch data\\.", parse_mode='MarkdownV2')
        return

    # Validasi Address
    try:
        checksum_addr = w3.to_checksum_address(wallet_address)
        code = await asyncio.to_thread(lambda: w3.eth.get_code(checksum_addr))
        if code and code != b'0x' and code != b'\x00':
             await update.message.reply_text("❌ That’s a contract, not a wallet\\.", parse_mode='MarkdownV2')
             return
    except InvalidAddress:
        await update.message.reply_text("❌ Invalid wallet address\\.", parse_mode='MarkdownV2')
        return
    except Exception:
        await update.message.reply_text("⚠️ Error checking address\\.", parse_mode='MarkdownV2')
        return

    msg = await update.message.reply_text("⏳ *PADISCAN* is tracking wallet\\.\\.\\.", parse_mode='MarkdownV2')

    # --- CORE LOGIC ---
    data = await get_wallet_data_optimized(wallet_address)
    
    # --- FORMATTING ---
    total_net_worth = data['pls_value'] + data['total_token_value']
    wallet_class = escape_markdown_v2(classify_wallet(total_net_worth))
    
    # Pisahkan token berdasarkan grup
    basic_lines = []
    pt_lines = []

    for t in data['tokens']:
        clean_symbol = escape_markdown_v2(t['symbol'])
        balance_fmt = escape_markdown_v2(human_format(t['balance']))
        value_fmt = escape_markdown_v2(t['value_str'])
        
        # Format baris: SYMBOL (kiri), BALANCE (kanan), VALUE (kanan)
        line = f"{clean_symbol:<10} {balance_fmt:>12} {value_fmt:>15}"
        
        if t['group'] == 'PT':
            pt_lines.append(line)
        else:
            basic_lines.append(line)

    token_list_string = ""
    if not basic_lines and not pt_lines:
        token_list_string = "No assets found\\."
    else:
        parts = []
        if basic_lines:
            parts.append("*ERC 20 Tokens*")
            parts.append("```\nToken          Balance           Value")
            parts.append('\n'.join(basic_lines))
            parts.append("```")
        if pt_lines:
            parts.append("*Pump Tires Tokens*")
            parts.append("```\nToken          Balance           Value")
            parts.append('\n'.join(pt_lines))
            parts.append("```")
        token_list_string = '\n'.join(parts)

    # Escape value total
    total_val_esc = escape_markdown_v2(human_format(total_net_worth))
    pls_bal_esc = escape_markdown_v2(f"{data['pls_balance']:,.2f}")
    pls_val_esc = escape_markdown_v2(human_format(data['pls_value']))
    tokens_val_esc = escape_markdown_v2(human_format(data['total_token_value']))
    
    social = escape_markdown_v2("@padicalls")
    sep = "\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\"

    report = f"""
*Total Value:* ${total_val_esc}
`{wallet_address}`

\\[{wallet_class} \\- PulseChain\\]
{sep}
*PLS Balance*
*Balance:* {pls_bal_esc} PLS
*Value:* ${pls_val_esc}
{sep}
*Assets*
*Total Value:* ${tokens_val_esc}

{token_list_string}
{sep}
*Subscribe my channel and follow my X* {social}\\

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
        logging.error(f"Error sending message: {e}")
        await update.message.reply_text("⚠️ Failed to send report\\.", parse_mode='MarkdownV2')
