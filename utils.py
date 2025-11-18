# utils.py

import os
import json
import asyncio
import httpx
import logging
import time
import re
from web3 import Web3
from web3.exceptions import ContractLogicError, BadFunctionCallOutput, InvalidAddress
from typing import Tuple, Any, Dict, Optional, List
from dotenv import load_dotenv
from telegram.ext import ContextTypes 
from telegram import Update
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
WPLS_CHECKSUM_LOWER = WPLS_ADDRESS.lower() # Untuk perbandingan subgraph
STABLECOIN_ADDRESS = "0xefD766cCb38EaF1dfd701853BFCe31359239F305"
STABLECOIN_DECIMALS = 18
DEAD_ADDRESS = "0x000000000000000000000000000000000000dEaD"
PULSE_BURN_ADDRESS = "0x0000000000000000000000000000000000000369"

BURN_ADDRESSES_CHECKSUM = []
WPLS_CHECKSUM = None

# >>> START MODIFIKASI GLOBAL SETUP (Penerapan Stablecoin) <<<
STABLECOIN_CHECKSUM = None 
STABLECOIN_CHECKSUM_LOWER = None 

if w3:
    try:
        BURN_ADDRESSES_CHECKSUM = [w3.to_checksum_address(a) for a in [DEAD_ADDRESS, "0x0000000000000000000000000000000000000000", PULSE_BURN_ADDRESS]]
        WPLS_CHECKSUM = w3.to_checksum_address(WPLS_ADDRESS)
        # NEW: Tambahkan Stablecoin Checksum logic
        STABLECOIN_CHECKSUM = w3.to_checksum_address(STABLECOIN_ADDRESS)
        STABLECOIN_CHECKSUM_LOWER = STABLECOIN_CHECKSUM.lower()
    except Exception:
        pass

# NEW: Definisikan daftar alamat dasar (WPLS dan Stablecoin) untuk pencarian Graph
GRAPH_SEARCH_BASES = []
if w3 and WPLS_CHECKSUM:
    GRAPH_SEARCH_BASES.append(WPLS_CHECKSUM_LOWER)
if w3 and STABLECOIN_CHECKSUM:
    GRAPH_SEARCH_BASES.append(STABLECOIN_CHECKSUM_LOWER)
# >>> END MODIFIKASI GLOBAL SETUP <<<


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
    {"symbol": "PX402", "address": "0x675ac865aebcfc1d22f819ba0fe7a60bf17cb60d", "group": "BASIC"},
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
    {"symbol": "WHALE", "address": "0x03b1a1b10151733bcefa52178aadf9d7239407b4", "group": "PT"},
    {"symbol": "5555", "address": "0xD4259602922212Afa5f8fbC404fE4664F69f19fC", "group": "PT"},
    {"symbol": "SPACEWHALE", "address": "0x4A04257c9872cDF93850DEe556fEEeDDE76785D4", "group": "PT"},
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

# Fungsi sinkron untuk mendapatkan rasio harga ERC20/PLS (RPC) - DIJAGA SEBAGAI FALLBACK
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
            pass 

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
            root_abi = None 

    if isinstance(root_abi, list) and root_abi:
        return root_abi, source
        
    return None, source 

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
        
def escape_markdown_v2(text: str) -> str:
    """
    Escape karakter spesial sesuai aturan resmi Telegram MarkdownV2.
    Referensi: https://core.telegram.org/bots/api#markdownv2-style
    """
    if not isinstance(text, str):
        return ""

    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#',
                    '+', '-', '=', '|', '{', '}', '.', '!']

    text = text.replace('\\', '\\\\')

    for char in escape_chars:
        text = text.replace(char, f'\\{char}')

    return text.replace('\\\\n', '\n')
    
def levenshtein(a: str, b: str) -> int:
    """Helper function for fuzzy string matching (e.g., misspelled 'renounceownership')."""
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

# FUNGSI LAMA DIGANTI OLEH get_graph_market_data_async
# def scan_and_rank_wpls_pairs_sync(token_address): ...

