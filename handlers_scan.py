# handlers_scan.py

import re
import json
import asyncio
import httpx
import logging
from typing import List, Dict, Any, Optional, Tuple
from telegram import Update
from telegram.ext import ContextTypes
from web3.exceptions import InvalidAddress

# Import resources dari utils yang dibersihkan
from utils import (
    w3,
    PULSESCAN_API_BASE_URL,
    PULSESCAN_API_KEY,
    SOURCIFY_REPO,
    HONEY_V1_ADDRESS,
    HONEY_V2_ADDRESS,
    HONEY_ABI_MINIMAL,
    TOKEN_MINIMAL_ABI,
    WPLS_CHECKSUM_LOWER,
    BURN_ADDRESSES_CHECKSUM,
    SCAN_MODE,
    STANDARD_ERC20_FUNCTIONS,
    IGNORED_ADMIN_VARS,
    SAFE_SETTER_EXCLUDES,
    human_format,
    escape_markdown_v2,
    _safe_rpc_call,
    levenshtein,
    query_graphql,
    _httpx_get,
    get_token_metadata_sync
)

# --- FUNGSI PADI SCAN (Logic Internal) ---

def extra_scan_source_patterns(source_code: str, sus_list: list, detailed_flags: list = None):
    if not isinstance(source_code, str) or not source_code: return
    s = source_code
    state_var_pattern = r"(?:^|\n)\s*(?:address|bool|uint\d*|mapping\s*\([^\)]*\))\s+(?:public|private|internal|external)?\s*([A-Za-z0s9_]{3,40})\s*(?:=|;)"
    state_vars_found = set(re.findall(state_var_pattern, s, flags=re.M))
    admin_assigns = re.findall(r"([A-Za-z0s9_]{3,40})\s*=\s*(_?msgSender\(\)|msg\.sender)\s*;", s)
    for var, _fn in admin_assigns:
        if var not in state_vars_found: continue
        sus_list.append(f"🚩 Admin variable detected: `{var}` assigned to secondary owner")
        if detailed_flags is not None: detailed_flags.append({"type":"admin_var", "var": var})
    checks = re.findall(r"([A-Za-z0s9_]{3,40})\s*(!=|==)\s*msg\.sender", s)
    for var, op in checks:
        if var in state_vars_found or len(re.findall(r"\b" + re.escape(var) + r"\b", s)) > 4:
            sus_list.append(f"🚩 Access check using custom admin var `{var}` with operator `{op}`")
            if detailed_flags is not None: detailed_flags.append({"type":"admin_check", "var": var, "op": op})
    if re.search(r"\b([A-Za-z0s9_]{2,40})\s*=\s*\1\s*\^\s*\1\b", s):
        sus_list.append("🚩 XOR with self pattern detected")
        if detailed_flags is not None: detailed_flags.append({"type":"xor_zeroing"})
    if re.search(r"\b([A-Za-z0s9_]{2,40})\s*=\s*[A-Za-z0s9_]{2,40}\s*\^\s*[A-Za-z0s9_]{2,40}", s):
        sus_list.append("🚩 Potential bitwise zeroing pattern found")
        if detailed_flags is not None: detailed_flags.append({"type":"xor_like"})
    if re.search(r"deductAmount\s*=\s*balances\[[^\]]+\]\s*;|balances\[[^\]]+\]\s*-\=\s*deductAmount", s):
        sus_list.append("🚩 Function that deducts entire balances detected")
        if detailed_flags is not None: detailed_flags.append({"type":"burn_entire_balance"})
    if re.search(r"_totalSupply\s*[\+\-\*]?=|balances\[[^\]]+\]\s*\+\=\s*[A-Za-z0s9_]+", s):
        sus_list.append("🚩 Modifies totalSupply or increases balances in code")
        if detailed_flags is not None: detailed_flags.append({"type":"mint_like"})
    if re.search(r"\b(balancesto|balancesfrom|blacklist|blocklist|isBlocked|isBanned)\b", s, flags=re.I):
        sus_list.append("🚩 Mapping flags found")
        if detailed_flags is not None: detailed_flags.append({"type":"mapping_flags"})
    if re.search(r"revert\(\s*\"[^\"]{1,6}\"\s*\)", s):
        sus_list.append("🟡 Short/obscure revert strings found")
        if detailed_flags is not None: detailed_flags.append({"type":"short_revert"})
    if re.search(r"_Holders\s*\[", s) or re.search(r"getTokenHolders\s*\(", s):
        sus_list.append("🟡 Contract collects token holder addresses")
        if detailed_flags is not None: detailed_flags.append({"type":"holders_list"})
    if re.search(r"function\s+[A-Za-z0s9_]*renounc[e|i][A-Za-z0s9_]*\s*\(", s, flags=re.I):
        sus_list.append("🚩 Suspicious fake renounce function name found")
        if detailed_flags is not None: detailed_flags.append({"type":"renounce_like"})
    if re.search(r"_balances\s*\[\s*_?msgSender\(\)\s*\]\s*\+\=\s*totalSupply\s*\(\s*\)\s*\*\s*[0-9]{2,}", s):
        sus_list.append("🚩 Owner mint via fake renounce function detected")
        if detailed_flags is not None: detailed_flags.append({"type":"owner_mint_totalSupply_mul"})
    if re.search(r"\b(ddsa|balancesto|balancesfrom|blacklist|isBlocked|isBanned)\b", s, flags=re.I):
        sus_list.append("🚩 Blacklist/flag mapping and custom transfer logic found")
        if detailed_flags is not None: detailed_flags.append({"type":"mapping_flag_transfer"})
    if re.search(r"_killEndTime|killEndTime", s) and re.search(r"block\.timestamp\s*<=\s*_killEndTime", s):
        sus_list.append("🚩 Kill window logic detected")
        if detailed_flags is not None: detailed_flags.append({"type":"kill_window"})
    return

