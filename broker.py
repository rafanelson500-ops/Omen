import os
import asyncio
import json
from datetime import datetime, timedelta, timezone
import dotenv
import requests
import pandas as pd
import time
from config.config import CONTRACT_ID, CONTRACT_LOTS, SYMBOL, TIMEFRAME, MODE

dotenv.load_dotenv()

cid = os.getenv("CID")
secret = os.getenv("SECRET")
user = os.getenv("USERNAME_PROP") if MODE == "prop" else os.getenv("USERNAME")
device_id = os.getenv("DEVICE_ID")
password = os.getenv("PASSWORD_PROP") if MODE == "prop" else os.getenv("PASSWORD")
base_url = os.getenv("BASE_URL") if MODE == "live" else os.getenv("PAPER_BASE_URL")
spec = os.getenv("LIVE_SPEC") if MODE == "live" else os.getenv("PAPER_SPEC")
account_id = os.getenv("ACCOUNT_ID")
tradovate_socket = None
socket_ready = False
access_token = None
md_token = None
stopped = False

def refresh_tokens():
    global access_token, md_token
    print("Refreshing tokens...")
    access_token, md_token = authenticate()

def authenticate():
    print("Authenticating...")
    url = f"https://{base_url}/auth/accesstokenrequest"

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    credentials = {
        "name": user,
        "password": password,
        "appId": "alpha",
        "appVersion": "0.0.1",
        "cid": cid,
        "deviceId": device_id,
        "sec": secret,
    }

    response = requests.post(url, headers=headers, json=credentials)
    return response.json()["accessToken"], response.json()["mdAccessToken"]

def update_account_stopped():
    global stopped
    try:
        url = f"https://{base_url}/accountRiskStatus/list"

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }

        response = requests.get(url, headers=headers)
        stopped = "userTriggeredLiqOnly" in response.json()[0] and response.json()[0]["userTriggeredLiqOnly"]
    except Exception as e:
        print(f"Error getting account stopped: {e}")
        stopped = True

def get_positions(default):
    retries = 3
    while retries > 0:
        print(f"Getting positions, retries left: {retries}")
        retries -= 1
        try:
            url = f"https://{base_url}/position/list"
            headers = {
                "Authorization": f"Bearer {access_token}",
            }
            response = requests.get(url, headers=headers)
            positions = response.json()
            if len(positions) == 0:
                print("No open positions")
                return 0
            for p in positions:
                if p['contractId'] == CONTRACT_ID:
                    print(f"Found position: {p['netPos']}")
                    return p['netPos']
            print(f"No position found, returning default: {default}")
            return default
        except Exception as e:
            print(f"Error getting positions: {e}, retries left: {retries}")
            time.sleep(1)
    print(f"No position found, returning default: {default}")
    return default

def buy():
    if stopped:
        print("Account is stopped, not buying")
        return
    try:
        if access_token is None or md_token is None:
            refresh_tokens()
        current = get_positions(CONTRACT_LOTS)
        cons_to_buy = CONTRACT_LOTS - current
        if cons_to_buy > 0:
            print(f"Buying {cons_to_buy} contracts")
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            }
            body = {
                "accountSpec": spec,
                "action": "Buy",
                "symbol": SYMBOL,
                "orderQty": cons_to_buy,
                "orderType": "Market",
                "isAutomated": True,
            }

            response = requests.post(f"https://{base_url}/order/placeorder", headers=headers, json=body)
            print(response.text)
    except Exception as e:
        print(f"Error buying: {e}")


def sell():
    if stopped:
        print("Account is stopped, not selling")
        return
    try:
        if access_token is None or md_token is None:
            refresh_tokens()
        current = get_positions(-CONTRACT_LOTS)
        cons_to_sell = current + CONTRACT_LOTS
        if cons_to_sell > 0:
            print(f"Selling {cons_to_sell} contracts")
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            }
            body = {
                "accountSpec": spec,
                "action": "Sell",
                "symbol": SYMBOL,
                "orderQty": cons_to_sell,
                "orderType": "Market",
                "isAutomated": True,
            }

            response = requests.post(f"https://{base_url}/order/placeorder", headers=headers, json=body)
            print(response.text)
    except Exception as e:
        print(f"Error selling: {e}")

def close_all():
    if stopped:
        print("Account is stopped, not closing all")
        return
    try:
        if access_token is None or md_token is None:
            refresh_tokens()
        current = get_positions(0)
        cons_to_buy = -current
        if cons_to_buy > 0:
            print(f"Liquidation: Buying {cons_to_buy} contracts")
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            }
            body = {
                "accountSpec": spec,
                "action": "Buy",
                "symbol": SYMBOL,
                "orderQty": cons_to_buy,
                "orderType": "Market",
                "isAutomated": True,
            }

            response = requests.post(f"https://{base_url}/order/placeorder", headers=headers, json=body)
            print(response.text)

        elif cons_to_buy < 0:
            print(f"Liquidation: Selling {-cons_to_buy} contracts")
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            }
            body = {
                "accountSpec": spec,
                "action": "Sell",
                "symbol": SYMBOL,
                "orderQty": -cons_to_buy,
                "orderType": "Market",
                "isAutomated": True,
            }

            response = requests.post(f"https://{base_url}/order/placeorder", headers=headers, json=body)
            print(response.text)

    except Exception as e:
        print(f"Error closing all: {e}")
