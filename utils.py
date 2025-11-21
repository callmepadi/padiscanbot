# utils.py

import os
import logging
import httpx
import json
import re
import asyncio
from web3 import Web3
from web3.exceptions import ContractLogicError, BadFunctionCallOutput
from typing import Tuple, Any, Dict, Optional, List, Set
from dotenv import load_dotenv
from telegram.ext import ContextTypes 

# Tambahkan ke bagian UTILS
PULSEX_V1_GRAPHQL_URL = "https://graph.pulsechain.com/subgraphs/name/pulsechain/pulsex/graphql"
PULSEX_V2_GRAPHQL_URL = "https://graph.pulsechain.com/subgraphs/name/pulsechain/pulsexv2/graphql"

# --- 1. Konfigurasi Global & Konstanta ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# Ambil RPC dari .env, tapi kita akan punya list cadangan di bawah
ENV_RPC = os.getenv("PULSECHAIN_RPC_URL")
PULSESCAN_API_KEY = os.getenv("PULSESCAN_API_KEY") 

HONEY_V2_ADDRESS = os.getenv("HONEY_V2_ADDRESS") 
HONEY_V1_ADDRESS = os.getenv("HONEY_V1_ADDRESS")

# --- 2. Inisialisasi Web3 dengan Auto-Switch RPC ---
# List RPC prioritas. Bot akan mencoba satu per satu sampai berhasil.
RPC_LIST = [
    ENV_RPC,                                # Prioritas 1: Dari .env
    "https://pulsechain.publicnode.com",    # Prioritas 2: Sering lolos blokir ISP
    "https://rpc-pulsechain.g4mm4.io",      # Prioritas 3
    "https://1rpc.io/pls",                  # Prioritas 4
    "https://rpc.pulsechain.com"            # Prioritas 5: Standard (sering diblokir)
]

# Hapus duplikat dan nilai None/Kosong
RPC_LIST = list(dict.fromkeys([url for url in RPC_LIST if url]))

w3 = None
connected_rpc_url = None

print(f"🔌 Connecting to PulseChain... Trying {len(RPC_LIST)} RPCs...")

for url in RPC_LIST:
    try:
        provider = Web3.HTTPProvider(url, request_kwargs={'timeout': 10})
        temp_w3 = Web3(provider)
        if temp_w3.is_connected():
            w3 = temp_w3
            connected_rpc_url = url
            print(f"✅ Success! Connected to: {url}")
            break
        else:
            print(f"⚠️ Failed to connect to: {url}")
    except Exception as e:
        print(f"⚠️ Error connecting to {url}: {e}")

if w3 is None:
    logging.error("❌ FATAL: All RPC connections failed.")
    print("❌ FATAL: Could not connect to any PulseChain RPC node. Check your internet connection or VPN.")

# --- KONFIGURASI API LAINNYA ---
PULSESCAN_API_BASE_URL = "https://api.scan.pulsechain.com/api"
SOURCIFY_REPO = "https://repo.sourcify.dev/contracts"
DEXSCREENER_API_URL = "https://api.dexscreener.com/latest/dex/tokens"

# --- ALAMAT KRITIS ---
WPLS_ADDRESS = "0xA1077a294dDE1B09bB078844df40758a5D0f9a27"
WPLS_CHECKSUM_LOWER = WPLS_ADDRESS.lower() 
DEAD_ADDRESS = "0x000000000000000000000000000000000000dEaD"
PULSE_BURN_ADDRESS = "0x0000000000000000000000000000000000000369"

BURN_ADDRESSES_CHECKSUM = []
WPLS_CHECKSUM = None
if w3:
    try:
        BURN_ADDRESSES_CHECKSUM = [w3.to_checksum_address(a) for a in [DEAD_ADDRESS, "0x0000000000000000000000000000000000000000", PULSE_BURN_ADDRESS]]
        WPLS_CHECKSUM = w3.to_checksum_address(WPLS_ADDRESS)
    except Exception:
        pass

