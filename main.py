# main.py

import os
import logging
from web3 import Web3
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import CommandHandler, ApplicationBuilder

# --- IMPORTS DARI MODUL SENDIRI ---
# HANYA impor w3 dan error_handler dari utils.py
from utils import w3, error_handler 
from handlers_scan import padiscan
from handlers_track import paditrack

# Konfigurasi Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    """Fungsi utama untuk menjalankan bot."""
    
    # 1. Load Environment Variables
    load_dotenv()
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    PULSECHAIN_RPC_URL = os.getenv("PULSECHAIN_RPC_URL")
    HONEY_V2_ADDRESS = os.getenv("HONEY_V2_ADDRESS") 
    HONEY_V1_ADDRESS = os.getenv("HONEY_V1_ADDRESS")

    # 2. Validasi Environment Variables
    if not TELEGRAM_TOKEN:
        print("❌ Error: TELEGRAM_TOKEN must be set in the .env file.")
        return
    
    if not PULSECHAIN_RPC_URL:
        print("❌ Error: PULSECHAIN_RPC_URL must be set in the .env file.")
        return
    
    if not HONEY_V2_ADDRESS or not HONEY_V1_ADDRESS:
        print("⚠️ Warning: HONEY_V2_ADDRESS and HONEY_V1_ADDRESS should be set in .env for accurate Tax checks.")

    # 3. Validasi Koneksi Web3
    # Catatan: w3 diinisialisasi di utils.py, kita cek statusnya di sini
    if w3 is None:
        print("❌ Error: Web3 Initialization Failed. Check PULSECHAIN_RPC_URL.")
        return

    if not w3.is_connected():
        print("❌ Error: Failed to connect to PulseChain RPC.")
        print(f"       -> Attempting connection to: {PULSECHAIN_RPC_URL}")
        return
        
    print("✅ Connected to PulseChain RPC. PadiBot (Scanner & Tracker) is running...")

    try:
        # 4. Inisialisasi Bot
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

        # --- COMMAND HANDLERS ---
        application.add_handler(CommandHandler("padiscan", padiscan))
        application.add_handler(CommandHandler("paditrack", paditrack))
        
        # Tambahkan error handler
        application.add_error_handler(error_handler)

        # 5. Jalankan Bot
        # drop_pending_updates=True agar bot tidak memproses pesan lama saat restart
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        
    except Exception as e:
        print(f"\n\n💥 CRITICAL BOT FAILURE DURING STARTUP OR POLLING: {e.__class__.__name__}")
        print(f"Detail: {e}")

if __name__ == '__main__':
    main()