def scan_suspicious_features_sync(contract, source_code: str = None) -> List[str]:
    abi = getattr(contract, "abi", None) or []
    addr_perm_msgs = []; critical_msgs = []; fee_tax_msgs = []; setter_like_msgs = []
    def is_address_param(p): return p.get("type","").startswith("address")
    def is_bool_param(p): return p.get("type","") == "bool"
    def is_uint_param(p): return p.get("type","").startswith("uint")
    PRIORITY = {"critical": 0, "addr_perm": 1, "fee_tax": 2, "setter": 3, "other": 4}
    seen_funcs = {}; fee_tax_count = 0; setter_count = 0

    for f in abi:
        if f.get("type") != "function": continue
        name = f.get("name","") or ""; lname = name.lower(); inputs = f.get("inputs",[]) or []
        if name in STANDARD_ERC20_FUNCTIONS: continue
        tag = None; tag_priority = PRIORITY["other"]
        if "transfertoburn" in lname or lname == "transfertoburn":
            tag = "critical"; tag_priority = PRIORITY["critical"]
        elif any(k in lname for k in ("fee","tax","settax","setfee","gettax","getfee","treasury","marketing","liquidity")):
            tag = "fee_tax"; tag_priority = PRIORITY["fee_tax"]
        elif len(inputs) >= 2 and is_address_param(inputs[0]) and (is_bool_param(inputs[1]) or is_uint_param(inputs[1])):
            tag = "addr_perm"; tag_priority = PRIORITY["addr_perm"]
        elif re.match(r'^(set|enable|disable|update|grant|revoke|transfer|withdraw|mint|burn)', name, flags=re.I):
            if name.lower() not in SAFE_SETTER_EXCLUDES:
                tag = "setter"; tag_priority = PRIORITY["setter"]
        prev_tag = seen_funcs.get(name)
        prev_priority = PRIORITY.get(prev_tag, PRIORITY["other"]) if prev_tag else None
        if prev_tag is None or (prev_priority is not None and tag_priority < prev_priority):
            if tag == "critical":
                cm = f"🔴 Critical control function: {name}"
                if cm not in critical_msgs: critical_msgs.append(cm)
            elif tag == "addr_perm":
                s = f"🟢 Address permission control: {name}"
                if s not in addr_perm_msgs: addr_perm_msgs.append(s)
            elif tag == "fee_tax":
                fee_tax_count += 1
                if fee_tax_count <= 6: fee_tax_msgs.append(f"🟡 Fee/Limit/Tax control: {name}")
            elif tag == "setter":
                setter_count += 1
                if setter_count <= 8: setter_like_msgs.append(f"🟡 Setter: {name}")
            if tag: seen_funcs[name] = tag
        else: continue

    admin_vars = set(); owner_access_pattern = False
    if isinstance(source_code, str) and source_code:
        s = source_code
        state_var_pattern = r"(?:^|\n)\s*(?:address|bool|uint\d*|mapping\s*\([^\)]*\))\s+(?:public|private|internal|external)?\s*([A-Za-z0s9_]{3,60})\s*(?:=|;)"
        state_vars_found = set(re.findall(state_var_pattern, s, flags=re.M))
        assigns = re.findall(r"([A-Za-z0s9_]{3,60})\s*=\s*(_?msgSender\(\)|msg\.sender)\s*;", s)
        checks = set(re.findall(r"([A-Za-z0s9_]{3,60})\s*(?:==|!=)\s*msg\.sender", s))
        for var, _fn in assigns:
            if var in state_vars_found and var in checks and var not in IGNORED_ADMIN_VARS: admin_vars.add(var)
        if "onlyowner" in s.lower() or "accesscontrol" in s.lower() or "default_admin_role" in s.lower() or "owner()" in s: owner_access_pattern = True

    def recolor_green_to_red(messages: List[str]) -> List[str]:
        return [m.replace("🟢", "🔴", 1) if m.startswith("🟢") else m for m in messages]

    if admin_vars:
        out = []; out.extend(addr_perm_msgs); out.extend(critical_msgs)
        for v in sorted(admin_vars): out.append(f"🚩 Admin variable detected: `{v}` assigned to secondary owner")
        out = recolor_green_to_red(out)
        if SCAN_MODE != "strict":
            if fee_tax_count: out.append(f"🟡 Fee/Limit/Tax functions detected: {fee_tax_count}")
            if setter_count: out.append(f"🟡 Setter functions detected: {setter_count}")
        seen2 = set(); final = []
        for x in out:
            if x not in seen2: seen2.add(x); final.append(x)
        return final
        
    if isinstance(source_code, str) and source_code:
        s = source_code
        owner_like_vars = set()
        for m in re.finditer(r"([A-Za-z0s9_]{3,80})\s*=\s*(?:_?msgSender\(\)|msg\.sender)\s*;", s): owner_like_vars.add(m.group(1))
        mapping_names = set(re.findall(r"mapping\s*\(\s*address\s*=>\s*bool\s*\)\s*([A-Za-z0s9_]{3,80})\s*;", s, flags=re.I))
        transfer_body = ""
        tf = re.search(r"function\s+(_?internaltransfer|_transfer|internalTransfer|transferFrom|transfer)[^\{]*\{([\s\S]{0,4000}?)\}", s, flags=re.I)
        if tf: transfer_body = tf.group(2)
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
            if mult is None: critical_msgs.append(f"🚩 Owner mint pattern detected targeting {target} (multiplier unparsable)")
            else:
                if mult >= 10: critical_msgs.append(f"🚩 Owner mint: {target} x {mult}")
                else: fee_tax_msgs.append(f"🚩 Small owner mint pattern found (multiplier {mult})")
        if transfer_body:
            if re.search(r"amount\s*=\s*amount\s*-\s*\(?\s*_?balances?\s*\[\s*[^\]]+\s*\]\s*\*\s*[0-9_]+", transfer_body, flags=re.I) or re.search(r"amount\s*=\s*_?balances?\s*\[[^\]]+\]\s*\*\s*[0-9_]+", transfer_body, flags=re.I) or re.search(r"amount\s*=\s*amount\s*-\s*\([^\)]*balance[^\)]*\)", transfer_body, flags=re.I):
                critical_msgs.append("🚩 Punitive transfer logic detected")
            for mn in mapping_names:
                if re.search(rf"\b{re.escape(mn)}\s*\[", transfer_body):
                    for match in re.finditer(rf"({re.escape(mn)}\s*\[[^\]]+\])", transfer_body):
                        if re.search(r"amount\s*=\s*amount|amount\s*-[=]?", transfer_body[match.start():match.start()+300], flags=re.I) or re.search(r"_balances?\s*\[", transfer_body[match.start():match.start()+300]):
                            critical_msgs.append(f"🚩 Mapping '{mn}' used to conditionally modify amount/balances in transfer")
        kill_assigns = re.findall(r"([A-Za-z0s9_]{3,80})\s*=\s*block\.timestamp\s*\+\s*([0-9_]+)", s, flags=re.I)
        for kv in kill_assigns:
            varname = kv[0]
            if re.search(rf"block\.timestamp\s*(?:<=|<|>=|>)\s*{re.escape(varname)}", s) or re.search(rf"{re.escape(varname)}\s*(?:>=|>|<=|<)\s*block\.timestamp", s):
                critical_msgs.append("🚩 Kill window logic detected")
        for m in re.finditer(r"function\s+([A-Za-z0s9_]{3,80})\s*\(", s, flags=re.I):
            fname = m.group(1); fname_lower = fname.lower()
            if "renounce" in fname_lower and "ownership" not in fname_lower:
                dist = levenshtein(fname_lower, "renounceownership")
                if dist <= 3: critical_msgs.append(f"🚩 Fake renounce: {fname}")
                else: fee_tax_msgs.append(f"🚩 Fake renounce function name (unusual): {fname}")
        for m in re.finditer(r"function\s+([A-Za-z0s9_]{3,80})[^\{]*\{([\s\S]{0,2000}?)\}", s, flags=re.I):
            fname, fbody = m.group(1), m.group(2)
            if re.search(r"\bonlyOwner\b|\bonlyowner\b", m.group(0) + fbody, flags=re.I):
                if re.search(r"_balances\s*\[\s*(?:_?msgSender\(\)|msg\.sender|[A-Za-z0s9_]{3,80})\s*\]\s*\+\=\s*totalSupply\s*\(", fbody, flags=re.I) or re.search(r"totalSupply\s*\(\s*\)\s*;[\s\S]{0,200}[\+\*0-9_]", fbody, flags=re.I):
                    critical_msgs.append(f"🚩 Owner only function '{fname}' mints/assigns large supply to owner")

    combined = []; combined.extend(addr_perm_msgs); combined.extend(critical_msgs); combined.extend(fee_tax_msgs[:6]); combined.extend(setter_like_msgs[:8])
    if not combined: return ["🟢 No suspicious non-ERC20 functions found"]
    seen3 = set(); out = []
    for x in combined:
        if x not in seen3: seen3.add(x); out.append(x)
    return out

