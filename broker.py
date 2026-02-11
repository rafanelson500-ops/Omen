import os
import asyncio
import json
from datetime import datetime, timedelta, timezone
import dotenv
import requests
import pandas as pd
import time
from config.config import CONTRACT_ID, CONTRACT_LOTS, SYMBOL, TIMEFRAME

dotenv.load_dotenv()

cid = os.getenv("CID")
secret = os.getenv("SECRET")
user = os.getenv("USERNAME")
device_id = os.getenv("DEVICE_ID")
password = os.getenv("PASSWORD")
base_url = os.getenv("BASE_URL")
account_id = os.getenv("ACCOUNT_ID")
tradovate_socket = None
socket_ready = False
access_token = None
md_token = None

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
    print("Access token: ", response.json()["accessToken"])
    print("MD access token: ", response.json()["mdAccessToken"])
    return response.json()["accessToken"], response.json()["mdAccessToken"]


def get_positions():
    url = f"https://{base_url}/position/list"
    headers = {
        "Authorization": f"Bearer {access_token}",
    }
    response = requests.get(url, headers=headers)
    positions = response.json()
    for p in positions:
        if p['contractId'] == CONTRACT_ID:
            return p['netPos']


def buy():
    if access_token is None or md_token is None:
        refresh_tokens()
    current = get_positions()
    cons_to_buy = CONTRACT_LOTS - current
    if cons_to_buy > 0:
        print(f"Buying {cons_to_buy} contracts")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        body = {
            "accountSpec": "DEMO5997930",
            "action": "Buy",
            "symbol": SYMBOL,
            "orderQty": cons_to_buy,
            "orderType": "Market",
            "isAutomated": True,
        }

        response = requests.post(f"https://{base_url}/order/placeorder", headers=headers, json=body)
        print(response.text)


def sell():
    if access_token is None or md_token is None:
        refresh_tokens()
    current = get_positions()
    cons_to_sell = current + CONTRACT_LOTS
    if cons_to_sell > 0:
        print(f"Selling {cons_to_sell} contracts")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        body = {
            "accountSpec": "DEMO5997930",
            "action": "Sell",
            "symbol": SYMBOL,
            "orderQty": cons_to_sell,
            "orderType": "Market",
            "isAutomated": True,
        }

        response = requests.post(f"https://{base_url}/order/placeorder", headers=headers, json=body)
        print(response.text)