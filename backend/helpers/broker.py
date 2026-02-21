import os
import asyncio
import json
from datetime import datetime, timedelta, timezone
import dotenv
import requests
import pandas as pd
import time
from .config_handler import load_setting, load_config, set_setting
from .logs import log

dotenv.load_dotenv()

cid = os.getenv("CID")
secret = os.getenv("SECRET")
user = os.getenv("USERNAME")
device_id = os.getenv("DEVICE_ID")
password = os.getenv("PASSWORD")
live_url = os.getenv("LIVE_URL")
paper_url = os.getenv("PAPER_URL")
paper_spec = os.getenv("PAPER_SPEC")
live_spec = os.getenv("LIVE_SPEC")
access_token = None

CONTRACT_ID = 4214195
SYMBOL = "MESH6"

def refresh_tokens():
    global access_token
    access_token = authenticate()

def authenticate():
    print("Authenticating...")
    config = load_setting("paper")
    base_url = paper_url if config else live_url
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
    return response.json()["accessToken"]


def get_positions(default=0):
    try:
        if access_token is None:
            refresh_tokens()
        config = load_setting("paper")
        base_url = paper_url if config else live_url
        url = f"https://{base_url}/position/list"
        headers = {
            "Authorization": f"Bearer {access_token}",
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            positions = response.json()
            for p in positions:
                if p['contractId'] == CONTRACT_ID:
                    return p['netPos']
    except Exception as e:
        print(f"Error getting positions: {e}")
    return default


def buy():
    config = load_config()
    contract_lots = config["lots_size"]
    account_id = paper_spec if config["paper"] else live_spec
    base_url = paper_url if config["paper"] else live_url
    
    if access_token is None:
        refresh_tokens()
    current = get_positions()
    cons_to_buy = contract_lots - current
    if cons_to_buy > 0:
        log(f"Enter long")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        body = {
            "accountSpec": account_id,
            "action": "Buy",
            "symbol": SYMBOL,
            "orderQty": cons_to_buy,
            "orderType": "Market",
            "isAutomated": True,
        }

        response = requests.post(f"https://{base_url}/order/placeorder", headers=headers, json=body)
        set_setting("current_position", contract_lots)
        print(response.text)


def sell():
    config = load_config()
    contract_lots = config["lots_size"]
    account_id = paper_spec if config["paper"] else live_spec
    base_url = paper_url if config["paper"] else live_url

    if access_token is None:
        refresh_tokens()
    current = get_positions()
    cons_to_sell = current + contract_lots
    if cons_to_sell > 0:
        log(f"Enter short")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        body = {
            "accountSpec": account_id,
            "action": "Sell",
            "symbol": SYMBOL,
            "orderQty": cons_to_sell,
            "orderType": "Market",
            "isAutomated": True,
        }

        response = requests.post(f"https://{base_url}/order/placeorder", headers=headers, json=body)
        set_setting("current_position", -contract_lots)
        print(response.text)

def close_all():
    try:
        config = load_config()
        account_id = paper_spec if config["paper"] else live_spec
        base_url = paper_url if config["paper"] else live_url
        if access_token is None:
            refresh_tokens()
        current = get_positions(0)
        cons_to_buy = -current
        if cons_to_buy > 0:
            log(f"Exit short")
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            }
            body = {
                "accountSpec": account_id,
                "action": "Buy",
                "symbol": SYMBOL,
                "orderQty": cons_to_buy,
                "orderType": "Market",
                "isAutomated": True,
            }

            response = requests.post(f"https://{base_url}/order/placeorder", headers=headers, json=body)
            set_setting("current_position", 0)
            print(response.text)

        elif cons_to_buy < 0:
            log(f"Exit long")
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            }
            body = {
                "accountSpec": account_id,
                "action": "Sell",
                "symbol": SYMBOL,
                "orderQty": -cons_to_buy,
                "orderType": "Market",
                "isAutomated": True,
            }

            response = requests.post(f"https://{base_url}/order/placeorder", headers=headers, json=body)
            set_setting("current_position", 0)
            print(response.text)

    except Exception as e:
        print(f"Error closing all: {e}")