def extra_scan_source_patterns(source_code: str, sus_list: list, detailed_flags: list = None):
    """
    Heuristics to reveal obfuscated admin/backdoor patterns. (Dibiarkan agar tidak memecah kode)
    """
    if not isinstance(source_code, str) or not source_code:
        return

    s = source_code

    # ---------- identify state (contract-level) variables ----------
    state_var_pattern = r"(?:^|\n)\s*(?:address|bool|uint\d*|mapping\s*\([^\)]*\))\s+(?:public|private|internal|external)?\s*([A-Za-z0s9_]{3,40})\s*(?:=|;)"
    state_vars_found = set(re.findall(state_var_pattern, s, flags=re.M))

    # ---------- 1) admin variable assigned to msg.sender/_msgSender() but only if state var ----------
    admin_assigns = re.findall(r"([A-Za-z0s9_]{3,40})\s*=\s*(_?msgSender\(\)|msg\.sender)\s*;", s)
    for var, _fn in admin_assigns:
        if var not in state_vars_found:
            continue
        sus_list.append(f"🚩 Admin variable detected: `{var}` assigned to secondary owner")
        if detailed_flags is not None:
            detailed_flags.append({"type":"admin_var", "var": var})

    # ---------- 2) admin checks comparing var with msg.sender ----------
    checks = re.findall(r"([A-Za-z0s9_]{3,40})\s*(!=|==)\s*msg\.sender", s)
    for var, op in checks:
        if var in state_vars_found or len(re.findall(r"\b" + re.escape(var) + r"\b", s)) > 4:
            sus_list.append(f"🚩 Access check using custom admin var `{var}` with operator `{op}`")
            if detailed_flags is not None:
                detailed_flags.append({"type":"admin_check", "var": var, "op": op})

    # ---------- 3) XOR-with-self patterns (zeroing balances) ----------
    if re.search(r"\b([A-Za-z0s9_]{2,40})\s*=\s*\1\s*\^\s*\1\b", s):
        sus_list.append("🚩 XOR with self pattern detected")
        if detailed_flags is not None:
            detailed_flags.append({"type":"xor_zeroing"})

    if re.search(r"\b([A-Za-z0s9_]{2,40})\s*=\s*[A-Za-z0s9_]{2,40}\s*\^\s*[A-Za-z0s9_]{2,40}", s):
        sus_list.append("🚩 Potential bitwise zeroing pattern found")
        if detailed_flags is not None:
            detailed_flags.append({"type":"xor_like"})

    # ---------- 4) detect removing full user balance (deduct pattern) ----------
    if re.search(r"deductAmount\s*=\s*balances\[[^\]]+\]\s*;|balances\[[^\]]+\]\s*-\=\s*deductAmount", s):
        sus_list.append("🚩 Function that deducts entire balances detected")
        if detailed_flags is not None:
            detailed_flags.append({"type":"burn_entire_balance"})

    # ---------- 5) detect _totalSupply modifications / balances[...] += ... (possible mint) ----------
    if re.search(r"_totalSupply\s*[\+\-\*]?=|balances\[[^\]]+\]\s*\+\=\s*[A-Za-z0s9_]+", s):
        sus_list.append("🚩 Modifies totalSupply or increases balances in code")
        if detailed_flags is not None:
            detailed_flags.append({"type":"mint_like"})

    # ---------- 6) mapping flags likely used to freeze/zero balances ----------
    if re.search(r"\b(balancesto|balancesfrom|blacklist|blocklist|isBlocked|isBanned)\b", s, flags=re.I):
        sus_list.append("🚩 Mapping flags found")
        if detailed_flags is not None:
            detailed_flags.append({"type":"mapping_flags"})

    # ---------- 7) short obscure revert strings (obfuscation) ----------
    if re.search(r"revert\(\s*\"[^\"]{1,6}\"\s*\)", s):
        sus_list.append("🟡 Short/obscure revert strings found")
        if detailed_flags is not None:
            detailed_flags.append({"type":"short_revert"})

    # ---------- 8) _Holders array / getTokenHolders usage ----------
    if re.search(r"_Holders\s*\[", s) or re.search(r"getTokenHolders\s*\(", s):
        sus_list.append("🟡 Contract collects token holder addresses")
        if detailed_flags is not None:
            detailed_flags.append({"type":"holders_list"})
            
    # ---------- X) detect fake/obfuscated renounce + owner mint pattern ----------
    if re.search(r"function\s+[A-Za-z0s9_]*renounc[e|i][A-Za-z0s9_]*\s*\(", s, flags=re.I):
        sus_list.append("🚩 Suspicious fake renounce function name found")
        if detailed_flags is not None:
            detailed_flags.append({"type":"renounce_like"})

    if re.search(r"_balances\s*\[\s*_?msgSender\(\)\s*\]\s*\+\=\s*totalSupply\s*\(\s*\)\s*\*\s*[0-9]{2,}", s):
        sus_list.append("🚩 Owner mint via fake renounce function detected")
        if detailed_flags is not None:
            detailed_flags.append({"type":"owner_mint_totalSupply_mul"})

    if re.search(r"\b(ddsa|balancesto|balancesfrom|blacklist|isBlocked|isBanned)\b", s, flags=re.I):
        sus_list.append("🚩 Blacklist/flag mapping and custom transfer logic found")
        if detailed_flags is not None:
            detailed_flags.append({"type":"mapping_flag_transfer"})

    if re.search(r"_killEndTime|killEndTime", s) and re.search(r"block\.timestamp\s*<=\s*_killEndTime", s):
        sus_list.append("🚩 Kill window logic detected")
        if detailed_flags is not None:
            detailed_flags.append({"type":"kill_window"})

    return