def get_tax_info_simulation_sync(token_address, honey_ca):
    tax_results = {"BuyTax": 0.0, "SellTax": 0.0, "BuySuccess": False, "SellSuccess": False}
    if not w3 or not honey_ca or not w3.is_address(honey_ca): return {"error": "HONEY Contract not deployed or invalid address"}
    try:
        honey_contract = w3.eth.contract(address=w3.to_checksum_address(honey_ca), abi=HONEY_ABI_MINIMAL)
        results = _safe_rpc_call(lambda: honey_contract.functions.checkHoneyMain(w3.to_checksum_address(token_address)).call({'gas': 5000000})) 
        if results is None or len(results) < 7: return {"error": "Tax simulation failed to return expected data."}
        buyEstimate, buyReal, sellEstimate, sellReal, buy, sell, _ = results
        tax_results["BuySuccess"] = buy; tax_results["SellSuccess"] = sell
        if buyEstimate > 0 and buyReal > 0: tax_results["BuyTax"] = round((buyEstimate - buyReal) / buyEstimate * 100, 2)
        elif buyEstimate > 0 and buyReal == 0 and buy: tax_results["BuyTax"] = 100.0
        elif not buy: tax_results["BuyTax"] = "Fail"
        if sellEstimate > 0 and sellReal > 0: tax_results["SellTax"] = round((sellEstimate - sellReal) / sellEstimate * 100, 2)
        elif sellEstimate > 0 and sellReal == 0 and sell: tax_results["SellTax"] = 100.0
        elif not sell: tax_results["SellTax"] = "Fail"
    except Exception as e:
        return {"error": f"Tax simulation failed: {e.__class__.__name__} - {str(e)}"}
    return tax_results