# --- KONFIGURASI SCANNER ---
SCAN_MODE = "balanced"
STANDARD_ERC20_FUNCTIONS = {
    'totalSupply', 'balanceOf', 'transfer', 'transferFrom', 'approve', 'allowance', 'name', 'symbol', 'decimals', 'owner', 'increaseAllowance', 'decreaseAllowance', 'getTokenHolders', 'burn', 'burnFrom' 
}
IGNORED_ADMIN_VARS = {"owner", "_owner", "spender", "msgSender", "burnAddress", "recipient", "to", "from", "getFees"}
SAFE_SETTER_EXCLUDES = {"transferownership", "_transferownership"}

# --- ABI MINIMAL ---
TOKEN_MINIMAL_ABI = [
    {"constant": True, "inputs": [], "name": "owner", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"internalType":"uint8","name":"","type":"uint8"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"}
]
HONEY_ABI_MINIMAL = [
    {
        "inputs": [{"internalType": "address", "name": "token", "type": "address"}],
        "name": "checkHoneyMain",
        "outputs": [{"internalType": "uint256", "name": "buyEstimate", "type": "uint256"}, {"internalType": "uint256", "name": "buyReal", "type": "uint256"}, {"internalType": "uint256", "name": "sellEstimate", "type": "uint256"}, {"internalType": "uint256", "name": "sellReal", "type": "uint256"}, {"internalType": "bool", "name": "buy", "type": "bool"}, {"internalType": "bool", "name": "sell", "type": "bool"}, {"internalType": "uint256", "name": "blockNumber", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# --- DAFTAR TOKEN KHUSUS (Pump Tires) ---
PT_TOKENS_LIST = [
    {"symbol": "PHEN", "address": "0xFDe3255Fb043eA55F9D8635C5e7FF18770A6a810", "group": "PT"},
    {"symbol": "PEPE", "address": "0x2a8f6137ba7749560bb9e84b36cb2ac9536d9e88", "group": "PT"},
    {"symbol": "ZERO", "address": "0xf6703DBff070F231eEd966D33B1B6D7eF5207d26", "group": "PT"},
    {"symbol": "MOST", "address": "0xe33a5AE21F93aceC5CfC0b7b0FDBB65A0f0Be5cC", "group": "PT"},
    {"symbol": "DEVC", "address": "0xA804b9E522A2D1645a19227514CFe856Ad8C2fbC", "group": "PT"},
    {"symbol": "PUMP", "address": "0xec4252e62C6dE3D655cA9Ce3AfC12E553ebBA274", "group": "PT"},
    {"symbol": "PTIGER", "address": "0xC2ACde27428d292C4E8e5A4A38148d6b7A2215f5", "group": "PT"},
    {"symbol": "PCOCK", "address": "0xc10A4Ed9b4042222d69ff0B374eddd47ed90fC1F", "group": "PT"},
    {"symbol": "XGAME", "address": "0x4Eb7C1c05087f98Ae617d006F48914eE73fF8D2A", "group": "PT"},
    {"symbol": "YOINK", "address": "0xfc975B5Dee0Bf337030a2310D2b4545263694cd3", "group": "PT"},
    {"symbol": "TRUMP", "address": "0x8cc6d99114edd628249fabc8a4d64f9a759a77bf", "group": "PT"},
    {"symbol": "BEST", "address": "0x84601f4e914e00dc40296ac11cdd27926be319f2", "group": "PT"},
    {"symbol": "SOL", "address": "0x873301f2b4b83feaff04121b68ec9231b29ce0df", "group": "PT"},
    {"symbol": "DOGE", "address": "0xdde9164e7e0da7ae48b58f36b42c1c9f80e7245f", "group": "PT"},
    {"symbol": "BTC", "address": "0xf7bf2a938f971d7e4811a1170c43d651d21a0f81", "group": "PT"},
    {"symbol": "PLS", "address": "0x260e5da7ef6e30e0a647d1adf47628198dcb0709", "group": "PT"},
    {"symbol": "XRP", "address": "0x35cf97ec047f93660c27c21fdd846dea72bc66d7", "group": "PT"},
    {"symbol": "MARS", "address": "0x709e07230860fe0543dcbc359fdf1d1b5ed13305", "group": "PT"},
    {"symbol": "USDC", "address": "0x080f7a005834c84240f25b2df4aed8236bd57812", "group": "PT"},
    {"symbol": "ADA", "address": "0x4774e075c16989be68c26cc146fe707ef4393661", "group": "PT"},
    {"symbol": "TRX", "address": "0x0392fbd58918e7ecbb2c68f4ebe4e2225c9a6468", "group": "PT"},
    {"symbol": "PLSX", "address": "0xd73731bda87c3464e76268c094d959c1b35b9bf1", "group": "PT"},
    {"symbol": "ETH", "address": "0xbfcfa52225baa5feec5fbb54e6458957d53ddd94", "group": "PT"},
    {"symbol": "PUPPERS", "address": "0xbd59a88754902b80922dfebc15c7ea94a8c21ce2", "group": "PT"},
    {"symbol": "JOHN", "address": "0x83a7722b431062a39154201f331344dccfa678fb", "group": "PT"},
    {"symbol": "urmom", "address": "0xe43b3cee3554e120213b8b69caf690b6c04a7ec0", "group": "PT"},
    {"symbol": "LIBELOOR", "address": "0xc1cb1bdd29bbed60594b3db3e8b3b7971b3fd71a", "group": "PT"},
    {"symbol": "Briah", "address": "0xa80736067abdc215a3b6b66a57c6e608654d0c9a", "group": "PT"},
    {"symbol": "ZELDA", "address": "0x01272a2B4B5A7918Bb4AAbD02f4A267329EDe345", "group": "PT"},
    {"symbol": "ZEN", "address": "0xebeCbffA46Eaee7CB3B3305cCE9283cf05CfD1BB", "group": "PT"},
    {"symbol": "TEDDY", "address": "0x91Ab48C4988aE5bbEB02aCB8b5cdBCd8225D7974", "group": "PT"},
    {"symbol": "p402", "address": "0x32241F4EC021A759bAd1087bd72BB26D6fD7fC83", "group": "PT"},
    {"symbol": "VAULT", "address": "0xeB52ac4D25067185f75bab4BcbfBaFA28c876A22", "group": "PT"},
    {"symbol": "SWRM", "address": "0x1E2b066d068eb087CCf85620B8306a283ea70816", "group": "PT"},
    {"symbol": "FIREW", "address": "0x03b4652C8565BC8c257Fbd9fA935AAE41160fc4C", "group": "PT"},
    {"symbol": "SOLIDX", "address": "0x988aCabE384d80454995D6c9e105a4f67eA9947C", "group": "PT"},
    {"symbol": "PIKAJEW", "address": "0x36fc7d749506caa3131fb0c5999d2d364c59498e", "group": "PT"},
    {"symbol": "WHALE", "address": "0x03b1a1b10151733bcefa52178aadf9d7239407b4", "group": "PT"},
    {"symbol": "5555", "address": "0xD4259602922212Afa5f8fbC404fE4664F69f19fC", "group": "PT"},
    {"symbol": "SPACEWHALE", "address": "0x4A04257c9872cDF93850DEe556fEEeDDE76785D4", "group": "PT"},
]

# --- FUNGSI UTILITAS SINKRON ---
def _safe_rpc_call(func):
    try: return func()
    except (ContractLogicError, BadFunctionCallOutput, Exception): return None

def safe_decimals(value, fallback=18):
    try:
        v = int(value)
        return v if 0 < v <= 30 else fallback
    except: return fallback

def get_token_metadata_sync(ca):
    meta = {"Name": "Unknown Token", "Ticker": "TOKEN", "Decimals": 18}
    if not w3: return meta
    try:
        token_contract = w3.eth.contract(address=w3.to_checksum_address(ca), abi=TOKEN_MINIMAL_ABI)
        name = _safe_rpc_call(token_contract.functions.name().call)
        symbol = _safe_rpc_call(token_contract.functions.symbol().call)
        decimals = _safe_rpc_call(token_contract.functions.decimals().call)
        meta["Name"] = name.strip('\x00') if isinstance(name, str) else (name if name is not None else "Unknown Token")
        meta["Ticker"] = symbol.strip('\x00') if isinstance(symbol, str) else (symbol if symbol is not None else "TOKEN")
        meta["Decimals"] = decimals if decimals is not None else 18
    except Exception: pass
    return meta

# --- HELPER FORMATTING & TEXT ---
def human_format(num, decimals=2):
    num = float(num)
    if num == 0: return f"{0:,.{decimals}f}"
    magnitude = 0
    while abs(num) >= 1_000_000_000_000 and magnitude < 4:
        magnitude += 1; num /= 1000.0
    while abs(num) >= 1000 and magnitude < 3:
        magnitude += 1; num /= 1000.0
    suffixes = ['', 'K', 'M', 'B', 'T']
    if magnitude == 0: return f"{num:,.{decimals}f}"
    return f"{round(num, decimals):,.{decimals}f}{suffixes[magnitude]}"

def classify_wallet(total_value_usd):
    if total_value_usd >= 100000: return "🐳 God Whale"
    elif total_value_usd >= 5000: return "🐋 Whale"
    elif total_value_usd >= 2000: return "🦈 Shark"
    elif total_value_usd >= 1000: return "🐬 Dolphine"
    elif total_value_usd >= 500: return "🐟 Fish"
    elif total_value_usd >= 100: return "🦐 Shrimp"
    else: return "🪱 Plankton"
        
def escape_markdown_v2(text: str) -> str:
    if not isinstance(text, str): return ""
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    text = text.replace('\\', '\\\\')
    for char in escape_chars: text = text.replace(char, f'\\{char}')
    return text.replace('\\\\n', '\n')
    
def levenshtein(a: str, b: str) -> int:
    if a == b: return 0
    if not a: return len(b)
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            add = prev[j] + 1; delete = curr[j-1] + 1; change = prev[j-1] + (0 if ca == cb else 1)
            curr.append(min(add, delete, change))
        prev = curr
    return prev[-1]

# --- FUNGSI UTILITAS ASINKRON (Networking/Shared) ---
REQUEST_TIMEOUT = 8

async def _httpx_get(client, url, timeout=REQUEST_TIMEOUT):
    try: return await client.get(url, timeout=timeout)
    except Exception as e:
        logging.debug(f"HTTPX GET error for {url}: {type(e).__name__}: {e}")
        return None

async def query_graphql(url: str, query: str, variables: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(url, json={"query": query, "variables": variables or {}})
            response.raise_for_status()
            data = response.json()
            if data and data.get("data"): return data["data"]
    except Exception as e:
        logging.error(f"GraphQL HTTPX request failed for {url}: {e}"); return None
    return None

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Exception while handling an update:", exc_info=context.error)
    print(f"\n\n🚨 TELEGRAM HANDLER CRASHED! 🚨\nError: {context.error}\n" + "-" * 50)
    if update and update.effective_message:
        await update.effective_message.reply_text(f"❌ \\*Error processing command\\!\\* \nDetail: `{escape_markdown_v2(context.error.__class__.__name__)}`", parse_mode='MarkdownV2')
        
# ==========================
#  HARGA TOKEN VIA SUBGRAPH
# ==========================

async def fetch_prices_from_subgraph(url: str, address_list: List[str]) -> Dict[str, float]:
    """
    Ambil harga token (derivedUSD) dari subgraph PulseX.
    - Hanya baca entitas 'tokens'.
    - Return: {address_lower: price_usd}
    """
    prices: Dict[str, float] = {}

    # Tidak ada alamat = tidak usah query
    if not address_list:
        return prices

    # Normalisasi ke lowercase
    addr_lower = [a.lower() for a in address_list]

    query = """
    query GetTokenPrices($tokenAddresses: [ID!]!) {
      tokens(where: {id_in: $tokenAddresses}, first: 1000) {
        id
        derivedUSD
      }
    }
    """
    variables = {"tokenAddresses": addr_lower}

    data = await query_graphql(url, query, variables)
    if not data:
        return prices

    tokens = data.get("tokens", [])
    for token in tokens:
        addr = (token.get("id") or "").lower()
        raw = token.get("derivedUSD", 0)
        try:
            price = float(raw or 0)
        except (TypeError, ValueError):
            price = 0.0

        if addr and price > 0:
            prices[addr] = price

    return prices


async def fetch_wpls_price_fallback() -> float:
    """
    Fallback khusus WPLS/PLS:
    - Coba ambil harga PLS dari CoinGecko.
    - Kalau gagal, return 0.0 (jadi nilai PLS = 0 di report, tapi bot tidak crash).
    """
    url = "https://api.coingecko.com/api/v3/simple/price?ids=pulsechain&vs_currencies=usd"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            price = float(data.get("pulsechain", {}).get("usd", 0) or 0)
            if price <= 0:
                logging.error("Fallback WPLS price from CoinGecko is 0.")
            return price
    except Exception as e:
        logging.error(f"Failed to fetch WPLS price from fallback API: {e}")
        return 0.0


async def get_prices_graphql_batch(addresses: Set[str]) -> Dict[str, float]:
    """
    Ambil harga token batch dari:
      1) PulseX V2 subgraph
      2) PulseX V1 subgraph (fallback)
      3) Fallback WPLS dari API eksternal (CoinGecko)
    """
    final_prices: Dict[str, float] = {}

    if not addresses:
        return final_prices

    # Normalisasi semua alamat ke lowercase
    all_addrs: Set[str] = {a.lower() for a in addresses if a}
    # Pastikan WPLS selalu ikut di-query
    all_addrs.add(WPLS_CHECKSUM_LOWER)

    addr_list = list(all_addrs)

    # --- Langkah 1: coba PulseX V2 dulu ---
    logging.info("Fetching token prices from PulseX V2 subgraph...")
    try:
        prices_v2 = await fetch_prices_from_subgraph(PULSEX_V2_GRAPHQL_URL, addr_list)
        final_prices.update(prices_v2)
    except Exception as e:
        logging.warning(f"Error fetching prices from V2: {e}")

    # Cek alamat yang masih belum ada harga / 0
    missing = [a for a in all_addrs if final_prices.get(a, 0.0) <= 0]

    # --- Langkah 2: fallback ke PulseX V1 ---
    if missing:
        logging.info(f"Missing {len(missing)} prices from V2. Trying PulseX V1...")
        try:
            prices_v1 = await fetch_prices_from_subgraph(PULSEX_V1_GRAPHQL_URL, missing)
            for addr, price in prices_v1.items():
                if price > 0:
                    final_prices[addr] = price
        except Exception as e:
            logging.warning(f"Error fetching prices from V1: {e}")

    # --- Langkah 3: Fallback khusus WPLS ---
    wpls_price = final_prices.get(WPLS_CHECKSUM_LOWER, 0.0)
    if wpls_price <= 0:
        logging.info("WPLS price not found in subgraphs. Using fallback API...")
        wpls_price = await fetch_wpls_price_fallback()
        if wpls_price > 0:
            final_prices[WPLS_CHECKSUM_LOWER] = wpls_price
        else:
            # Kalau tetap gagal, set 0 tapi log error
            final_prices[WPLS_CHECKSUM_LOWER] = 0.0
            logging.error("Failed to resolve WPLS price from both subgraphs and fallback API.")

    return final_prices