def scan_suspicious_features_sync(contract, source_code: str = None) -> List[str]:
    """
    Final scanner implementing rule: (Dibiarkan agar tidak memecah kode)
    """
    abi = getattr(contract, "abi", None) or []
    addr_perm_msgs = []
    critical_msgs = []
    fee_tax_msgs = []
    setter_like_msgs = []

    def is_address_param(p): return p.get("type","").startswith("address")
    def is_bool_param(p): return p.get("type","") == "bool"
    def is_uint_param(p): return p.get("type","").startswith("uint")

    PRIORITY = {
        "critical": 0,
        "addr_perm": 1,
        "fee_tax": 2,
        "setter": 3,
        "other": 4
    }
    seen_funcs = {} 
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

        tag = None
        tag_priority = PRIORITY["other"]

        if "transfertoburn" in lname or lname == "transfertoburn":
            tag = "critical"
            tag_priority = PRIORITY["critical"]

        elif any(k in lname for k in ("fee","tax","settax","setfee","gettax","getfee","treasury","marketing","liquidity")):
            tag = "fee_tax"
            tag_priority = PRIORITY["fee_tax"]

        elif len(inputs) >= 2 and is_address_param(inputs[0]) and (is_bool_param(inputs[1]) or is_uint_param(inputs[1])):
            tag = "addr_perm"
            tag_priority = PRIORITY["addr_perm"]

        elif re.match(r'^(set|enable|disable|update|grant|revoke|transfer|withdraw|mint|burn)', name, flags=re.I):
            if name.lower() not in SAFE_SETTER_EXCLUDES:
                tag = "setter"
                tag_priority = PRIORITY["setter"]

        prev_tag = seen_funcs.get(name)
        prev_priority = PRIORITY.get(prev_tag, PRIORITY["other"]) if prev_tag else None

        if prev_tag is None or (prev_priority is not None and tag_priority < prev_priority):
            if tag == "critical":
                cm = f"🔴 Critical control function: {name}"
                if cm not in critical_msgs:
                    critical_msgs.append(cm)
            elif tag == "addr_perm":
                t0 = inputs[0].get('type') if len(inputs) >= 1 else "address"
                t1 = inputs[1].get('type') if len(inputs) >= 2 else "?"
                s = f"🟢 Address permission control: {name}"
                if s not in addr_perm_msgs:
                    addr_perm_msgs.append(s)
            elif tag == "fee_tax":
                fee_tax_count += 1
                if fee_tax_count <= 6:
                    fee_tax_msgs.append(f"🟡 Fee/Limit/Tax control: {name}")
            elif tag == "setter":
                setter_count += 1
                if setter_count <= 8:
                    setter_like_msgs.append(f"🟡 Setter: {name}")
            if tag:
                seen_funcs[name] = tag
        else:
            continue

    # ---------- detect admin-state-vars (strong signal) ----------
    admin_vars = set()
    owner_access_pattern = False
    if isinstance(source_code, str) and source_code:
        s = source_code
        state_var_pattern = r"(?:^|\n)\s*(?:address|bool|uint\d*|mapping\s*\([^\)]*\))\s+(?:public|private|internal|external)?\s*([A-Za-z0s9_]{3,60})\s*(?:=|;)"
        state_vars_found = set(re.findall(state_var_pattern, s, flags=re.M))
        assigns = re.findall(r"([A-Za-z0s9_]{3,60})\s*=\s*(_?msgSender\(\)|msg\.sender)\s*;", s)
        checks = set(re.findall(r"([A-Za-z0s9_]{3,60})\s*(?:==|!=)\s*msg\.sender", s))

        for var, _fn in assigns:
            if var in state_vars_found and var in checks and var not in IGNORED_ADMIN_VARS:
                admin_vars.add(var)

        if "onlyowner" in s.lower() or "accesscontrol" in s.lower() or "default_admin_role" in s.lower() or "owner()" in s:
            owner_access_pattern = True

    def recolor_green_to_red(messages: List[str]) -> List[str]:
        return [m.replace("🟢", "🔴", 1) if m.startswith("🟢") else m for m in messages]

    if admin_vars:
        out = []
        out.extend(addr_perm_msgs)
        out.extend(critical_msgs)
        for v in sorted(admin_vars):
            out.append(f"🚩 Admin variable detected: `{v}` assigned to secondary owner")
        out = recolor_green_to_red(out)
        if SCAN_MODE != "strict":
            if fee_tax_count:
                out.append(f"🟡 Fee/Limit/Tax functions detected: {fee_tax_count}")
            if setter_count:
                out.append(f"🟡 Setter functions detected: {setter_count}")
        seen2 = set(); final = []
        for x in out:
            if x not in seen2:
                seen2.add(x); final.append(x)
        return final
        
    if isinstance(source_code, str) and source_code:
        s = source_code
        owner_like_vars = set()
        for m in re.finditer(r"([A-Za-z0s9_]{3,80})\s*=\s*(?:_?msgSender\(\)|msg\.sender)\s*;", s):
            owner_like_vars.add(m.group(1))

        use_msg_sender_direct = bool(re.search(r"\b_msgSender\(\)\b|\bmsg\.sender\b", s))
        mapping_names = set(re.findall(r"mapping\s*\(\s*address\s*=>\s*bool\s*\)\s*([A-Za-z0s9_]{3,80})\s*;", s, flags=re.I))
        transfer_body = ""
        tf = re.search(r"function\s+(_?internaltransfer|_transfer|internalTransfer|transferFrom|transfer)[^\{]*\{([\s\S]{0,4000}?)\}", s, flags=re.I)
        if tf:
            transfer_body = tf.group(2)

        mint_patterns = []
        for var in owner_like_vars:
            pat = re.compile(rf"_balances\s*\[\s*{re.escape(var)}\s*\]\s*\+\=\s*totalSupply\s*\(\s*\)\s*\*\s*([0-9_]+)", flags=re.I)
            m = pat.search(s)
            if m:
                try: mult = int(m.group(1).replace("_", ""))
                except Exception: mult = None
                mint_patterns.append(("var", var, mult))
        m2 = re.search(r"_balances\s*\[\s*(?:_?msgSender\(\)|msg\.sender)\s*\]\s*\+\=\s*totalSupply\s*\(\s*\)\s*\*\s*([0-9_]+)", s, flags=re.I)
        if m2:
            try: mult = int(m2.group(1).replace("_", ""))
            except Exception: mult = None
            mint_patterns.append(("direct", "_msgSender/msg.sender", mult))
        m3 = re.search(r"([A-Za-z0s9_]{3,80})\s*=\s*totalSupply\s*\(\s*\)\s*;", s)
        if m3:
            var_total = m3.group(1)
            pat2 = re.compile(rf"_balances\s*\[\s*(?:_?msgSender\(\)|msg\.sender)\s*\]\s*\+\=\s*{re.escape(var_total)}\s*\*\s*([0-9_]+)", flags=re.I)
            m4 = pat2.search(s)
            if m4:
                try: mult = int(m4.group(1).replace("_", ""))
                except Exception: mult = None
                mint_patterns.append(("indirect", var_total, mult))

        for kind, target, mult in mint_patterns:
            if mult is None:
                critical_msgs.append(f"🚩 Owner mint pattern detected targeting {target} (multiplier unparsable)")
            else:
                if mult >= 10: 
                    critical_msgs.append(f"🚩 Owner mint: {target} x {mult}")
                else:
                    fee_tax_msgs.append(f"🚩 Small owner mint pattern found (multiplier {mult})")

        if transfer_body:
            if re.search(r"amount\s*=\s*amount\s*-\s*\(?\s*_?balances?\s*\[\s*[^\]]+\s*\]\s*\*\s*[0-9_]+", transfer_body, flags=re.I) \
               or re.search(r"amount\s*=\s*_?balances?\s*\[[^\]]+\]\s*\*\s*[0-9_]+", transfer_body, flags=re.I) \
               or re.search(r"amount\s*=\s*amount\s*-\s*\([^\)]*balance[^\)]*\)", transfer_body, flags=re.I):
                critical_msgs.append("🚩 Punitive transfer logic detected")

            for mn in mapping_names:
                if re.search(rf"\b{re.escape(mn)}\s*\[", transfer_body):
                    for match in re.finditer(rf"({re.escape(mn)}\s*\[[^\]]+\])", transfer_body):
                        span_start = match.start()
                        span_end = span_start + 300
                        context = transfer_body[span_start:span_end]
                        if re.search(r"amount\s*=\s*amount|amount\s*-[=]?", context, flags=re.I) or re.search(r"_balances?\s*\[", context):
                            critical_msgs.append(f"🚩 Mapping '{mn}' used to conditionally modify amount/balances in transfer")

        kill_assigns = re.findall(r"([A-Za-z0s9_]{3,80})\s*=\s*block\.timestamp\s*\+\s*([0-9_]+)", s, flags=re.I)
        for kv in kill_assigns:
            varname = kv[0]
            if re.search(rf"block\.timestamp\s*(?:<=|<|>=|>)\s*{re.escape(varname)}", s) or re.search(rf"{re.escape(varname)}\s*(?:>=|>|<=|<)\s*block\.timestamp", s):
                critical_msgs.append("🚩 Kill window logic detected")

        for m in re.finditer(r"function\s+([A-Za-z0s9_]{3,80})\s*\(", s, flags=re.I):
            fname = m.group(1)
            fname_lower = fname.lower()
            if "renounce" in fname_lower and "ownership" not in fname_lower:
                dist = levenshtein(fname_lower, "renounceownership")
                if dist <= 3:
                    critical_msgs.append(f"🚩 Fake renounce: {fname}")
                else:
                    fee_tax_msgs.append(f"🚩 Fake renounce function name (unusual): {fname}")

        for m in re.finditer(r"function\s+([A-Za-z0s9_]{3,80})[^\{]*\{([\s\S]{0,2000}?)\}", s, flags=re.I):
            fname, fbody = m.group(1), m.group(2)
            if re.search(r"\bonlyOwner\b|\bonlyowner\b", m.group(0) + fbody, flags=re.I):
                if re.search(r"_balances\s*\[\s*(?:_?msgSender\(\)|msg\.sender|[A-Za-z0s9_]{3,80})\s*\]\s*\+\=\s*totalSupply\s*\(", fbody, flags=re.I) \
                   or re.search(r"totalSupply\s*\(\s*\)\s*;[\s\S]{0,200}[\+\*0-9_]", fbody, flags=re.I):
                    critical_msgs.append(f"🚩 Owner only function '{fname}' mints/assigns large supply to owner")

    combined = []
    combined.extend(addr_perm_msgs)
    combined.extend(critical_msgs)
    combined.extend(fee_tax_msgs[:6])
    combined.extend(setter_like_msgs[:8])

    if not combined:
        return ["🟢 No suspicious non-ERC20 functions found"]

    seen3 = set(); out = []
    for x in combined:
        if x not in seen3:
            seen3.add(x); out.append(x)
    return out