def process_tax_results(tax_data_raw):
    buy_tax = None; sell_tax = None; buy_ok = False; sell_ok = False
    tax_data = {"BuyTax": "N/A", "SellTax": "N/A", "BuySuccess": False, "SellSuccess": False, "Honeypot": "❌ Unknown"}
    if isinstance(tax_data_raw, dict) and not tax_data_raw.get("error"):
        buy_tax = tax_data_raw.get('BuyTax'); sell_tax = tax_data_raw.get('SellTax'); buy_ok = tax_data_raw.get('BuySuccess', False); sell_ok = tax_data_raw.get('SellSuccess', False)
        if isinstance(buy_tax, (int, float)):
            if not isinstance(sell_tax, (int, float)) or sell_tax > 20.0 or sell_tax < 0: sell_tax = buy_tax 
        buy_tax_str = f"{buy_tax:.2f}%" if isinstance(buy_tax, (int, float)) else "N/A"
        sell_tax_str = f"{sell_tax:.2f}%" if isinstance(sell_tax, (int, float)) else "N/A"
        tax_data["BuyTax"] = buy_tax_str; tax_data["SellTax"] = sell_tax_str; tax_data["BuySuccess"] = buy_ok; tax_data["SellSuccess"] = sell_ok
        if buy_ok and not sell_ok: tax_data["Honeypot"] = "🚨 Honeypot"
        elif isinstance(sell_tax, (int, float)) and sell_tax >= 99.0: tax_data["Honeypot"] = "🚨 100% Tax"
        elif not buy_ok and not sell_ok: tax_data["Honeypot"] = "❌ Unknown"
        else: tax_data["Honeypot"] = "✅ OK"
    tax_data["BuyTax"] = escape_markdown_v2(tax_data["BuyTax"]); tax_data["SellTax"] = escape_markdown_v2(tax_data["SellTax"]); tax_data["Honeypot"] = escape_markdown_v2(tax_data["Honeypot"])
    return tax_data

