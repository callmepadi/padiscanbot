# utils.py

import os
import json
import asyncio
import httpx
from web3 import Web3
from web3.exceptions import ContractLogicError, BadFunctionCallOutput, InvalidAddress
from typing import Tuple, Any, Dict, Optional, List
from dotenv import load_dotenv
from telegram.ext import ContextTypes 
from telegram import Update
import logging
import time
import re
from typing import List, Dict, Any

# --- 1. Konfigurasi Global & Konstanta ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PULSECHAIN_RPC_URL = os.getenv("PULSECHAIN_RPC_URL")
PULSESCAN_API_KEY = os.getenv("PULSESCAN_API_KEY") 

HONEY_V2_ADDRESS = os.getenv("HONEY_V2_ADDRESS") 
HONEY_V1_ADDRESS = os.getenv("HONEY_V1_ADDRESS")

# Inisialisasi Web3
w3 = None
if PULSECHAIN_RPC_URL:
    try:
        w3 = Web3(Web3.HTTPProvider(PULSECHAIN_RPC_URL))
    except Exception:
        w3 = None
        logging.error("Web3 init failed.")

PULSESCAN_API_BASE_URL = "https://api.scan.pulsechain.com/api"
SOURCIFY_BASE = "https://sourcify.dev/server"
SOURCIFY_REPO = "https://repo.sourcify.dev/contracts"

# --- ALAMAT KRITIS ---
PULSEX_V2_ROUTER_ADDR = "0x165C3410fC91EF562C50559f7d2289fEbed552d9"
WPLS_ADDRESS = "0xA1077a294dDE1B09bB078844df40758a5D0f9a27"
STABLECOIN_ADDRESS = "0xefD766cCb38EaF1dfd701853BFCe31359239F305"
STABLECOIN_DECIMALS = 18
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