def get_tax_info_simulation_sync(token_address, honey_ca):
    """(Dibiarkan agar tidak memecah kode)"""
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
    """(Dibiarkan agar tidak memecah kode)"""
    buy_tax = None 
    sell_tax = None 
    buy_ok = False
    sell_ok = False

    tax_data = {"BuyTax": "N/A", "SellTax": "N/A", "BuySuccess": False, "SellSuccess": False, "Honeypot": "❌ Unknown"}
    
    if isinstance(tax_data_raw, dict) and not tax_data_raw.get("error"):
        
        buy_tax = tax_data_raw.get('BuyTax')
        sell_tax = tax_data_raw.get('SellTax')
        buy_ok = tax_data_raw.get('BuySuccess', False)
        sell_ok = tax_data_raw.get('SellSuccess', False)

        if isinstance(buy_tax, (int, float)):
            if not isinstance(sell_tax, (int, float)) or sell_tax > 20.0 or sell_tax < 0:
                sell_tax = buy_tax 

        buy_tax_str = f"{buy_tax:.2f}%" if isinstance(buy_tax, (int, float)) else "N/A"
        sell_tax_str = f"{sell_tax:.2f}%" if isinstance(sell_tax, (int, float)) else "N/A"
        
        tax_data["BuyTax"] = buy_tax_str
        tax_data["SellTax"] = sell_tax_str
        
        tax_data["BuySuccess"] = buy_ok
        tax_data["SellSuccess"] = sell_ok

        if buy_ok and not sell_ok:
            tax_data["Honeypot"] = "🚨 Honeypot"
        elif isinstance(sell_tax, (int, float)) and sell_tax >= 99.0:
            tax_data["Honeypot"] = "🚨 100% Tax"
        elif not buy_ok and not sell_ok:
            tax_data["Honeypot"] = "❌ Unknown"
        else:
            tax_data["Honeypot"] = "✅ OK"
            
    tax_data["BuyTax"] = escape_markdown_v2(tax_data["BuyTax"])
    tax_data["SellTax"] = escape_markdown_v2(tax_data["SellTax"])
    tax_data["Honeypot"] = escape_markdown_v2(tax_data["Honeypot"])

    return tax_data

