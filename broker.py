import os
import asyncio
import json
from datetime import datetime, timedelta, timezone
import dotenv
import requests
import websockets
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

async def connect_to_socket():
    access_token, md_token = authenticate()
    global tradovate_socket, socket_ready

    if tradovate_socket is None:
        tradovate_socket = await websockets.connect("wss://md.tradovateapi.com/v1/websocket")
    async with tradovate_socket as websocket:
        print("Connected to data socket")
        print("Authorizing...")
        message = f"authorize\n2\n\n{access_token}"
        await websocket.send(message)
        while True:
            resp = await websocket.recv()
            action = resp[0]
            # Data
            if action == "a":
                data = json.loads(resp[1:])[0]
                if data["i"] == 2:
                    if data["s"] == 200:
                        print("Authorized")
                        socket_ready = True
                    else:
                        print("Authorization failed")
                elif data["i"] == 67:
                    print("Chart data received")
                    print(data)

            # Heartbeat
            elif action == "h":
                await websocket.send("[]")

            # Market data
            elif action == "md":
                data = json.loads(resp[1:])[0]
                print(data)

            # Unknown action
            else:
                print(resp)

async def get_data():
    print("Getting data...")
    if tradovate_socket is None or not socket_ready:
        print("Socket not connected or not ready")
        return []
    
    request = {
        "symbol": 4214195,
        "chartDescription": {
            "underlyingType":"MinuteBar",
            "elementSize":5,
            "elementSizeUnit":"UnderlyingUnits",
            "withHistogram": False
        },
        "timeRange": {
            "asMuchAsElements":66
        },
    }

    message = f"md/getChart\n67\n\n{json.dumps(request)}"
    await tradovate_socket.send(message)

def get_user_info():
    access_token, md_token = authenticate()
    url = f"https://{base_url}/account/list"
    headers = {
        "Authorization": f"Bearer {access_token}",
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    response = requests.get(url, headers=headers)
    return response.json()

def init_socket():
    asyncio.run(connect_to_socket())

if __name__ == "__main__":
    print(get_user_info())