def deep_lp_scan_sync(lp_to_scan, token_contract, token_total_supply, w3, BURN_ADDRESSES_CHECKSUM, lp_source):
    data = {"LP_Source_Name": lp_source}
    try:
        lp_address_checksum = lp_to_scan 
        lp_contract = w3.eth.contract(address=lp_address_checksum, abi=TOKEN_MINIMAL_ABI)
        lp_total_supply = _safe_rpc_call(lp_contract.functions.totalSupply().call)
        if lp_total_supply is None or lp_total_supply == 0:
            data["LP_burnt"] = "N/A (LP Total Supply is 0)"; data["Supply_in_Pool"] = "N/A"
            return data
        lp_total_burnt_balance = sum(_safe_rpc_call(lambda: lp_contract.functions.balanceOf(a).call()) or 0 for a in BURN_ADDRESSES_CHECKSUM)
        percent_burnt = (lp_total_burnt_balance / lp_total_supply) * 100
        data["LP_burnt"] = f"{percent_burnt:.2f}% 🔥 | {lp_source}"
        token_total_burnt_balance = sum(_safe_rpc_call(lambda: token_contract.functions.balanceOf(a).call()) or 0 for a in BURN_ADDRESSES_CHECKSUM)
        if token_total_supply == 0: raise Exception("Total supply is zero")
        percent_supply_burnt = (token_total_burnt_balance / token_total_supply) * 100
        token_balance_in_pool = _safe_rpc_call(lambda: token_contract.functions.balanceOf(lp_address_checksum).call()) or 0
        percent_in_pool = (token_balance_in_pool / token_total_supply) * 100
        data["Supply_in_Pool"] = f"{percent_in_pool:.2f}% | {percent_supply_burnt:.2f}% 🔥Burn"
    except Exception as e:
        logging.error(f"Deep LP Scan failed: {e}")
        data["LP_burnt"] = "Error LP Scan"; data["Supply_in_Pool"] = "Error Supply Scan"
    return data