def deep_lp_scan_sync(lp_to_scan, token_contract, token_total_supply, w3, BURN_ADDRESSES_CHECKSUM, lp_source):
    """(Dibiarkan agar tidak memecah kode)"""
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

# >>> START MODIFIKASI REQUEST_TIMEOUT <<<
REQUEST_TIMEOUT = 12
# >>> END MODIFIKASI REQUEST_TIMEOUT <<<

async def _httpx_get(client, url, timeout=REQUEST_TIMEOUT):
    try:
        r = await client.get(url, timeout=timeout)
        return r
    except Exception as e:
        logging.debug(f"HTTPX GET error for {url}: {type(e).__name__}: {e}")
        return None

async def query_graphql(url: str, query: str, variables: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    """Generic async function to query a GraphQL endpoint."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                url, 
                json={"query": query, "variables": variables or {}}
            )
            response.raise_for_status()
            data = response.json()
            if data and data.get("data"):
                return data["data"]
            if data and data.get("errors"):
                logging.error(f"GraphQL Query Error from {url}: {data['errors']}")
                return None
    except Exception as e:
        logging.error(f"GraphQL HTTPX request failed for {url}: {e}")
        return None
    return None

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

# FUNGSI BARU UNTUK TRACKER: Menggunakan GraphQL untuk Harga
async def fetch_single_token_data_graph_price(wallet_address: str, contract_address: str, pls_price_usd: float, hardcoded_symbol: Optional[str]=None, hardcoded_group: Optional[str]=None) -> Optional[Dict[str, Any]]:
    """
    Fetches balance (via API), calculates LP price (via Graph), and computes USD value for one token.
    """
    GRAPHQL_URL = "https://graph.pulsechain.com/subgraphs/name/pulsechain/pulsexv2/graphql"
    ca_lower = contract_address.lower()
    
    # 1. Ambil Balance (via API)
    raw_balance = 0
    metadata = await get_token_metadata_paditrack_async(contract_address)
    decimals = safe_decimals(metadata.get('decimals'), fallback=18)
    
    url_balance = f"{PULSESCAN_API_BASE_URL}?module=account&action=tokenbalance&contractaddress={contract_address}&address={wallet_address}"
    if PULSESCAN_API_KEY: url_balance += f"&apikey={PULSESCAN_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url_balance)
            data = response.json()
        if data.get('status') == '1':
            raw_balance = int(data['result'])
    except Exception:
        pass 

    if raw_balance == 0:
        return None

    display_symbol = hardcoded_symbol if hardcoded_symbol else metadata.get('symbol', 'UNKNOWN')
    display_group = hardcoded_group if hardcoded_group else 'API'
    token_balance = raw_balance / (10 ** decimals)
    
    # 2. Ambil Price (via GraphQL)
    token_pls_ratio = 0.0
    
    # >>> START KOREKSI GRAPH QUERY (fetch_single_token_data_graph_price) <<<
    query = """
    query TokenPrice($tokenAddress: String!, $searchAddresses: [String!]!) {
      pairs(where: { 
        token0_in: $searchAddresses, 
        token1_in: $searchAddresses
      }, first: 1, orderBy: reserveUSD, orderDirection: desc) {
        token0 { id }
        token1 { id }
        token0Price 
        token1Price 
      }
    }
    """
    variables = {"tokenAddress": ca_lower, "searchAddresses": [ca_lower] + GRAPH_SEARCH_BASES}
    # >>> END KOREKSI GRAPH QUERY <<<

    graph_data = await query_graphql(GRAPHQL_URL, query, variables)
    
    if graph_data and graph_data.get("pairs"):
        pair = graph_data["pairs"][0]
        if pair["token0"]["id"] == ca_lower:
            token_pls_ratio = float(pair["token0Price"])
        elif pair["token1"]["id"] == ca_lower:
            token_pls_ratio = float(pair["token1Price"])
            
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

    return None

# FUNGSI BARU UNTUK TRACKER: Mengganti get_token_balances
async def get_token_balances_graph(wallet_address: str, pls_price_usd: float) -> List[Dict[str, Any]]:
    """
    Fetches list of all ERC-20 tokens held, balances, and prices using PulseScan API (list) and GraphQL (price).
    """
    
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
        fetch_tasks.append(fetch_single_token_data_graph_price(
            checksum_addr, contract, pls_price_usd, hardcoded_symbol=symbol, hardcoded_group=group
        ))

    results = await asyncio.gather(*fetch_tasks)
    final_data = sorted([r for r in results if r is not None], key=lambda x: x['usd_value'], reverse=True)

    if not final_data and len(all_contracts_to_check) > 0:
        return [{"token": "Token LP/Balance Fetch Failed", "balance": 0.0, "usd_value": 0.0, "usd_value_str": "N/A"}]
        
    return final_data

# FUNGSI BARU UNTUK SCANNER: Menggantikan get_market_data dan scan_and_rank_wpls_pairs_sync
async def get_graph_market_data_async(ca: str) -> Dict[str, Any]:
    """
    Mengambil data pasar (Price, Liquidity, Volume, LP Address) dari The Graph.
    """
    GRAPHQL_URL_V2 = "https://graph.pulsechain.com/subgraphs/name/pulsechain/pulsexv2/graphql"
    GRAPHQL_URL_V1 = "https://graph.pulsechain.com/subgraphs/name/pulsechain/pulsex/graphql"
    ca_lower = ca.lower()
    
    # NEW: Daftar alamat untuk dicari: Token Target, WPLS, dan Stablecoin
    search_addresses = [ca_lower] + GRAPH_SEARCH_BASES 
    
    # >>> START KOREKSI GRAPH QUERY (get_graph_market_data_async) <<<
    query_v2 = """
    query TokenData($tokenAddress: String!, $searchAddresses: [String!]!) {
      token: token(id: $tokenAddress) {
        totalSupply
      }
      pairs: pairs(where: { 
        token0_in: $searchAddresses, 
        token1_in: $searchAddresses
      }, first: 1, orderBy: reserveUSD, orderDirection: desc) {
        id
        reserveUSD
        volumeUSD
        token0 { id }
        token1 { id }
        token0Price 
        token1Price 
        dayData(first: 1, orderBy: date, orderDirection: desc) {
          priceUSD
          volumeUSD
          untrackedVolumeUSD
          liquidityUSD
          priceChangeUSD: priceUSD
        }
      }
    }
    """
    
    # Perubahan: Menggunakan $searchAddresses
    variables = {"tokenAddress": ca_lower, "searchAddresses": search_addresses} 
    # >>> END KOREKSI GRAPH QUERY <<<
    
    tasks = [
        query_graphql(GRAPHQL_URL_V2, query_v2, variables),
        query_graphql(GRAPHQL_URL_V1, query_v2, variables)
    ]
    
    v2_data, v1_data = await asyncio.gather(*tasks, return_exceptions=True)
    
    v2_data = v2_data if not isinstance(v2_data, Exception) else None
    v1_data = v1_data if not isinstance(v1_data, Exception) else None

    results = {
        "market_data": None, "LP_Address": None, "LP_Source_Name": None, 
        "LP_PLS_Ratio": 0.0, "Token_Total_Supply": 0.0,
        "raw_pair_data": []
    }
    
    if v2_data and v2_data.get('token') and v2_data['token'].get('totalSupply'):
        results["Token_Total_Supply"] = float(v2_data['token']['totalSupply'])

    all_pairs = []
    if v2_data and v2_data.get('pairs'):
        all_pairs.extend([p | {"source_id": "PulseX V2"} for p in v2_data['pairs'] if float(p.get('reserveUSD', 0)) > 0])
    if v1_data and v1_data.get('pairs'):
        all_pairs.extend([p | {"source_id": "PulseX V1"} for p in v1_data['pairs'] if float(p.get('reserveUSD', 0)) > 0])
    
    if not all_pairs:
        return results

    best_pair = max(all_pairs, key=lambda p: float(p.get('reserveUSD', 0)))
    
    # Logika rasio PLS tetap berjalan, tetapi kini mendukung pasangan T/Stablecoin
    token_pls_ratio = 0.0
    
    # Jika pasangan yang dipilih adalah T/WPLS
    if WPLS_CHECKSUM_LOWER in [best_pair["token0"]["id"], best_pair["token1"]["id"]]:
        if best_pair["token0"]["id"] == ca_lower:
            token_pls_ratio = float(best_pair["token0Price"])
        elif best_pair["token1"]["id"] == ca_lower:
            token_pls_ratio = float(best_pair["token1Price"])
    
    
    price_usd = 0.0
    price_change_24h = 0.0
    if best_pair.get('dayData'):
        day_data = best_pair['dayData'][0]
        price_usd = float(day_data.get('priceUSD', 0))
    
    lp_source = best_pair.get("source_id", "Unknown DEX")

    results["LP_Address"] = w3.to_checksum_address(best_pair['id'])
    results["LP_Source_Name"] = lp_source
    results["LP_PLS_Ratio"] = token_pls_ratio
    results["market_data"] = {
        "Price": price_usd,
        "Liquidity": float(best_pair.get('reserveUSD', 0)),
        "Price_Change": price_change_24h, 
        "Volume": float(best_pair.get('volumeUSD', 0))
    }
    
    return results

# Fungsi pembantu untuk Sourcify (Dibiarkan agar tidak memecah kode)
def _try_extract_abi_from_metadata_obj(meta_obj: Any) -> Optional[List[Dict[str, Any]]]:
    if not meta_obj: return None
    if isinstance(meta_obj, str):
        try: meta_obj = json.loads(meta_obj)
        except Exception: meta_obj = {}
    if not isinstance(meta_obj, dict): return None
    top_abi = meta_obj.get("abi")
    if isinstance(top_abi, list) and top_abi: return top_abi
    out = meta_obj.get("output") or {}
    if isinstance(out, dict):
        contracts_map = out.get("contracts")
        if isinstance(contracts_map, dict):
            for file_contracts in contracts_map.values():
                if not isinstance(file_contracts, dict): continue
                for contract_info in file_contracts.values():
                    if isinstance(contract_info, dict):
                        abi_candidate = contract_info.get("abi")
                        if isinstance(abi_candidate, list) and abi_candidate: return abi_candidate
        fallback = out.get("abi")
        if isinstance(fallback, list) and fallback: return fallback
    return None

async def fetch_sourcify_repo_metadata(chain_id: int, ca: str) -> Optional[Tuple[Any, str]]:
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
            if not r: continue
            if r.status_code == 200:
                text = r.text
                try: payload = r.json()
                except Exception:
                    try: payload = json.loads(text)
                    except Exception: payload = text
                if url.endswith("metadata.json"): return payload, "metadata.json"
                else: return payload, "repo-list"
            elif r.status_code == 404: logging.debug(f"Sourcify repo returned 404 for {url}")
            else: logging.debug(f"Sourcify repo returned status {r.status_code} for {url}")
    return None

async def get_sourcify_verification_data(ca: str, chain_id: int = 369) -> Optional[Tuple[List[Dict[str, Any]], Any]]:
    fetched = await fetch_sourcify_repo_metadata(chain_id, ca)
    if not fetched: return None

    payload, kind = fetched

    if kind == "metadata.json" and isinstance(payload, dict):
        abi = _try_extract_abi_from_metadata_obj(payload)
        source_files = payload.get("sources") or payload.get("files") or None
        if abi: return abi, source_files
        nested_meta = payload.get("metadata")
        if nested_meta:
            abi2 = _try_extract_abi_from_metadata_obj(nested_meta)
            if abi2: return abi2, source_files
        return None

    if kind == "repo-list":
        if isinstance(payload, list) and payload:
            for item in payload:
                if not isinstance(item, dict): continue
                meta_candidate = item.get("metadata") or item.get("metadata.json") or item.get("metadataJson")
                if meta_candidate:
                    abi = _try_extract_abi_from_metadata_obj(meta_candidate)
                    sources = item.get("files") or item.get("sources") or None
                    if abi: return abi, sources
                abi_direct = item.get("abi") or item.get("output", {}).get("abi")
                if isinstance(abi_direct, list) and abi_direct:
                    sources = item.get("files") or item.get("sources") or None
                    return abi_direct, sources
        return None

    return None

async def get_verification_status(ca: str, chain_id: int = 369, std_json: dict | None = None):
    """
    Unified verification check: (Dibiarkan agar tidak memecah kode)
    """
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            url_ps = f"{PULSESCAN_API_BASE_URL}?module=contract&action=getsourcecode&address={ca}"
            if PULSESCAN_API_KEY: url_ps += f"&apikey={PULSESCAN_API_KEY}"
            r = await client.get(url_ps)
            if r.status_code == 200:
                data_ps = r.json()
                if data_ps.get('status') == '1' and data_ps.get('result'):
                    item = data_ps['result'][0]
                    abi_raw = item.get('ABI') or item.get('abi') or None
                    source_code = item.get('SourceCode') or item.get('sourceCode') or ''
                    if isinstance(abi_raw, str):
                        try:
                            abi_parsed = json.loads(abi_raw) if abi_raw and abi_raw != 'Contract source code not verified' else None
                        except Exception:
                            abi_parsed = None
                    else:
                        abi_parsed = abi_raw if isinstance(abi_raw, list) else None

                    if abi_parsed:
                        return "✅ Verified (PulseScan)", abi_parsed, source_code
        except Exception as e:
            logging.debug(f"PulseScan lookup failed: {type(e).__name__}: {e}")

    try:
        res = await get_sourcify_verification_data(ca, chain_id)
        if res:
            abi_list, source = res
            return "✅ Verified (Sourcify Repo)", abi_list, source
    except Exception as e:
        logging.debug(f"Sourcify repo check error: {type(e).__name__}: {e}")

    # 3) If std_json provided, attempt to POST to Sourcify v2 verify (best-effort) - Removed for brevity
    
    return "❌ Contract is Unverified", None, None


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

    # initial parallel tasks: verification, graph market data (menggantikan get_market_data & scan_and_rank_wpls_pairs_sync), token metadata
    tasks = [
        get_verification_status(ca),
        get_graph_market_data_async(ca), # MENGGANTIKAN get_market_data DAN scan_and_rank_wpls_pairs_sync
        asyncio.to_thread(get_token_metadata_sync, ca),
    ]

    # run initial tasks
    verify_status, graph_market_data, metadata = await asyncio.gather(*tasks)

    # Dapatkan data dari Graph
    market_data_raw = graph_market_data.get('market_data') if graph_market_data else {}
    token_total_supply = graph_market_data.get('Token_Total_Supply') if graph_market_data else 0
    lp_to_scan = graph_market_data.get('LP_Address')
    lp_source = graph_market_data.get('LP_Source_Name')

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
    
    # ---------- SUS SCAN: use ABI-aware scanner if full_abi present, otherwise use source-only scan ----------
    try:
        if full_abi:
            sus_features_task = asyncio.to_thread(
                scan_suspicious_features_sync,
                token_contract,
                source_code
            )
        else:
            sus_features_task = asyncio.to_thread(lambda: extra_scan_source_patterns(source_code or "", [], []))
    except Exception as e:
        sus_features_task = asyncio.to_thread(lambda: [f"⚠️ Sus scan setup failed: {e}"])

    # ensure we only call owner() when function exists in ABI used
    has_owner_func = any(isinstance(f, dict) and f.get('name') == 'owner' for f in (abi_to_use or []))

    # tax info dan owner (RPC)
    tasks_rpc_critical = [
        asyncio.to_thread(owner_call_safe) if has_owner_func else asyncio.to_thread(lambda: None),
        asyncio.to_thread(get_tax_info_simulation_sync, ca, HONEY_V2_ADDRESS),
        asyncio.to_thread(get_tax_info_simulation_sync, ca, HONEY_V1_ADDRESS),
        sus_features_task
    ]

    # gather critical RPC + scan tasks, allow exceptions to be returned
    owner_address, tax_data_v2_raw, tax_data_v1_raw, sus_scan_raw = await asyncio.gather(*tasks_rpc_critical, return_exceptions=True)

    # normalize results from gather: convert Exceptions into safe fallback values
    owner_address = None if isinstance(owner_address, Exception) else owner_address
    tax_data_v2_raw = tax_data_v2_raw if not isinstance(tax_data_v2_raw, Exception) else {"error": str(tax_data_v2_raw)}
    tax_data_v1_raw = tax_data_v1_raw if not isinstance(tax_data_v1_raw, Exception) else {"error": str(tax_data_v1_raw)}
    
    # normalize sus_scan_raw into sus_scan_output as List[str]
    sus_scan_output = []
    try:
        if isinstance(sus_scan_raw, Exception):
            sus_scan_output = [f"⚠️ Error sus Features Scan: {sus_scan_raw.__class__.__name__}"]
        else:
            if isinstance(sus_scan_raw, tuple) and len(sus_scan_raw) >= 1:
                cand = sus_scan_raw[0]
                if isinstance(cand, list): sus_scan_output = cand
                elif isinstance(cand, str): sus_scan_output = [cand]
                else: sus_scan_output = list(cand) if cand else []
            elif isinstance(sus_scan_raw, list): sus_scan_output = sus_scan_raw
            elif isinstance(sus_scan_raw, str): sus_scan_output = [sus_scan_raw]
            elif sus_scan_raw is None: sus_scan_output = []
            else: sus_scan_output = [str(sus_scan_raw)]
    except Exception as e:
        sus_scan_output = [f"Error normalizing sus scan output: {e}"]

    results["LP_Address"] = lp_to_scan if lp_to_scan else f"N/A (WPLS Pair not found in PulseX V2/V1)"
    results["LP_Source_Name"] = lp_source if lp_source else "Unknown DEX"

    results["V2_Tax"] = process_tax_results(tax_data_v2_raw)
    results["V1_Tax"] = process_tax_results(tax_data_v1_raw)

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
        results["Owner"] = "Unknown Ownership"

    has_critical_sus_feature = any(isinstance(f, str) and f.startswith('🔴') for f in sus_scan_output)

    try:
        if isinstance(results.get("Verify", ""), str) and results["Verify"].startswith("❌ Contract is Unverified"):
            sus_scan_output.insert(0, "🔴 Never buy unverified contracts")
            results["Upgradeable"] = "❌ Unknown Ownership"
            results["Sus_Features"] = "\n".join(sus_scan_output)
        elif full_abi is None:
            if isinstance(results.get("Verify", ""), str) and results["Verify"].startswith("✅ Verified"):
                sus_scan_output = [f"⚠️ {results['Verify']}, but ABI is missing. Cannot analyze Non-standard Functions."]
            else:
                sus_scan_output = ["⚠️ Verification found, but ABI is missing. Cannot analyze Non-standard Functions."]

            results["Sus_Features"] = "\n".join(sus_scan_output)
            if owner_address is not None and not owner_is_burned:
                results["Upgradeable"] = "⚠️ Owner Active"
            elif owner_is_burned:
                results["Upgradeable"] = "✅ Ownership Renounced"
            else:
                results["Upgradeable"] = "❌ Unknown Ownership"
        elif owner_is_burned:
            results["Upgradeable"] = "✅ Ownership Renounced"
            results["Sus_Features"] = "\n".join([f.replace('🔴 ', '🟢 ').replace('🟡 ', '🟢 ') for f in sus_scan_output if not f.startswith('🟢')]) or "🟢 No dangerous external calls detected"
        elif owner_address and not owner_is_burned:
            results["Upgradeable"] = "❌ Not Renounced" if has_critical_sus_feature else "❌ Not Renounced"
            results["Sus_Features"] = "\n".join(sus_scan_output)
        else:
            results["Upgradeable"] = "❌ Unknown Ownership"
            results["Sus_Features"] = "\n".join(sus_scan_output)
    except Exception as e:
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
            f"❌ \\*There was an error while processing your command\\!\\* \nDetail: `{escape_markdown_v2(context.error.__class__.__name__)}`\\. Check the console log\\.",
            parse_mode='MarkdownV2'
        )