# --- ABI MINIMAL (Digunakan Bersama) ---
ROUTER_ABI_GET_AMOUNTS_OUT = [
    {"constant": True, "inputs": [{"internalType": "uint256", "name": "amountIn", "type": "uint256"}, {"internalType": "address[]", "name": "path", "type": "address[]"}], "name": "getAmountsOut", "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}], "stateMutability": "view", "type": "function"}
]
TOKEN_MINIMAL_ABI = [
    {"constant": True, "inputs": [], "name": "owner", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [{"internalType": "address", "name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"internalType":"uint8","name":"","type":"uint8"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"}
]
FACTORY_ABI_MINIMAL = [
    {"inputs":[{"internalType":"address","name":"tokenA","type":"address"},{"internalType":"address","name":"tokenB","type":"address"}],"name":"getPair","outputs":[{"internalType":"address","name":"pair","type":"address"}],"stateMutability":"view", "type":"function"}
]
ROUTER_V2_ABI_COMBINED = [
    {"inputs":[],"name":"factory","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view", "type":"function"},
    {"inputs":[{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"address[]","name":"path","type":"address[]"}],"name":"getAmountsOut","outputs":[{"internalType":"uint256[]","name":"amounts","type":"uint256[]"}],"stateMutability":"view","type":"function"},
]
HONEY_ABI_MINIMAL = [
    {
        "inputs": [{"internalType": "address", "name": "token", "type": "address"}],
        "name": "checkHoneyMain",
        "outputs": [
            {"internalType": "uint256", "name": "buyEstimate", "type": "uint256"},
            {"internalType": "uint256", "name": "buyReal", "type": "uint256"},
            {"internalType": "uint256", "name": "sellEstimate", "type": "uint256"},
            {"internalType": "uint256", "name": "sellReal", "type": "uint256"},
            {"internalType": "bool", "name": "buy", "type": "bool"},
            {"internalType": "bool", "name": "sell", "type": "bool"},
            {"internalType": "uint256", "name": "blockNumber", "type": "uint256"}
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]


# --- HARGA FALLBACK & STANDAR ERC20 ---
PLS_FALLBACK_PRICE = 0.0000001
PLS_FALLBACK_PRICE_DISPLAY = "N/A (Price Unknown)"
SCAN_MODE = "balanced"   # set to "strict" if you REALLY want only the 4 lines when admin exists
STANDARD_ERC20_FUNCTIONS = {
    'totalSupply', 'balanceOf', 'transfer', 'transferFrom', 'approve', 'allowance', 'name', 'symbol', 'decimals', 'owner', 'increaseAllowance', 'decreaseAllowance', 'getTokenHolders', 'burn', 'burnFrom' 
}
IGNORED_ADMIN_VARS = {"owner", "_owner", "spender", "msgSender", "burnAddress", "recipient", "to", "from", "getFees"}
SAFE_SETTER_EXCLUDES = {"transferownership", "_transferownership"}

# --- DAFTAR TOKEN WAJIB (HARDCODED) ---
BASIC_TOKENS_LIST = [
    {"symbol": "TEDDY", "address": "0xd6c31bA0754C4383A41c0e9DF042C62b5e918f6d", "group": "BASIC"},
    {"symbol": "pTGC", "address": "0x94534EeEe131840b1c0F61847c572228bdfDDE93", "group": "BASIC"},
    {"symbol": "INC", "address": "0xf808bb6265e9ca27002c0a04562bf50d4fe37eaa", "group": "BASIC"},
    {"symbol": "PLSX", "address": "0x95B303987A60C71504D99Aa1b13B4DA07b0790ab", "group": "BASIC"},
    {"symbol": "pHEX", "address": "0x2b591e99afE9f32eAA6214f7B7629768c40Eeb39", "group": "BASIC"},
    {"symbol": "SOLIDX", "address": "0x8Da17Db850315A34532108f0f5458fc0401525f6", "group": "BASIC"},
    {"symbol": "eDAI", "address": "0xefD766cCb38EaF1dfd701853BFCe31359239F305", "group": "BASIC"},
    {"symbol": "USDC", "address": "0x15D38573d2feeb82e7ad5187aB8c1D52810B1f07", "group": "BASIC"},
    {"symbol": "WETH", "address": "0x02DcdD04e3F455D838cd1249292C58f3B79e3C3C", "group": "BASIC"},
    {"symbol": "pDAI", "address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "group": "BASIC"},
    {"symbol": "DTO", "address": "0xc438437218009EDD656d319689c902aE56b4b96F", "group": "BASIC"},
    {"symbol": "FIRE", "address": "0xf330cb1d41052dbC74D3325376Cb82E99454e501", "group": "BASIC"},
    {"symbol": "AXIS", "address": "0x8BDB63033b02C15f113De51EA1C3a96Af9e8ecb5", "group": "BASIC"},
    {"symbol": "eHEX", "address": "0x57fde0a71132198BBeC939B98976993d8D89D225", "group": "BASIC"},
    {"symbol": "UFO", "address": "0x456548A9B56eFBbD89Ca0309edd17a9E20b04018", "group": "BASIC"},
    {"symbol": "USDT", "address": "0x0Cb6F5a34ad42ec934882A05265A7d5F59b51A2f", "group": "BASIC"},
    {"symbol": "WBNB", "address": "0x518076CCE3729eF1a3877EA3647a26e278e764FE", "group": "BASIC"},
    {"symbol": "pWBTC", "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "group": "BASIC"},
    {"symbol": "WBTC", "address": "0xb17D901469B9208B17d916112988A3FeD19b5cA1", "group": "BASIC"},
    {"symbol": "pWETH", "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "group": "BASIC"},
    {"symbol": "TRC", "address": "0xe2892C876c5e52a4413Ba5f373D1a6E5f2e9116D", "group": "BASIC"},
    {"symbol": "ALIVE", "address": "0xb0ebaf9378d6e7531ba09403a12636947cc2f84b", "group": "BASIC"},
    {"symbol": "GEL", "address": "0x616cb6a245Ed4c11216Ec58D10B6A2E87271845d", "group": "BASIC"},
    {"symbol": "SCADA", "address": "0x69e23263927Ae53E5FF3A898d082a83B7D6fB438", "group": "BASIC"},
    {"symbol": "🎭", "address": "0x2401E09acE92C689570a802138D6213486407B24", "group": "BASIC"},
    {"symbol": "🖨", "address": "0x770CFA2FB975E7bCAEDDe234D92c3858C517Adca", "group": "BASIC"},
    {"symbol": "BLSEYE🎯", "address": "0xeAb7c22B8F5111559A2c2B1A3402d3FC713CAc27", "group": "BASIC"},
    {"symbol": "Finvesta", "address": "0x1C81b4358246d3088Ab4361aB755F3D8D4dd62d2", "group": "BASIC"},
    {"symbol": "OOF", "address": "0x9B334c49821d36D435e684e7CB9b564b328126e5", "group": "BASIC"},
    {"symbol": "X", "address": "0xA6C4790cc7Aa22CA27327Cb83276F2aBD687B55b", "group": "BASIC"},
]

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
]

HARDCODED_MAP = {t['address']: (t['symbol'], t['group']) for t in BASIC_TOKENS_LIST + PT_TOKENS_LIST}


# --- FUNGSI UTILITAS SINKRON (RPC Calls) ---

def _safe_rpc_call(func):
    """Wraps Web3.py calls to return None if an RPC exception occurs."""
    try:
        return func()
    except (ContractLogicError, BadFunctionCallOutput, Exception) as e:
        return None

def safe_decimals(value, fallback=18):
    """Safely converts value to int for decimals."""
    try:
        v = int(value)
        return v if 0 < v <= 30 else fallback
    except:
        return fallback

def get_token_metadata_sync(ca):
    """Fetches Name, Ticker, and Decimals from contract (used by PadiScan)."""
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
    except Exception:
        pass
    return meta

def get_pls_price_from_lp_sync():
    """Fetches PLS/USD price from On-Chain LP (WPLS -> Stablecoin) synchronously."""
    if not w3: return 0.0
    try:
        amount_in = 10**18
        path = [w3.to_checksum_address(WPLS_ADDRESS), w3.to_checksum_address(STABLECOIN_ADDRESS)]
        router = w3.eth.contract(address=w3.to_checksum_address(PULSEX_V2_ROUTER_ADDR), abi=ROUTER_ABI_GET_AMOUNTS_OUT)
        amounts = router.functions.getAmountsOut(amount_in, path).call()
        pls_price = amounts[1] / (10 ** STABLECOIN_DECIMALS)
        return pls_price
    except Exception as e:
        logging.warning(f"LP Price Calc for PLS failed: {e}")
        return 0.0

def get_erc20_price_from_lp_sync(contract_address, token_decimals):
    """Fetches Token/PLS price ratio from On-Chain LP (Token -> WPLS) synchronously."""
    if not w3: return 0.0
    try:
        amount_in = 10**safe_decimals(token_decimals, fallback=18)
        path = [w3.to_checksum_address(contract_address), w3.to_checksum_address(WPLS_ADDRESS)]
        router = w3.eth.contract(address=w3.to_checksum_address(PULSEX_V2_ROUTER_ADDR), abi=ROUTER_ABI_GET_AMOUNTS_OUT)
        amounts = router.functions.getAmountsOut(amount_in, path).call()
        token_pls_ratio = amounts[1] / (10 ** 18)
        return token_pls_ratio
    except Exception as e:
        logging.warning(f"LP Price Calc for ERC20 failed for {contract_address}: {e}")
        return 0.0

# --- FUNGSI PADI SCAN UTILS SINKRON (Lainnya) ---

def _extract_abi_from_sourcify_response(info: Dict[str, Any]) -> Optional[Tuple[List[Dict[str, Any]], Any]]:
    """
    Ekstrak ABI dan Source Code dari respons Sourcify (v2/contract).
    """
    
    files = info.get("files") or {}
    metadata_obj = files.get("metadata") or info.get("metadata")
    source = info.get("files", {}).get("source") or info.get("files", {}).get("sources")

    # --- 1. Coba jalur spesifik metadata.output.contracts (UTAMA, Standard JSON) ---
    if isinstance(metadata_obj, dict):
        try:
            contracts_map = metadata_obj.get("output", {}).get("contracts")
            if isinstance(contracts_map, dict):
                for contract_file_data in contracts_map.values():
                    if isinstance(contract_file_data, dict):
                        for contract_info in contract_file_data.values():
                            abi_list = contract_info.get("abi")
                            if isinstance(abi_list, list) and abi_list:
                                return abi_list, source
        except Exception:
            pass # Lanjutkan ke fallback

    # --- 2. Coba fallback sederhana: output.abi (Paling mungkin gagal jika stringified) ---
    if isinstance(metadata_obj, dict):
        fallback_abi_output = metadata_obj.get("output", {}).get("abi")
        if isinstance(fallback_abi_output, list) and fallback_abi_output:
            return fallback_abi_output, source

    # --- 3. Coba fallback di root response atau file (PENTING: menangani stringified JSON) ---
    root_abi = info.get("abi") or info.get("verified", {}).get("abi")
    
    # KASUS KRITIS: Coba parse jika berupa string
    if isinstance(root_abi, str):
        try:
            parsed = json.loads(root_abi)
            if isinstance(parsed, list):
                root_abi = parsed
        except Exception:
            # Jika gagal parse, kita anggap root_abi tidak valid/None
            root_abi = None 

    if isinstance(root_abi, list) and root_abi:
        return root_abi, source
        
    return None, source # ABI benar-benar tidak ditemukan

def human_format(num, decimals=2):
    """Converts a number to K, M, B format."""
    num = float(num)
    if num == 0:
        return f"{0:,.{decimals}f}"

    magnitude = 0
    while abs(num) >= 1_000_000_000_000 and magnitude < 4:
        magnitude += 1
        num /= 1000.0

    while abs(num) >= 1000 and magnitude < 3:
        magnitude += 1
        num /= 1000.0

    suffixes = ['', 'K', 'M', 'B', 'T']
    if magnitude == 0:
        return f"{num:,.{decimals}f}"
    return f"{round(num, decimals):,.{decimals}f}{suffixes[magnitude]}"

# utils.py

# ... (Kode import dan konfigurasi awal) ...

# ... (Fungsi human_format) ...
#def human_format(num, decimals=2):
# ... (isi fungsi human_format) ...

# --- FUNGSI CLASSIFY_WALLET (revisi/konfirmasi) ---
def classify_wallet(total_value_usd):
    """Classifies the wallet based on total USD value."""
    if total_value_usd >= 100000:
        return "🐳 God Whale"
    elif total_value_usd >= 5000:
        return "🐋 Whale"
    elif total_value_usd >= 2000:
        return "🦈 Shark"
    elif total_value_usd >= 1000:
        return "🐬 Dolphine"
    elif total_value_usd >= 500:
        return "🐟 Fish"
    elif total_value_usd >= 100:
        return "🦐 Shrimp"
    else:
        return "🪱 Plankton"
# --- AKHIR CLASSIFY_WALLET ---
        
# --- FUNGSI ESCAPE MARKDOWN BARU ---
def escape_markdown_v2(text: str) -> str:
    """Escapes common Markdown V2 characters (used by Telegram API)."""
    if not isinstance(text, str):
        return ""
    # Only escape characters that are NOT inside a triple backtick (code block)
    # This is a robust escaping strategy for Markdown V2.
    text = text.replace('\\', '\\\\')
    for char in ['*', '_', '`', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
        text = text.replace(char, f'\\{char}')
    return text.replace('\\\\n', '\n') # un-escape newlines if any
# --- AKHIR ESCAPE MARKDOWN ---

# --- FUNGSI CALCULATE_LP_BURNT_PERCENT_SYNC (revisi/konfirmasi) ---
def calculate_lp_burnt_percent_sync(lp_address):
    if not w3: return 0.0, 0, 0
    try:
        lp_contract = w3.eth.contract(address=lp_address, abi=TOKEN_MINIMAL_ABI)
        lp_total_supply = _safe_rpc_call(lp_contract.functions.totalSupply().call)
        if lp_total_supply is None or lp_total_supply == 0:
            return 0.0, 0, 0
        lp_total_burnt_balance = sum(_safe_rpc_call(lambda: lp_contract.functions.balanceOf(a).call()) or 0 for a in BURN_ADDRESSES_CHECKSUM)
        percent_burnt = (lp_total_burnt_balance / lp_total_supply) * 100
        return percent_burnt, lp_total_burnt_balance, lp_total_supply
    except Exception:
        return 0.0, 0, 0
# --- AKHIR CALCULATE_LP_BURNT_PERCENT_SYNC ---

# ... (lanjutkan fungsi sinkron lainnya seperti scan_and_rank_wpls_pairs_sync, dll.) ...

def scan_and_rank_wpls_pairs_sync(token_address):
    if not w3 or not WPLS_CHECKSUM: return None, None 
    routers = {"PulseX V2": PULSEX_V2_ROUTER_ADDR, "PulseX V1": "0x98bf93ebf5c380C0e6Ae8e192A7e2AE08edAcc02"} 
    token_checksum = w3.to_checksum_address(token_address)
    best_lp = {"address": None, "source": None, "burnt_percent": -1.0}
    for source, router_addr in routers.items():
        try:
            router_contract = w3.eth.contract(address=w3.to_checksum_address(router_addr), abi=ROUTER_V2_ABI_COMBINED)
            factory_address = _safe_rpc_call(router_contract.functions.factory().call)
            if not factory_address: continue
            factory_contract = w3.eth.contract(address=w3.to_checksum_address(factory_address), abi=FACTORY_ABI_MINIMAL)
            lp_address = _safe_rpc_call(lambda: factory_contract.functions.getPair(token_checksum, WPLS_CHECKSUM).call())
            if lp_address and int(lp_address, 16) != 0:
                lp_address_checksum = w3.to_checksum_address(lp_address)
                burnt_percent, _, _ = calculate_lp_burnt_percent_sync(lp_address_checksum)
                if burnt_percent > best_lp["burnt_percent"]:
                    best_lp["burnt_percent"] = burnt_percent
                    best_lp["address"] = lp_address_checksum
                    best_lp["source"] = source
        except Exception as e:
            logging.warning(f"LP Ranking failed for {source}: {e}")
            continue
    return best_lp["address"], best_lp["source"]

def extra_scan_source_patterns(source_code: str, sus_list: list, detailed_flags: list = None):
    """
    Heuristics to reveal obfuscated admin/backdoor patterns.
    - Only flags state (persistent) variables assigned to msg.sender/_msgSender()
    - Detect admin checks using custom admin var (var == msg.sender / var != msg.sender)
    - Detect XOR-zeroing patterns (var = var ^ var)
    - Detect full-balance wipe patterns, _totalSupply modifications, mapping flags (balancesto/balancesfrom)
    - Detect obscure revert strings and _Holders usage
    """
    if not isinstance(source_code, str) or not source_code:
        return

    s = source_code

    # ---------- identify state (contract-level) variables ----------
    # Rough regex: look for declarations like:
    #   address private cjxxx;
    #   address public owner = 0x...
    #   mapping(address => bool) private flags;
    state_var_pattern = r"(?:^|\n)\s*(?:address|bool|uint\d*|mapping\s*\([^\)]*\))\s+(?:public|private|internal|external)?\s*([A-Za-z0-9_]{3,40})\s*(?:=|;)"
    state_vars_found = set(re.findall(state_var_pattern, s, flags=re.M))

    # ---------- 1) admin variable assigned to msg.sender/_msgSender() but only if state var ----------
    admin_assigns = re.findall(r"([A-Za-z0-9_]{3,40})\s*=\s*(_?msgSender\(\)|msg\.sender)\s*;", s)
    for var, _fn in admin_assigns:
        if var not in state_vars_found:
            # likely a local variable; skip
            continue
        sus_list.append(f"🔴 Admin variable detected: `{var}` assigned to msg.sender/_msgSender()")
        if detailed_flags is not None:
            detailed_flags.append({"type":"admin_var", "var": var})

    # ---------- 2) admin checks comparing var with msg.sender ----------
    checks = re.findall(r"([A-Za-z0-9_]{3,40})\s*(!=|==)\s*msg\.sender", s)
    for var, op in checks:
        # flag only if var is a state variable OR appears to be used widely in contract (simple heuristic)
        if var in state_vars_found or len(re.findall(r"\b" + re.escape(var) + r"\b", s)) > 4:
            sus_list.append(f"🔴 Access-check using custom admin var `{var}` with operator `{op}`")
            if detailed_flags is not None:
                detailed_flags.append({"type":"admin_check", "var": var, "op": op})

    # ---------- 3) XOR-with-self patterns (zeroing balances) ----------
    # exact same-variable XOR: x = x ^ x
    if re.search(r"\b([A-Za-z0-9_]{2,40})\s*=\s*\1\s*\^\s*\1\b", s):
        sus_list.append("🔴 XOR-with-self pattern detected (likely zeroing balances via `x = x ^ x`)")
        if detailed_flags is not None:
            detailed_flags.append({"type":"xor_zeroing"})

    # generic var = var ^ var (approx match)
    if re.search(r"\b([A-Za-z0-9_]{2,40})\s*=\s*[A-Za-z0-9_]{2,40}\s*\^\s*[A-Za-z0-9_]{2,40}", s):
        sus_list.append("🔴 Potential bitwise-zeroing pattern found (var = var ^ var)")
        if detailed_flags is not None:
            detailed_flags.append({"type":"xor_like"})

    # ---------- 4) detect removing full user balance (deduct pattern) ----------
    if re.search(r"deductAmount\s*=\s*balances\[[^\]]+\]\s*;|balances\[[^\]]+\]\s*-\=\s*deductAmount", s):
        sus_list.append("🔴 Function that deducts entire balances[caller] detected (possible rug/burn user balances)")
        if detailed_flags is not None:
            detailed_flags.append({"type":"burn_entire_balance"})

    # ---------- 5) detect _totalSupply modifications / balances[...] += ... (possible mint) ----------
    if re.search(r"_totalSupply\s*[\+\-\*]?=|balances\[[^\]]+\]\s*\+\=\s*[A-Za-z0-9_]+", s):
        sus_list.append("🔴 Modifies _totalSupply or increases balances in code (possible hidden mint)")
        if detailed_flags is not None:
            detailed_flags.append({"type":"mint_like"})

    # ---------- 6) mapping flags likely used to freeze/zero balances ----------
    if re.search(r"\b(balancesto|balancesfrom|blacklist|blocklist|isBlocked|isBanned)\b", s, flags=re.I):
        sus_list.append("🔴 Mapping flags (balancesto/balancesfrom/blacklist) found — may be used to freeze or zero balances")
        if detailed_flags is not None:
            detailed_flags.append({"type":"mapping_flags"})

    # ---------- 7) short obscure revert strings (obfuscation) ----------
    if re.search(r"revert\(\s*\"[^\"]{1,6}\"\s*\)", s):
        sus_list.append("🟡 Short/obscure revert strings found (developer tried to hide reason)")
        if detailed_flags is not None:
            detailed_flags.append({"type":"short_revert"})

    # ---------- 8) _Holders array / getTokenHolders usage ----------
    if re.search(r"_Holders\s*\[", s) or re.search(r"getTokenHolders\s*\(", s):
        sus_list.append("🟡 Contract collects token holder addresses (useful for targeted rug)")
        if detailed_flags is not None:
            detailed_flags.append({"type":"holders_list"})
            
    # ---------- X) detect fake/obfuscated renounce + owner mint pattern ----------
    # catch misspelled renounce functions (renounceownersip, renounceownershIp, etc.)
    if re.search(r"function\s+[A-Za-z0-9_]*renounc[e|i][A-Za-z0-9_]*\s*\(", s, flags=re.I):
        sus_list.append("🔴 Suspicious renounce-like function name found (possible obfuscated owner mint/privilege)")
        if detailed_flags is not None:
            detailed_flags.append({"type":"renounce_like"})

    # detect pattern: _balances[_msgSender()] += totalSupply() * <big factor>
    if re.search(r"_balances\s*\[\s*_?msgSender\(\)\s*\]\s*\+\=\s*totalSupply\s*\(\s*\)\s*\*\s*[0-9]{2,}", s):
        sus_list.append("🔴 Owner mint via renounce-like function detected (`_balances[_msgSender()] += totalSupply() * N`)")
        if detailed_flags is not None:
            detailed_flags.append({"type":"owner_mint_totalSupply_mul"})

    # detect mapping-based blacklist + special transfer logic (ddsa, balancesto, blacklist)
    if re.search(r"\b(ddsa|balancesto|balancesfrom|blacklist|isBlocked|isBanned)\b", s, flags=re.I):
        sus_list.append("🔴 Blacklist/flag mapping + custom transfer logic found (may lock/zero user balances)")
        if detailed_flags is not None:
            detailed_flags.append({"type":"mapping_flag_transfer"})

    # detect kill window pattern: setting a kill time and conditional burn in transfer
    if re.search(r"_killEndTime|killEndTime", s) and re.search(r"block\.timestamp\s*<=\s*_killEndTime", s):
        sus_list.append("🔴 Kill-window logic detected (temporary burn/zeroing of transfers during time window)")
        if detailed_flags is not None:
            detailed_flags.append({"type":"kill_window"})

    return


def scan_suspicious_features_sync(contract, source_code: str = None) -> List[str]:
    """
    Final scanner implementing rule:
      - If admin-state-var (assigned to msg.sender/_msgSender()) detected, force recolor all function '🟢' -> '🔴'
      - Do NOT let any 'owner==0x0' or 'ownership renounced' logic override recolor when admin var present.
      - Otherwise behave in balanced compact mode.
    """
    abi = getattr(contract, "abi", None) or []
    addr_perm_msgs = []
    critical_msgs = []
    fee_tax_msgs = []
    setter_like_msgs = []

    def is_address_param(p): return p.get("type","").startswith("address")
    def is_bool_param(p): return p.get("type","") == "bool"
    def is_uint_param(p): return p.get("type","").startswith("uint")

    # collect ABI info (non-ERC20) with priority + dedupe
    # priority order (lower number = higher priority)
    PRIORITY = {
        "critical": 0,
        "addr_perm": 1,
        "fee_tax": 2,
        "setter": 3,
        "other": 4
    }
    seen_funcs = {}  # name -> chosen_tag
    fee_tax_count = 0
    setter_count = 0

    for f in abi:
        if f.get("type") != "function":
            continue
        name = f.get("name","") or ""
        lname = name.lower()
        inputs = f.get("inputs",[]) or []

        if name in STANDARD_ERC20_FUNCTIONS:
            continue

        # determine tag and its priority
        tag = None
        tag_priority = PRIORITY["other"]

        # critical (highest)
        if "transfertoburn" in lname or lname == "transfertoburn":
            tag = "critical"
            tag_priority = PRIORITY["critical"]

        # fee/tax heuristics
        elif any(k in lname for k in ("fee","tax","settax","setfee","gettax","getfee","treasury","marketing","liquidity")):
            tag = "fee_tax"
            tag_priority = PRIORITY["fee_tax"]

        # address,bool or address,uint permission patterns
        elif len(inputs) >= 2 and is_address_param(inputs[0]) and (is_bool_param(inputs[1]) or is_uint_param(inputs[1])):
            tag = "addr_perm"
            tag_priority = PRIORITY["addr_perm"]

        # setter-like names (lower priority than addr_perm so it won't override)
        elif re.match(r'^(set|enable|disable|update|grant|revoke|transfer|withdraw|mint|burn)', name, flags=re.I):
            if name.lower() not in SAFE_SETTER_EXCLUDES:
                tag = "setter"
                tag_priority = PRIORITY["setter"]

        # decide whether to record/override based on priority
        prev_tag = seen_funcs.get(name)
        prev_priority = PRIORITY.get(prev_tag, PRIORITY["other"]) if prev_tag else None

        if prev_tag is None or (prev_priority is not None and tag_priority < prev_priority):
            # accept/override this function's tag
            if tag == "critical":
                cm = f"🔴 Critical Control Function: {name}"
                if cm not in critical_msgs:
                    critical_msgs.append(cm)
            elif tag == "addr_perm":
                # guard: ensure we have at least two inputs to display types
                t0 = inputs[0].get('type') if len(inputs) >= 1 else "address"
                t1 = inputs[1].get('type') if len(inputs) >= 2 else "?"
                s = f"🟢 Address Permission Control: {name}({t0},{t1})"
                if s not in addr_perm_msgs:
                    addr_perm_msgs.append(s)
            elif tag == "fee_tax":
                fee_tax_count += 1
                if fee_tax_count <= 6:
                    fee_tax_msgs.append(f"🟡 Fee/Limit/Tax control: {name}")
            elif tag == "setter":
                setter_count += 1
                if setter_count <= 8:
                    setter_like_msgs.append(f"🟡 Setter-like: {name}")
            # mark chosen tag
            if tag:
                seen_funcs[name] = tag
        else:
            # lower-priority tag ignored to avoid duplicate explanations
            continue

    # ---------- detect admin-state-vars (strong signal) ----------
    admin_vars = set()
    owner_access_pattern = False
    if isinstance(source_code, str) and source_code:
        s = source_code

        # find state variable declarations (contract-level)
        state_var_pattern = r"(?:^|\n)\s*(?:address|bool|uint\d*|mapping\s*\([^\)]*\))\s+(?:public|private|internal|external)?\s*([A-Za-z0-9_]{3,60})\s*(?:=|;)"
        state_vars_found = set(re.findall(state_var_pattern, s, flags=re.M))

        # assignments to msg.sender/_msgSender()
        assigns = re.findall(r"([A-Za-z0-9_]{3,60})\s*=\s*(_?msgSender\(\)|msg\.sender)\s*;", s)

        # explicit admin checks (== or !=)
        checks = set(re.findall(r"([A-Za-z0-9_]{3,60})\s*(?:==|!=)\s*msg\.sender", s))

        # Mark admin only if:
        # - var declared as state variable
        # - var assigned to msg.sender/_msgSender()
        # - var appears in explicit check (== or != msg.sender)
        for var, _fn in assigns:
            if var in state_vars_found and var in checks and var not in IGNORED_ADMIN_VARS:
                admin_vars.add(var)

        # owner/access pattern for compact hints when no admin var
        if "onlyowner" in s.lower() or "accesscontrol" in s.lower() or "default_admin_role" in s.lower() or "owner()" in s:
            owner_access_pattern = True

    # ---------- utility recolor (green -> red) ----------
    def recolor_green_to_red(messages: List[str]) -> List[str]:
        return [m.replace("🟢", "🔴", 1) if m.startswith("🟢") else m for m in messages]

    # ---------- If any admin-vars found: FORCE recolor & ignore owner==0 safety ----------
    if admin_vars:
        out = []
        # collect function items (addr perms) and critical
        out.extend(addr_perm_msgs)
        out.extend(critical_msgs)
        # show admin var lines (keep them visually clear; you can change emoji if you want them red too)
        for v in sorted(admin_vars):
            out.append(f"🚩 Admin Variable Detected: `{v}` assigned to multiple-ownership")

        # now force recolor of function items (🟢 -> 🔴)
        out = recolor_green_to_red(out)

        # balanced mode: also add short summaries (optional)
        if SCAN_MODE != "strict":
            if fee_tax_count:
                out.append(f"🟡 Fee/Tax related functions detected: {fee_tax_count} (showing up to 6)")
            if setter_count:
                out.append(f"🟡 Setter-like functions detected: {setter_count} (showing up to 8)")
            # we do NOT append owner-renounced safety here; admin presence overrides safety

        # dedupe & return (preserve order)
        seen2 = set(); final = []
        for x in out:
            if x not in seen2:
                seen2.add(x); final.append(x)
        return final
        
            # ---------- EXTRA: Detect scam patterns from source (kill-window, blacklist, fake-renounce, owner-mint) ----------

        # ---------- SMART, NAME-AGNOSTIC SOURCE DETECTORS ----------
    if isinstance(source_code, str) and source_code:
        s = source_code

        # --- helpers ---
        def levenshtein(a: str, b: str) -> int:
            if a == b: return 0
            if not a: return len(b)
            if not b: return len(a)
            prev = list(range(len(b) + 1))
            for i, ca in enumerate(a, start=1):
                curr = [i]
                for j, cb in enumerate(b, start=1):
                    add = prev[j] + 1
                    delete = curr[j-1] + 1
                    change = prev[j-1] + (0 if ca == cb else 1)
                    curr.append(min(add, delete, change))
                prev = curr
            return prev[-1]

        # --- 1) find state vars that get assigned to msg.sender (owner-like aliases) ---
        owner_like_vars = set()
        for m in re.finditer(r"([A-Za-z0-9_]{3,80})\s*=\s*(?:_?msgSender\(\)|msg\.sender)\s*;", s):
            owner_like_vars.add(m.group(1))

        # Also treat direct use of _msgSender()/msg.sender as owner candidate
        use_msg_sender_direct = bool(re.search(r"\b_msgSender\(\)\b|\bmsg\.sender\b", s))

        # --- 2) find mapping(address => bool) names (possible blacklist flags) ---
        mapping_names = set(re.findall(r"mapping\s*\(\s*address\s*=>\s*bool\s*\)\s*([A-Za-z0-9_]{3,80})\s*;", s, flags=re.I))

        # --- 3) extract a plausible transfer/internaltransfer function body (if present) ---
        transfer_body = ""
        # try multiple common names, capture up to reasonable length
        tf = re.search(r"function\s+(_?internaltransfer|_transfer|internalTransfer|transferFrom|transfer)[^\{]*\{([\s\S]{0,4000}?)\}", s, flags=re.I)
        if tf:
            transfer_body = tf.group(2)

        # --- 4) Owner-mint detection that is name-agnostic ---
        # check for patterns like: balances[<owner-like or _msgSender()>] += totalSupply() * NUMBER
        mint_patterns = []
        # if owner_like_vars exist, check for them
        for var in owner_like_vars:
            pat = re.compile(rf"_balances\s*\[\s*{re.escape(var)}\s*\]\s*\+\=\s*totalSupply\s*\(\s*\)\s*\*\s*([0-9_]+)", flags=re.I)
            m = pat.search(s)
            if m:
                try:
                    mult = int(m.group(1).replace("_", ""))
                except Exception:
                    mult = None
                mint_patterns.append(("var", var, mult))

        # check for direct msg.sender target
        m2 = re.search(r"_balances\s*\[\s*(?:_?msgSender\(\)|msg\.sender)\s*\]\s*\+\=\s*totalSupply\s*\(\s*\)\s*\*\s*([0-9_]+)", s, flags=re.I)
        if m2:
            try:
                mult = int(m2.group(1).replace("_", ""))
            except Exception:
                mult = None
            mint_patterns.append(("direct", "_msgSender/msg.sender", mult))

        # also detect patterns where they call totalSupply() then assign to local and use that local multiplied:
        # e.g. uint256 amount = totalSupply(); balances[msg.sender] += amount * 75000;
        m3 = re.search(r"([A-Za-z0-9_]{3,80})\s*=\s*totalSupply\s*\(\s*\)\s*;", s)
        if m3:
            var_total = m3.group(1)
            pat2 = re.compile(rf"_balances\s*\[\s*(?:_?msgSender\(\)|msg\.sender)\s*\]\s*\+\=\s*{re.escape(var_total)}\s*\*\s*([0-9_]+)", flags=re.I)
            m4 = pat2.search(s)
            if m4:
                try:
                    mult = int(m4.group(1).replace("_", ""))
                except Exception:
                    mult = None
                mint_patterns.append(("indirect", var_total, mult))

        for kind, target, mult in mint_patterns:
            if mult is None:
                critical_msgs.append(f"🚩 Owner-mint pattern detected targeting {target} (multiplier unparsable)")
            else:
                if mult >= 10:  # threshold: multiplier >= 10 is very suspicious
                    critical_msgs.append(f"🚩 Owner mint exploit detected targeting {target} (multiplier={mult})")
                else:
                    fee_tax_msgs.append(f"🚩 Small owner-mint-like pattern found (multiplier={mult})")

        # --- 5) punitive amount adjustment detection in transfer body (name-agnostic) ---
        if transfer_body:
            # look for amount = amount - (balance * N) or amount = amount - balance * N
            if re.search(r"amount\s*=\s*amount\s*-\s*\(?\s*_?balances?\s*\[\s*[^\]]+\s*\]\s*\*\s*[0-9_]+", transfer_body, flags=re.I) \
               or re.search(r"amount\s*=\s*_?balances?\s*\[[^\]]+\]\s*\*\s*[0-9_]+", transfer_body, flags=re.I) \
               or re.search(r"amount\s*=\s*amount\s*-\s*\([^\)]*balance[^\)]*\)", transfer_body, flags=re.I):
                critical_msgs.append("🚩 Punitive transfer logic detected (amount reduced based on balance)")

            # detect mapping conditional used to punish: if (M[from]) { ... amount = amount - ... }
            for mn in mapping_names:
                if re.search(rf"\b{re.escape(mn)}\s*\[", transfer_body):
                    # check for amount modification near usage (within 300 chars)
                    for match in re.finditer(rf"({re.escape(mn)}\s*\[[^\]]+\])", transfer_body):
                        span_start = match.start()
                        span_end = span_start + 300
                        context = transfer_body[span_start:span_end]
                        if re.search(r"amount\s*=\s*amount|amount\s*-[=]?", context, flags=re.I) or re.search(r"_balances?\s*\[", context):
                            critical_msgs.append(f"🚩 Mapping '{mn}' used to conditionally modify amount/balances in transfer")

        # --- 6) kill-window detection robust: require var set AND used in conditional ---
        # find assignment like: someVar = block.timestamp + NUM (we allow many variable names)
        kill_assigns = re.findall(r"([A-Za-z0-9_]{3,80})\s*=\s*block\.timestamp\s*\+\s*([0-9_]+)", s, flags=re.I)
        for kv in kill_assigns:
            varname = kv[0]
            # search usage in conditional
            if re.search(rf"block\.timestamp\s*(?:<=|<|>=|>)\s*{re.escape(varname)}", s) or re.search(rf"{re.escape(varname)}\s*(?:>=|>|<=|<)\s*block\.timestamp", s):
                critical_msgs.append("🚩 Kill-window logic detected (time var set and used in conditional)")

        # --- 7) fuzzy renounce function names (avoid false positives) ---
        for m in re.finditer(r"function\s+([A-Za-z0-9_]{3,80})\s*\(", s, flags=re.I):
            fname = m.group(1)
            fname_lower = fname.lower()
            if "renounce" in fname_lower and "ownership" not in fname_lower:
                dist = levenshtein(fname_lower, "renounceownership")
                if dist <= 3:
                    critical_msgs.append(f"🚩 Obfuscated renounce-like function name detected: {fname} (lev={dist})")
                else:
                    # less confident but mention
                    fee_tax_msgs.append(f"🚩 Renounce-like function name (unusual): {fname}")

        # --- 8) owner-only function that mints/checks totalSupply: if a function uses onlyOwner and performs mint to msg.sender, flag ---
        # find functions that have 'onlyOwner' modifier and inside contain balances[...] += ...totalSupply
        for m in re.finditer(r"function\s+([A-Za-z0-9_]{3,80})[^\{]*\{([\s\S]{0,2000}?)\}", s, flags=re.I):
            fname, fbody = m.group(1), m.group(2)
            if re.search(r"\bonlyOwner\b|\bonlyowner\b", m.group(0) + fbody, flags=re.I):
                if re.search(r"_balances\s*\[\s*(?:_?msgSender\(\)|msg\.sender|[A-Za-z0-9_]{3,80})\s*\]\s*\+\=\s*totalSupply\s*\(", fbody, flags=re.I) \
                   or re.search(r"totalSupply\s*\(\s*\)\s*;[\s\S]{0,200}[\+\*0-9_]", fbody, flags=re.I):
                    critical_msgs.append(f"🚩 Owner-only function '{fname}' mints/assigns large supply to owner")

    # ---------- END SMART DETECTORS ----------
    # ---------- No admin-vars: normal compact fallback ----------
    combined = []
    combined.extend(addr_perm_msgs)
    combined.extend(critical_msgs)
    combined.extend(fee_tax_msgs[:6])
    combined.extend(setter_like_msgs[:8])
    #if owner_access_pattern:
    #    combined.append("🟡 Owner/Access-control patterns found in source (no custom state-admin var detected)")

    if not combined:
        return ["🟢 No suspicious non-ERC20 functions found"]

    # dedupe & return
    seen3 = set(); out = []
    for x in combined:
        if x not in seen3:
            seen3.add(x); out.append(x)
    return out

def get_tax_info_simulation_sync(token_address, honey_ca):
    tax_results = {"BuyTax": 0.0, "SellTax": 0.0, "BuySuccess": False, "SellSuccess": False}
    if not w3 or not honey_ca or not w3.is_address(honey_ca): 
        return {"error": "HONEY Contract not deployed or invalid address"}

    try:
        honey_contract = w3.eth.contract(address=w3.to_checksum_address(honey_ca), abi=HONEY_ABI_MINIMAL)
        results = _safe_rpc_call(lambda: honey_contract.functions.checkHoneyMain(
            w3.to_checksum_address(token_address)
        ).call({'gas': 5000000})) 

        if results is None or len(results) < 7:
            return {"error": "Tax simulation failed to return expected data."}

        buyEstimate, buyReal, sellEstimate, sellReal, buy, sell, _ = results
        tax_results["BuySuccess"] = buy
        tax_results["SellSuccess"] = sell
        
        if buyEstimate > 0 and buyReal > 0:
            tax_results["BuyTax"] = round((buyEstimate - buyReal) / buyEstimate * 100, 2)
        elif buyEstimate > 0 and buyReal == 0 and buy: tax_results["BuyTax"] = 100.0
        elif not buy: tax_results["BuyTax"] = "Fail"

        if sellEstimate > 0 and sellReal > 0:
            tax_results["SellTax"] = round((sellEstimate - sellReal) / sellEstimate * 100, 2)
        elif sellEstimate > 0 and sellReal == 0 and sell: tax_results["SellTax"] = 100.0
        elif not sell: tax_results["SellTax"] = "Fail"
            
    except Exception as e:
        return {"error": f"Tax simulation failed: {e.__class__.__name__} - {str(e)}"}
    return tax_results

def process_tax_results(tax_data_raw):
    tax_data = {"BuyTax": "N/A", "SellTax": "N/A", "BuySuccess": False, "SellSuccess": False, "Honeypot": "❌ Unknown"}
    if isinstance(tax_data_raw, dict) and not tax_data_raw.get("error"):
        buy_tax = tax_data_raw['BuyTax']
        sell_tax = tax_data_raw['SellTax']
        buy_ok = tax_data_raw['BuySuccess']
        sell_ok = tax_data_raw['SellSuccess']

        if buy_ok and sell_ok and isinstance(buy_tax, (int, float)):
            if not isinstance(sell_tax, (int, float)) or sell_tax > 20.0 or sell_tax < 0:
                sell_tax = buy_tax 

        tax_data["BuyTax"] = f"{buy_tax:.2f}%" if isinstance(buy_tax, (int, float)) else tax_data["BuyTax"]
        tax_data["SellTax"] = f"{sell_tax:.2f}%" if isinstance(sell_tax, (int, float)) else tax_data["SellTax"]
        
        tax_data["BuySuccess"] = buy_ok
        tax_data["SellSuccess"] = sell_ok

        if buy_ok and not sell_ok:
            tax_data["Honeypot"] = "🚨 HONEYPOT"
        elif isinstance(sell_tax, (int, float)) and sell_tax >= 99.0:
            tax_data["Honeypot"] = "🚨 *RUG/100% Tax*"
        elif not buy_ok and not sell_ok:
            tax_data["Honeypot"] = "❌ Unknown"
        else:
            tax_data["Honeypot"] = "✅ OK"
            
    elif isinstance(tax_data_raw, dict) and tax_data_raw.get("error"):
        tax_data["BuyTax"] = "N/A"
        tax_data["SellTax"] = "N/A"
    return tax_data

def deep_lp_scan_sync(lp_to_scan, token_contract, token_total_supply, w3, BURN_ADDRESSES_CHECKSUM, lp_source):
    data = {"LP_Source_Name": lp_source}
    try:
        lp_address_checksum = lp_to_scan 
        lp_contract = w3.eth.contract(address=lp_address_checksum, abi=TOKEN_MINIMAL_ABI)
        
        lp_total_supply = _safe_rpc_call(lp_contract.functions.totalSupply().call)
        if lp_total_supply is None or lp_total_supply == 0:
            data["LP_burnt"] = "N/A (LP Total Supply is 0)"
            data["Supply_in_Pool"] = "N/A"
            return data
            
        lp_total_burnt_balance = sum(_safe_rpc_call(lambda: lp_contract.functions.balanceOf(a).call()) or 0 for a in BURN_ADDRESSES_CHECKSUM)
            
        percent_burnt = (lp_total_burnt_balance / lp_total_supply) * 100
        data["LP_burnt"] = f"{percent_burnt:.2f}% 🔥 | {lp_source}"
        
        token_total_burnt_balance = sum(_safe_rpc_call(lambda: token_contract.functions.balanceOf(a).call()) or 0 for a in BURN_ADDRESSES_CHECKSUM)
            
        if token_total_supply == 0: raise Exception("Total supply is zero")
            
        percent_supply_burnt = (token_total_burnt_balance / token_total_supply) * 100
        token_balance_in_pool = _safe_rpc_call(lambda: token_contract.functions.balanceOf(lp_address_checksum).call()) or 0
        percent_in_pool = (token_balance_in_pool / token_total_supply) * 100
        
        data["Supply_in_Pool"] = (
            f"{percent_in_pool:.2f}% | "
            f"{percent_supply_burnt:.2f}% 🔥Burn"
        )
    except Exception as e:
        logging.error(f"Deep LP Scan failed: {e}")
        data["LP_burnt"] = "Error LP Scan"
        data["Supply_in_Pool"] = "Error Supply Scan"
    return data

# --- FUNGSI UTILITAS ASINKRON ---

REQUEST_TIMEOUT = 8

async def get_pls_price():
    """Fetches PLS USD price from PulseScan API (coinprice) with LP Calc Fallback."""
    url_ps = f"{PULSESCAN_API_BASE_URL}?module=stats&action=coinprice"
    if PULSESCAN_API_KEY: url_ps += f"&apikey={PULSESCAN_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url_ps)
            data = response.json()
            if data.get('status') == '1' and data.get('result'):
                price_usd = float(data['result'].get('ethusd', 0))
                if price_usd > 0:
                    return price_usd, f"${price_usd:,.8f}"
    except Exception:
        logging.warning("PulseScan API Price fetch failed. Falling back to LP calculation.")
        pass

    lp_price = await asyncio.to_thread(get_pls_price_from_lp_sync)
    if lp_price > 0:
        return lp_price, f"${lp_price:,.8f} (LP Calc)"

    return PLS_FALLBACK_PRICE, PLS_FALLBACK_PRICE_DISPLAY

async def get_pls_balance(wallet_address):
    """Fetches native PLS balance, USD value, and returns raw balance for error checking."""
    if not w3 or not w3.is_connected():
        return None, 0.0, 0.0, 0.0, ""

    try:
        checksum_addr = w3.to_checksum_address(wallet_address)
    except InvalidAddress:
        return None, 0.0, 0.0, 0.0, ""

    tasks = [
        asyncio.to_thread(lambda: w3.eth.get_balance(checksum_addr)),
        get_pls_price()
    ]

    try:
        pls_raw_balance, price_tuple = await asyncio.gather(*tasks)
    except Exception as e:
        logging.error(f"Failed to fetch PLS balance/price in async gather: {e}")
        return None, 0.0, 0.0, PLS_FALLBACK_PRICE, PLS_FALLBACK_PRICE_DISPLAY


    pls_price_usd, pls_price_display = price_tuple

    if pls_raw_balance is None:
        return None, 0.0, 0.0, pls_price_usd, pls_price_display

    pls_balance = w3.from_wei(pls_raw_balance, 'ether')
    pls_value_usd = float(pls_balance) * pls_price_usd

    return pls_raw_balance, pls_balance, pls_value_usd, pls_price_usd, pls_price_display

async def get_token_metadata_paditrack_async(contract_address):
    """Fetches Name, Symbol, and Decimals from PulseScan API, with RPC fallback for decimals."""
    
    decimals_rpc_sync = lambda: _safe_rpc_call(w3.eth.contract(address=w3.to_checksum_address(contract_address), abi=[{"constant":True,"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"type": "function"}]).functions.decimals().call)
    decimals_rpc = await asyncio.to_thread(decimals_rpc_sync) or 18

    url = f"{PULSESCAN_API_BASE_URL}?module=token&action=getToken&contractaddress={contract_address}"
    if PULSESCAN_API_KEY: url += f"&apikey={PULSESCAN_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(url)
            data = response.json()
        if data.get('status') == '1' and data.get('result'):
            api_result = data['result']
            decimals = safe_decimals(api_result.get('decimals'), fallback=decimals_rpc)
            return {
                "name": api_result.get('name', 'Unknown'),
                "symbol": api_result.get('symbol', 'TOKEN'),
                "decimals": decimals
            }
    except Exception:
        logging.warning("PulseScan API Token Metadata failed. Falling back to RPC metadata.")
        
    metadata_rpc = await asyncio.to_thread(get_token_metadata_sync, contract_address)
    metadata_rpc["Decimals"] = decimals_rpc 
    return {"name": metadata_rpc['Name'], "symbol": metadata_rpc['Ticker'], "decimals": metadata_rpc['Decimals']}

async def fetch_single_token_data(wallet_address, contract_address, pls_price_usd, hardcoded_symbol=None, hardcoded_group=None):
    """Fetches balance, calculates LP price, and computes USD value for one token."""
    
    metadata, raw_balance = None, 0
    display_symbol = hardcoded_symbol if hardcoded_symbol else 'UNKNOWN'
    display_group = hardcoded_group if hardcoded_group else 'API'
    
    try:
        metadata = await get_token_metadata_paditrack_async(contract_address)

        url_balance = f"{PULSESCAN_API_BASE_URL}?module=account&action=tokenbalance&contractaddress={contract_address}&address={wallet_address}"
        if PULSESCAN_API_KEY: url_balance += f"&apikey={PULSESCAN_API_KEY}"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url_balance)
            data = response.json()
        if data.get('status') == '1':
            raw_balance = int(data['result'])
        
        if raw_balance == 0:
            return None

        if display_symbol == 'UNKNOWN' or display_symbol is None:
            display_symbol = metadata.get('symbol', 'UNKNOWN')

        decimals = safe_decimals(metadata.get('decimals'), fallback=18)
        token_balance = raw_balance / (10 ** decimals)
        token_pls_ratio = await asyncio.to_thread(get_erc20_price_from_lp_sync, contract_address, decimals)
        token_value_usd = token_balance * token_pls_ratio * pls_price_usd

        if token_value_usd > 0 and token_balance > 0:
            usd_value_str = f"≈ ${human_format(token_value_usd, decimals=2)}" if token_value_usd >= 1 else f"≈ ${token_value_usd:,.4f}"
            return {
                "token": display_symbol,
                "group": display_group,
                "balance": token_balance,
                "usd_value": token_value_usd,
                "usd_value_str": usd_value_str
            }
        
        if token_balance > 0:
             return {
                "token": display_symbol,
                "group": display_group,
                "balance": token_balance,
                "usd_value": 0.0,
                "usd_value_str": "N/A (No LP)"
            }

    except Exception as e:
        logging.error(f"Failed to fetch/process data for {contract_address}: {e}")
        return None 
    return None

async def get_token_balances(wallet_address, pls_price_usd):
    """Fetches list of all ERC-20 tokens held using PulseScan API (tokenlist + Hardcoded)."""
    
    if not w3 or not w3.is_connected(): 
        return [{"token": "Web3 Connection Failed", "balance": 0.0, "usd_value": 0.0, "usd_value_str": "N/A"}] 
    
    try:
        checksum_addr = w3.to_checksum_address(wallet_address)
    except Exception:
        return [{"token": "Invalid Address Format", "balance": 0.0, "usd_value": 0.0, "usd_value_str": "N/A"}]

    all_contracts_to_check = set()
    token_details_map = HARDCODED_MAP.copy()

    url_tokenlist = f"{PULSESCAN_API_BASE_URL}?module=account&action=tokenlist&address={checksum_addr}"
    if PULSESCAN_API_KEY: url_tokenlist += f"&apikey={PULSESCAN_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url_tokenlist)
            data = response.json()

        if data.get('status') == '1' and isinstance(data.get('result'), list):
            for item in data['result']:
                contract = item.get('ContractAddress')
                if contract:
                    all_contracts_to_check.add(contract)
                    if contract not in token_details_map:
                        api_symbol = item.get('TokenSymbol', 'TOKEN')
                        token_details_map[contract] = (api_symbol, 'API')

    except Exception as api_e:
        logging.warning(f"PulseScan Tokenlist API failed: {api_e.__class__.__name__}. Proceeding with Hardcoded list.")

    for address in token_details_map.keys():
        all_contracts_to_check.add(address)
        
    if not all_contracts_to_check:
        return []

    fetch_tasks = []
    for contract in all_contracts_to_check:
        symbol, group = token_details_map.get(contract, (None, 'API'))
        fetch_tasks.append(fetch_single_token_data(
            checksum_addr, contract, pls_price_usd, hardcoded_symbol=symbol, hardcoded_group=group
        ))

    results = await asyncio.gather(*fetch_tasks)
    final_data = sorted([r for r in results if r is not None], key=lambda x: x['usd_value'], reverse=True)

    if not final_data and len(all_contracts_to_check) > 0:
        return [{"token": "Token LP/Balance Fetch Failed", "balance": 0.0, "usd_value": 0.0, "usd_value_str": "N/A"}]
        
    return final_data
    
REQUEST_TIMEOUT = 8

def _normalize_abi_from_sourcify(metadata: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Extract the first meaningful ABI found in Sourcify metadata JSON."""
    if not metadata or not isinstance(metadata, dict):
        return None

    # 1) Direct top-level 'abi' (pulse scan style/simple)
    top_abi = metadata.get("abi")
    if isinstance(top_abi, list):
        return top_abi

    # 2) Look into metadata['metadata'] if present (Sourcify nests compile metadata there sometimes)
    meta = metadata.get("metadata") or metadata
    
    # Jika metadata adalah JSON string, coba parse (kasus PulseScan/repo lama)
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    try:
        output = meta.get("output") if isinstance(meta, dict) else None
        if output and isinstance(output, dict):
            contracts = output.get("contracts") or {}
            # contracts mapping file -> {ContractName: compileOutput}
            for file_contracts in contracts.values():
                if not isinstance(file_contracts, dict): continue
                for cinfo in file_contracts.values():
                    if not isinstance(cinfo, dict): continue
                    ca = cinfo.get("abi")
                    if isinstance(ca, list) and ca:
                        # return the first non-empty ABI (Ini adalah jalur ON-POINT Anda)
                        return ca
    except Exception:
        logging.debug("Error while searching metadata.output.contracts for ABI")

    # 3) Fallback: Coba ambil dari 'output.abi'
    fallback_abi = output.get("abi") if isinstance(output, dict) else None
    if isinstance(fallback_abi, list):
         return fallback_abi

    # nothing found
    return None

# utils.py (Ganti fungsi get_verification_status)
# === START Sourcify robust helpers (paste to replace older versions) ===
SOURCIFY_REPO = "https://repo.sourcify.dev/contracts"   # canonical repo endpoint

async def _httpx_get(client, url, timeout=REQUEST_TIMEOUT):
    try:
        r = await client.get(url, timeout=timeout)
        return r
    except Exception as e:
        logging.debug(f"HTTPX GET error for {url}: {type(e).__name__}: {e}")
        return None

def _try_extract_abi_from_metadata_obj(meta_obj: Any) -> Optional[List[Dict[str, Any]]]:
    """
    Robust extraction for many shapes of metadata returned by Sourcify or Etherscan-like APIs.
    """
    if not meta_obj:
        return None

    # If metadata is stringified, try parse
    if isinstance(meta_obj, str):
        try:
            meta_obj = json.loads(meta_obj)
        except Exception:
            # not JSON -> ignore
            meta_obj = {}

    if not isinstance(meta_obj, dict):
        return None

    # 1) top-level 'abi'
    top_abi = meta_obj.get("abi")
    if isinstance(top_abi, list) and top_abi:
        return top_abi

    # 2) metadata.output.contracts.{file}.{ContractName}.abi
    out = meta_obj.get("output") or {}
    if isinstance(out, dict):
        # try output.contracts
        contracts_map = out.get("contracts")
        if isinstance(contracts_map, dict):
            for file_contracts in contracts_map.values():
                if not isinstance(file_contracts, dict):
                    continue
                for contract_info in file_contracts.values():
                    if isinstance(contract_info, dict):
                        abi_candidate = contract_info.get("abi")
                        if isinstance(abi_candidate, list) and abi_candidate:
                            return abi_candidate
        # fallback: output.abi
        fallback = out.get("abi")
        if isinstance(fallback, list) and fallback:
            return fallback

    return None

async def fetch_sourcify_repo_metadata(chain_id: int, ca: str) -> Optional[Tuple[Any, str]]:
    """
    Try to fetch metadata & files from repo.sourcify.dev using several canonical paths.
    Returns tuple (raw_response, kind) where kind is one of:
      - "metadata.json (full_match)"
      - "metadata.json (partial_match)"
      - "repo-list" (endpoint returns list of objects)
    """
    ca_norm = ca.lower().replace("0x", "")
    paths_to_try = [
        f"{SOURCIFY_REPO}/full_match/{chain_id}/{ca_norm}/metadata.json",
        f"{SOURCIFY_REPO}/partial_match/{chain_id}/{ca_norm}/metadata.json",
        f"{SOURCIFY_REPO}/full_match/{chain_id}/{ca_norm}",
        f"{SOURCIFY_REPO}/partial_match/{chain_id}/{ca_norm}"
    ]

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        for url in paths_to_try:
            r = await _httpx_get(client, url)
            if not r:
                continue
            if r.status_code == 200:
                # metadata.json path -> probably JSON object directly
                text = r.text
                try:
                    payload = r.json()
                except Exception:
                    # try parse if text contains JSON inside (rare)
                    try:
                        payload = json.loads(text)
                    except Exception:
                        payload = text
                # decide kind
                if url.endswith("metadata.json"):
                    return payload, "metadata.json"
                else:
                    # repo-list endpoint often returns list of objects (each with metadata/files)
                    return payload, "repo-list"
            elif r.status_code == 404:
                logging.debug(f"Sourcify repo returned 404 for {url}")
                continue
            else:
                logging.debug(f"Sourcify repo returned status {r.status_code} for {url}")
                continue
    return None

async def get_sourcify_verification_data(ca: str, chain_id: int = 369) -> Optional[Tuple[List[Dict[str, Any]], Any]]:
    """
    Robust getter that attempts to return (abi_list, source_files_or_source_text)
    It will try:
      - repo.sourcify.dev/.../metadata.json (full_match / partial_match)
      - repo.sourcify.dev/... (list form)
    """
    fetched = await fetch_sourcify_repo_metadata(chain_id, ca)
    if not fetched:
        return None

    payload, kind = fetched

    # Case A: metadata.json object (direct metadata)
    if kind == "metadata.json" and isinstance(payload, dict):
        # Try to extract ABI from the payload itself
        abi = _try_extract_abi_from_metadata_obj(payload)
        # Source files may be available under 'sources' or client may need to fetch file list separately.
        source_files = payload.get("sources") or payload.get("files") or None
        if abi:
            return abi, source_files
        # If payload lacks ABI but contains 'metadata' nested (rare), try that
        nested_meta = payload.get("metadata")
        if nested_meta:
            abi2 = _try_extract_abi_from_metadata_obj(nested_meta)
            if abi2:
                return abi2, source_files
        # else fallback None
        return None

    # Case B: repo-list form. That endpoint often returns a LIST of dicts each containing 'metadata' and 'files'
    if kind == "repo-list":
        if isinstance(payload, list) and payload:
            # find first entry with metadata and try to extract ABI
            for item in payload:
                if not isinstance(item, dict):
                    continue
                # item might include 'metadata' (string/dict) and 'files'
                meta_candidate = item.get("metadata") or item.get("metadata.json") or item.get("metadataJson")
                if meta_candidate:
                    abi = _try_extract_abi_from_metadata_obj(meta_candidate)
                    sources = item.get("files") or item.get("sources") or None
                    if abi:
                        return abi, sources
                # Some items may directly contain 'output' or 'abi'
                abi_direct = item.get("abi") or item.get("output", {}).get("abi")
                if isinstance(abi_direct, list) and abi_direct:
                    sources = item.get("files") or item.get("sources") or None
                    return abi_direct, sources
        return None

    return None

async def get_verification_status(ca: str, chain_id: int = 369, std_json: dict | None = None):
    """
    Unified verification check:
      - Try PulseScan getsourcecode first (Etherscan-compatible)
      - Fallback to Sourcify repo (robust functions above)
      - If std_json provided, attempt to submit to Sourcify v2 verify endpoint as before (best-effort)
    Returns (status_str, abi_or_None, source_or_None)
    """
    # 1) Try PulseScan / Etherscan-style getsourcecode
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            url_ps = f"{PULSESCAN_API_BASE_URL}?module=contract&action=getsourcecode&address={ca}"
            if PULSESCAN_API_KEY:
                url_ps += f"&apikey={PULSESCAN_API_KEY}"
            r = await client.get(url_ps)
            if r.status_code == 200:
                data_ps = r.json()
                if data_ps.get('status') == '1' and data_ps.get('result'):
                    item = data_ps['result'][0]
                    abi_raw = item.get('ABI') or item.get('abi') or None
                    source_code = item.get('SourceCode') or item.get('sourceCode') or ''
                    # normalize ABI if string
                    if isinstance(abi_raw, str):
                        try:
                            abi_parsed = json.loads(abi_raw) if abi_raw and abi_raw != 'Contract source code not verified' else None
                        except Exception:
                            abi_parsed = None
                    else:
                        abi_parsed = abi_raw if isinstance(abi_raw, list) else None

                    if abi_parsed:
                        return "✅ Verified (PulseScan)", abi_parsed, source_code
                    # else continue to Sourcify fallback
            else:
                logging.debug(f"PulseScan getsourcecode returned {r.status_code}")
        except Exception as e:
            logging.debug(f"PulseScan lookup failed: {type(e).__name__}: {e}")

    # 2) Try Sourcify repo (robust)
    try:
        res = await get_sourcify_verification_data(ca, chain_id)
        if res:
            abi_list, source = res
            return "✅ Verified (Sourcify Repo)", abi_list, source
    except Exception as e:
        logging.debug(f"Sourcify repo check error: {type(e).__name__}: {e}")

    # 3) If std_json provided, attempt to POST to Sourcify v2 verify (best-effort)
    if std_json:
        post_url = f"{SOURCIFY_BASE}/v2/verify/{chain_id}/{ca}"
        try:
            async with httpx.AsyncClient(timeout=30) as client2:
                rpost = await client2.post(post_url, json={"stdJsonInput": std_json}, headers={"Content-Type": "application/json"})
                if rpost.status_code in (200,201,202):
                    # try to re-query repo after short wait
                    await asyncio.sleep(2.0)
                    res2 = await get_sourcify_verification_data(ca, chain_id)
                    if res2:
                        abi_list2, source2 = res2
                        return "✅ Verified (Sourcify - submitted & matched)", abi_list2, source2
                    return "🟡 Submitted to Sourcify (pending)", None, None
                else:
                    logging.debug(f"Sourcify submit returned {rpost.status_code}: {rpost.text[:200]}")
                    return f"❌ Sourcify submit failed ({rpost.status_code})", None, None
        except Exception as e:
            logging.debug(f"Sourcify submit exception: {type(e).__name__}: {e}")
            return "❌ Sourcify submit exception", None, None

    # 4) Not verified
    return "❌ Contract is Unverified", None, None
# === END Sourcify robust helpers ===


async def get_market_data(ca):
    """Mengambil data pasar dari Dexscreener secara ASINKRON."""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{ca}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        pulse_pairs = [p for p in data.get('pairs', []) if p.get('chainId') == 'pulsechain']
        if not pulse_pairs: return None
        main_pair = max(pulse_pairs, key=lambda p: float(p.get('liquidity', {}).get('usd', 0)))
        stats = {"Price": float(main_pair.get('priceUsd', 0)), "Liquidity": float(main_pair.get('liquidity', {}).get('usd', 0)), "Price_Change": float(main_pair.get('priceChange', {}).get('h24', 0)), "Volume": float(main_pair.get('volume', {}).get('h24', 0))}
        return stats
    except httpx.TimeoutException: return {"error": "Dexscreener Timeout"}
    except httpx.RequestError as e: return {"error": f"Dexscreener Request Failed: {e.__class__.__name__}"}
    except Exception as e: return {"error": f"Unknown Error: {e.__class__.__name__}"}

async def deep_scan_contract(ca):
    """Performs Deep Scan for PadiScan."""
    results = {
        "metadata": {}, "Verify": "UNKNOWN", "Owner": "N/A (Owner function not found)", "Upgradeable": "UNKNOWN",
        "LP_Address": "N/A (PulseX V2/V1)", "LP_burnt": "N/A", "Supply_in_Pool": "N/A", "LP_Source_Name": "Unknown DEX",
        "Sus_Features": "N/A", "market_data": {}
    }

    if not w3 or not w3.is_connected():
        results['Verify'] = "RPC Connection Failed"
        return results

    # initial parallel tasks: verification, market data, token metadata
    tasks = [
        get_verification_status(ca),
        get_market_data(ca),
        asyncio.to_thread(get_token_metadata_sync, ca),
    ]

    # run initial tasks
    verify_status, market_data_raw, metadata = await asyncio.gather(*tasks)

    results["market_data"] = market_data_raw if market_data_raw and not market_data_raw.get("error") else {}
    # verify_status expected: (verify_str, full_abi_or_none, source_code_or_none)
    try:
        results["Verify"], full_abi, source_code = verify_status
    except Exception:
        # defensive fallback
        results["Verify"], full_abi, source_code = ("⚠️ Verification fetch failed", None, None)
    results["metadata"] = metadata

    # choose ABI: prefer full_abi, otherwise fallback to minimal token ABI
    abi_to_use = full_abi if full_abi else TOKEN_MINIMAL_ABI

    # try create token contract (with checksum address)
    try:
        token_contract = w3.eth.contract(address=w3.to_checksum_address(ca), abi=abi_to_use)
    except Exception:
        results["Owner"] = "Error in Web3 Contract Init"
        return results

    # safe wrappers for owner() and totalSupply() calls
    owner_call_safe = lambda: _safe_rpc_call(token_contract.functions.owner().call)
    supply_call_safe = lambda: _safe_rpc_call(token_contract.functions.totalSupply().call)

    # ---------- SUS SCAN: use ABI-aware scanner if full_abi present, otherwise use source-only scan ----------
    try:
        if full_abi:
            sus_features_task = asyncio.to_thread(
                scan_suspicious_features_sync,
                token_contract,
                source_code
            )
        else:
            # scan_source_patterns returns (sus_list, detailed_flags)
            sus_features_task = asyncio.to_thread(lambda: scan_source_patterns(source_code or "", [], []))
    except Exception as e:
        sus_features_task = asyncio.to_thread(lambda: [f"⚠️ Sus scan setup failed: {e}"])

    # ensure we only call owner()/totalSupply() when function exists in ABI used
    has_owner_func = any(isinstance(f, dict) and f.get('name') == 'owner' for f in (abi_to_use or []))
    has_supply_func = any(isinstance(f, dict) and f.get('name') == 'totalSupply' for f in (abi_to_use or []))

    tasks_rpc_critical = [
        asyncio.to_thread(owner_call_safe) if has_owner_func else asyncio.to_thread(lambda: None),
        asyncio.to_thread(supply_call_safe) if has_supply_func else asyncio.to_thread(lambda: 0),

        asyncio.to_thread(scan_and_rank_wpls_pairs_sync, ca),
        asyncio.to_thread(get_tax_info_simulation_sync, ca, HONEY_V2_ADDRESS),
        asyncio.to_thread(get_tax_info_simulation_sync, ca, HONEY_V1_ADDRESS),
        sus_features_task
    ]

    # gather critical RPC + scan tasks, allow exceptions to be returned
    owner_address, token_total_supply, lp_pair_data, tax_data_v2_raw, tax_data_v1_raw, sus_scan_raw = await asyncio.gather(*tasks_rpc_critical, return_exceptions=True)

    # normalize results from gather: convert Exceptions into safe fallback values
    owner_address = None if isinstance(owner_address, Exception) else owner_address
    token_total_supply = 0 if isinstance(token_total_supply, Exception) else token_total_supply
    lp_pair_data = (None, None) if isinstance(lp_pair_data, Exception) else lp_pair_data
    tax_data_v2_raw = tax_data_v2_raw if not isinstance(tax_data_v2_raw, Exception) else {"error": str(tax_data_v2_raw)}
    tax_data_v1_raw = tax_data_v1_raw if not isinstance(tax_data_v1_raw, Exception) else {"error": str(tax_data_v1_raw)}

    # normalize sus_scan_raw into sus_scan_output as List[str]
    sus_scan_output = []
    try:
        if isinstance(sus_scan_raw, Exception):
            sus_scan_output = [f"Error Sus Features Scan: {sus_scan_raw.__class__.__name__}"]
        else:
            # if we used scan_source_patterns it returns tuple (sus_list, detailed_flags)
            if isinstance(sus_scan_raw, tuple) and len(sus_scan_raw) >= 1:
                cand = sus_scan_raw[0]
                if isinstance(cand, list):
                    sus_scan_output = cand
                elif isinstance(cand, str):
                    sus_scan_output = [cand]
                else:
                    sus_scan_output = list(cand) if cand else []
            elif isinstance(sus_scan_raw, list):
                sus_scan_output = sus_scan_raw
            elif isinstance(sus_scan_raw, str):
                sus_scan_output = [sus_scan_raw]
            elif sus_scan_raw is None:
                sus_scan_output = []
            else:
                # fallback: stringify
                sus_scan_output = [str(sus_scan_raw)]
    except Exception as e:
        sus_scan_output = [f"Error normalizing sus scan output: {e}"]

    # lp pair unpack
    try:
        lp_to_scan, lp_source = lp_pair_data
    except Exception:
        lp_to_scan, lp_source = (None, None)

    results["LP_Address"] = lp_to_scan if lp_to_scan else f"N/A (WPLS Pair not found in PulseX V2/V1)"
    results["LP_Source_Name"] = lp_source if lp_source else "Unknown DEX"

    # process tax simulation results with your existing helper
    results["V2_Tax"] = process_tax_results(tax_data_v2_raw)
    results["V1_Tax"] = process_tax_results(tax_data_v1_raw)

    # owner normalization & burn check
    owner_is_burned = False
    if owner_address is not None:
        try:
            owner_address_checksum = w3.to_checksum_address(owner_address)
            results["Owner"] = owner_address_checksum
            if owner_address_checksum in BURN_ADDRESSES_CHECKSUM:
                owner_is_burned = True
        except Exception:
            results["Owner"] = "Error Owner Check"
    else:
        results["Owner"] = "`Unknown Ownership`"

    # detect critical sus features presence
    has_critical_sus_feature = any(isinstance(f, str) and f.startswith('🔴') for f in sus_scan_output)

    # ---------- Logic for verification & ownership messages ----------
    try:
        if isinstance(results.get("Verify", ""), str) and results["Verify"].startswith("❌ Contract is Unverified"):
            # Contract unverified -> prepend strong warning
            sus_scan_output.insert(0, "🔴 Never buy unverified contracts")
            results["Upgradeable"] = "❌ Unknown Ownership"
            results["Sus_Features"] = "\n".join(sus_scan_output)
        elif full_abi is None:
            # verified but ABI missing/unavailable
            if isinstance(results.get("Verify", ""), str) and results["Verify"].startswith("✅ Verified"):
                sus_scan_output = [f"⚠️ {results['Verify']}, but ABI is missing. Cannot analyze Non-standard Functions."]
            else:
                sus_scan_output = ["⚠️ Verification found, but ABI is missing. Cannot analyze Non-standard Functions."]

            results["Sus_Features"] = "\n".join(sus_scan_output)
            if owner_address is not None and not owner_is_burned:
                results["Upgradeable"] = "⚠️ Owner Active (Cannot verify features)"
            elif owner_is_burned:
                results["Upgradeable"] = "✅ Ownership Renounced (No ABI check)"
            else:
                results["Upgradeable"] = "❌ Unknown Ownership"
        elif owner_is_burned:
            results["Upgradeable"] = "✅ Ownership Renounced"
            # convert reds/yellows to green for safety message summary
            results["Sus_Features"] = "\n".join([f.replace('🔴 ', '🟢 ').replace('🟡 ', '🟢 ') for f in sus_scan_output if not f.startswith('🟢')]) or "🟢 No non-ERC20 structural control features detected"
        elif owner_address and not owner_is_burned:
            results["Upgradeable"] = "❌ Not Renounced" if has_critical_sus_feature else "❌ Not Renounced"
            results["Sus_Features"] = "\n".join(sus_scan_output)
        else:
            # fallback case
            results["Upgradeable"] = "❌ Unknown Ownership"
            results["Sus_Features"] = "\n".join(sus_scan_output)
    except Exception as e:
        # defensive fallback
        results["Upgradeable"] = "❌ Unknown Ownership"
        results["Sus_Features"] = "\n".join(sus_scan_output) if isinstance(sus_scan_output, list) else str(sus_scan_output)

    # ---------- LP deep scan if pair exists and supply known ----------
    try:
        if lp_to_scan and token_total_supply is not None and token_total_supply > 0:
            lp_scan_data = await asyncio.to_thread(
                lambda: deep_lp_scan_sync(lp_to_scan, token_contract, token_total_supply, w3, BURN_ADDRESSES_CHECKSUM, lp_source)
            )
            if lp_scan_data and isinstance(lp_scan_data.get("LP_burnt"), str):
                results.update(lp_scan_data)
            else:
                results["LP_burnt"] = "Error LP Scan"
                results["Supply_in_Pool"] = "Error Supply Scan"
        else:
            results["LP_burnt"] = "N/A"
            results["Supply_in_Pool"] = "N/A"
    except Exception:
        results["LP_burnt"] = "Error LP Scan"
        results["Supply_in_Pool"] = "Error Supply Scan"

    return results

# --- ERROR HANDLER GLOBAL ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the user/console."""
    logging.error("Exception while handling an update:", exc_info=context.error)
    print(f"\n\n🚨 TELEGRAM HANDLER CRASHED! 🚨")
    print(f"Error: {context.error}")
    print("-" * 50)
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            f"❌ *There was an error while processing your command!* \nDetail: `{context.error.__class__.__name__}`. Check the console log.",
            parse_mode='Markdown'
        )