async def get_graph_market_data_async(ca: str) -> Dict[str, Any]:
    GRAPHQL_URL_V2 = "https://graph.pulsechain.com/subgraphs/name/pulsechain/pulsexv2/graphql"
    GRAPHQL_URL_V1 = "https://graph.pulsechain.com/subgraphs/name/pulsechain/pulsex/graphql"
    ca_lower = ca.lower()
    query_v2 = """
    query TokenData($tokenAddress: String!, $wplsAddress: String!) {
      token: token(id: $tokenAddress) { totalSupply }
      pairs: pairs(where: { and: [{ token0_in: [$tokenAddress, $wplsAddress] }, { token1_in: [$tokenAddress, $wplsAddress] }] }, first: 1, orderBy: reserveUSD, orderDirection: desc) {
        id; reserveUSD; volumeUSD
        token0 { id }; token1 { id }; token0Price; token1Price 
        dayData(first: 1, orderBy: date, orderDirection: desc) {
          priceUSD; volumeUSD; untrackedVolumeUSD; liquidityUSD; priceChangeUSD: priceUSD
        }
      }
    }
    """
    variables = {"tokenAddress": ca_lower, "wplsAddress": WPLS_CHECKSUM_LOWER}
    tasks = [query_graphql(GRAPHQL_URL_V2, query_v2, variables), query_graphql(GRAPHQL_URL_V1, query_v2, variables)]
    v2_data, v1_data = await asyncio.gather(*tasks, return_exceptions=True)
    v2_data = v2_data if not isinstance(v2_data, Exception) else None
    v1_data = v1_data if not isinstance(v1_data, Exception) else None

    results = {"market_data": None, "LP_Address": None, "LP_Source_Name": None, "LP_PLS_Ratio": 0.0, "Token_Total_Supply": 0.0, "raw_pair_data": []}
    
    if v2_data and v2_data.get('token') and v2_data['token'].get('totalSupply'): results["Token_Total_Supply"] = float(v2_data['token']['totalSupply'])
    all_pairs = []
    if v2_data and v2_data.get('pairs'): all_pairs.extend([p | {"source_id": "PulseX V2"} for p in v2_data['pairs'] if float(p.get('reserveUSD', 0)) > 0])
    if v1_data and v1_data.get('pairs'): all_pairs.extend([p | {"source_id": "PulseX V1"} for p in v1_data['pairs'] if float(p.get('reserveUSD', 0)) > 0])
    
    if not all_pairs: return results
    best_pair = max(all_pairs, key=lambda p: float(p.get('reserveUSD', 0)))
    if best_pair["token0"]["id"] == ca_lower: token_pls_ratio = float(best_pair["token0Price"])
    elif best_pair["token1"]["id"] == ca_lower: token_pls_ratio = float(best_pair["token1Price"])
    else: token_pls_ratio = 0.0

    price_usd = 0.0; price_change_24h = 0.0
    if best_pair.get('dayData'): day_data = best_pair['dayData'][0]; price_usd = float(day_data.get('priceUSD', 0))
    
    results["LP_Address"] = w3.to_checksum_address(best_pair['id'])
    results["LP_Source_Name"] = best_pair.get("source_id", "Unknown DEX")
    results["LP_PLS_Ratio"] = token_pls_ratio
    results["market_data"] = {"Price": price_usd, "Liquidity": float(best_pair.get('reserveUSD', 0)), "Price_Change": price_change_24h, "Volume": float(best_pair.get('volumeUSD', 0))}
    return results

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
    paths_to_try = [f"{SOURCIFY_REPO}/full_match/{chain_id}/{ca_norm}/metadata.json", f"{SOURCIFY_REPO}/partial_match/{chain_id}/{ca_norm}/metadata.json", f"{SOURCIFY_REPO}/full_match/{chain_id}/{ca_norm}", f"{SOURCIFY_REPO}/partial_match/{chain_id}/{ca_norm}"]
    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
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
                        try: abi_parsed = json.loads(abi_raw) if abi_raw and abi_raw != 'Contract source code not verified' else None
                        except Exception: abi_parsed = None
                    else: abi_parsed = abi_raw if isinstance(abi_raw, list) else None
                    if abi_parsed: return "✅ Verified (PulseScan)", abi_parsed, source_code
        except Exception as e:
            logging.debug(f"PulseScan lookup failed: {type(e).__name__}: {e}")
    try:
        res = await get_sourcify_verification_data(ca, chain_id)
        if res:
            abi_list, source = res
            return "✅ Verified (Sourcify Repo)", abi_list, source
    except Exception as e:
        logging.debug(f"Sourcify repo check error: {type(e).__name__}: {e}")
    return "❌ Contract is Unverified", None, None

async def deep_scan_contract(ca):
    results = {"metadata": {}, "Verify": "UNKNOWN", "Owner": "N/A (Owner function not found)", "Upgradeable": "UNKNOWN", "LP_Address": "N/A (PulseX V2/V1)", "LP_burnt": "N/A", "Supply_in_Pool": "N/A", "LP_Source_Name": "Unknown DEX", "Sus_Features": "N/A", "market_data": {}}
    if not w3 or not w3.is_connected(): results['Verify'] = "RPC Connection Failed"; return results
    tasks = [get_verification_status(ca), get_graph_market_data_async(ca), asyncio.to_thread(get_token_metadata_sync, ca)]
    verify_status, graph_market_data, metadata = await asyncio.gather(*tasks)

    market_data_raw = graph_market_data.get('market_data') if graph_market_data else {}
    token_total_supply = graph_market_data.get('Token_Total_Supply') if graph_market_data else 0
    lp_to_scan = graph_market_data.get('LP_Address'); lp_source = graph_market_data.get('LP_Source_Name')
    results["market_data"] = market_data_raw if market_data_raw and not market_data_raw.get("error") else {}
    try: results["Verify"], full_abi, source_code = verify_status
    except Exception: results["Verify"], full_abi, source_code = ("⚠️ Verification fetch failed", None, None)
    results["metadata"] = metadata
    abi_to_use = full_abi if full_abi else TOKEN_MINIMAL_ABI
    try: token_contract = w3.eth.contract(address=w3.to_checksum_address(ca), abi=abi_to_use)
    except Exception: results["Owner"] = "Error in Web3 Contract Init"; return results
    owner_call_safe = lambda: _safe_rpc_call(token_contract.functions.owner().call)
    try:
        if full_abi: sus_features_task = asyncio.to_thread(scan_suspicious_features_sync, token_contract, source_code)
        else: sus_features_task = asyncio.to_thread(lambda: extra_scan_source_patterns(source_code or "", [], []))
    except Exception as e: sus_features_task = asyncio.to_thread(lambda: [f"⚠️ Sus scan setup failed: {e}"])
    has_owner_func = any(isinstance(f, dict) and f.get('name') == 'owner' for f in (abi_to_use or []))
    tasks_rpc_critical = [asyncio.to_thread(owner_call_safe) if has_owner_func else asyncio.to_thread(lambda: None), asyncio.to_thread(get_tax_info_simulation_sync, ca, HONEY_V2_ADDRESS), asyncio.to_thread(get_tax_info_simulation_sync, ca, HONEY_V1_ADDRESS), sus_features_task]
    owner_address, tax_data_v2_raw, tax_data_v1_raw, sus_scan_raw = await asyncio.gather(*tasks_rpc_critical, return_exceptions=True)

    owner_address = None if isinstance(owner_address, Exception) else owner_address
    tax_data_v2_raw = tax_data_v2_raw if not isinstance(tax_data_v2_raw, Exception) else {"error": str(tax_data_v2_raw)}
    tax_data_v1_raw = tax_data_v1_raw if not isinstance(tax_data_v1_raw, Exception) else {"error": str(tax_data_v1_raw)}
    sus_scan_output = []
    try:
        if isinstance(sus_scan_raw, Exception): sus_scan_output = [f"⚠️ Error sus Features Scan: {sus_scan_raw.__class__.__name__}"]
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
    except Exception as e: sus_scan_output = [f"Error normalizing sus scan output: {e}"]

    results["LP_Address"] = lp_to_scan if lp_to_scan else f"N/A (WPLS Pair not found in PulseX V2/V1)"; results["LP_Source_Name"] = lp_source if lp_source else "Unknown DEX"
    results["V2_Tax"] = process_tax_results(tax_data_v2_raw); results["V1_Tax"] = process_tax_results(tax_data_v1_raw)
    owner_is_burned = False
    if owner_address is not None:
        try:
            owner_address_checksum = w3.to_checksum_address(owner_address)
            results["Owner"] = owner_address_checksum
            if owner_address_checksum in BURN_ADDRESSES_CHECKSUM: owner_is_burned = True
        except Exception: results["Owner"] = "Error Owner Check"
    else: results["Owner"] = "Unknown Ownership"
    has_critical_sus_feature = any(isinstance(f, str) and f.startswith('🔴') for f in sus_scan_output)
    try:
        if isinstance(results.get("Verify", ""), str) and results["Verify"].startswith("❌ Contract is Unverified"):
            sus_scan_output.insert(0, "🔴 Never buy unverified contracts"); results["Upgradeable"] = "❌ Unknown Ownership"; results["Sus_Features"] = "\n".join(sus_scan_output)
        elif full_abi is None:
            if isinstance(results.get("Verify", ""), str) and results["Verify"].startswith("✅ Verified"): sus_scan_output = [f"⚠️ {results['Verify']}, but ABI is missing. Cannot analyze Non-standard Functions."]
            else: sus_scan_output = ["⚠️ Verification found, but ABI is missing. Cannot analyze Non-standard Functions."]
            results["Sus_Features"] = "\n".join(sus_scan_output)
            if owner_address is not None and not owner_is_burned: results["Upgradeable"] = "⚠️ Owner Active"
            elif owner_is_burned: results["Upgradeable"] = "✅ Ownership Renounced"
            else: results["Upgradeable"] = "❌ Unknown Ownership"
        elif owner_is_burned:
            results["Upgradeable"] = "✅ Ownership Renounced"
            results["Sus_Features"] = "\n".join([f.replace('🔴 ', '🟢 ').replace('🟡 ', '🟢 ') for f in sus_scan_output if not f.startswith('🟢')]) or "🟢 No dangerous external calls detected"
        elif owner_address and not owner_is_burned:
            results["Upgradeable"] = "❌ Not Renounced" if has_critical_sus_feature else "❌ Not Renounced"; results["Sus_Features"] = "\n".join(sus_scan_output)
        else: results["Upgradeable"] = "❌ Unknown Ownership"; results["Sus_Features"] = "\n".join(sus_scan_output)
    except Exception as e: results["Upgradeable"] = "❌ Unknown Ownership"; results["Sus_Features"] = "\n".join(sus_scan_output) if isinstance(sus_scan_output, list) else str(sus_scan_output)
    try:
        if lp_to_scan and token_total_supply is not None and token_total_supply > 0:
            lp_scan_data = await asyncio.to_thread(lambda: deep_lp_scan_sync(lp_to_scan, token_contract, token_total_supply, w3, BURN_ADDRESSES_CHECKSUM, lp_source))
            if lp_scan_data and isinstance(lp_scan_data.get("LP_burnt"), str): results.update(lp_scan_data)
            else: results["LP_burnt"] = "Error LP Scan"; results["Supply_in_Pool"] = "Error Supply Scan"
        else: results["LP_burnt"] = "N/A"; results["Supply_in_Pool"] = "N/A"
    except Exception: results["LP_burnt"] = "Error LP Scan"; results["Supply_in_Pool"] = "Error Supply Scan"
    return results

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
    
    lp_burnt_escaped = escape_markdown_v2(deep_scan_results.get('LP_burnt', 'N/A'))
    supply_in_pool_escaped = escape_markdown_v2(deep_scan_results.get('Supply_in_Pool', 'N/A'))
    
    price_escaped = escape_markdown_v2(f"{safe_market_data['Price']:.10f}")
    liquidity_escaped = escape_markdown_v2(human_format(safe_market_data['Liquidity'], decimals=2))
    volume_escaped = escape_markdown_v2(human_format(safe_market_data['Volume'], decimals=2))
    price_change_escaped = escape_markdown_v2(f"{safe_market_data['Price_Change']:.2f}")

    buy_tax_escaped = best_tax_data.get('BuyTax', 'N/A')
    sell_tax_escaped = best_tax_data.get('SellTax', 'N/A')

    social_handle_escaped = escape_markdown_v2("@padicalls")
    
    separator_line = "\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\-\-\\"

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
