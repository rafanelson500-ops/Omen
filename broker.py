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
access_token = "eyJraWQiOiIyMSIsImFsZyI6IkVkRFNBIn0.eyJzdWIiOiI1OTk3OTMwIiwiZXhwIjoxNzcwNzQ2MTc2LCJqdGkiOiItNDUzNDI0MTc4NjA1OTM2NDc1My0tMTUwMzczNDUyMDMyMTY2NDczOSIsInBocyI6LTQyMDkzNDk0LCJhY2wiOiJ7XCJlbnRyaWVzXCI6e1wiQ2hhdFwiOlwiRnVsbEFjY2Vzc1wiLFwiKlwiOlwiRGVuaWVkXCIsXCJVc2Vyc1wiOlwiRnVsbEFjY2Vzc1wiLFwiUHJpY2VzXCI6XCJSZWFkXCIsXCJPcmRlcnNcIjpcIkZ1bGxBY2Nlc3NcIixcIkFjY291bnRpbmdcIjpcIkZ1bGxBY2Nlc3NcIixcIlBvc2l0aW9uc1wiOlwiUmVhZFwiLFwiQ29udHJhY3RMaWJyYXJ5XCI6XCJSZWFkXCIsXCJBbGVydHNcIjpcIkZ1bGxBY2Nlc3NcIixcIlJpc2tzXCI6XCJGdWxsQWNjZXNzXCJ9LFwicmVwb3J0c1wiOntcIipcIjpcIkRlbmllZFwifSxcImRlZmF1bHRcIjpcIkRlbmllZFwifSJ9.i8wkp_EsIJOZcuYkW4-m4VK6p1V3oeUDB74i_NlZfus6zxhtS6U10Xig7UtX3Xan4YkjyjlAMm09-0ycIgY8Dw"
md_token = "eyJraWQiOiIyMSIsImFsZyI6IkVkRFNBIn0.eyJzdWIiOiI1OTk3OTMwIiwiZXhwIjoxNzcwNzQ2MTc2LCJqdGkiOiItNjIxODg0ODIwMDUyOTcxNTI3NS0zMzUyMzIwOTE5MzIzOTc4Njk0IiwicGhzIjotNDIwOTM0OTQsImFjbCI6IntcImVudHJpZXNcIjp7XCJVc2Vyc1wiOlwiUmVhZFwifSxcInJlcG9ydHNcIjp7fSxcImRlZmF1bHRcIjpcIkRlbmllZFwifSJ9.WTCAd2FsTjl0zoNHHpd0cYNPFxmpjgHGbN_bzTgu37vaWRhahGHnPq7wGcYrv9KTALYR7bGcSIjNQii_T_XbAQ"

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
    #access_token, md_token = authenticate()
    global tradovate_socket, socket_ready

    if tradovate_socket is None:
        tradovate_socket = await websockets.connect("wss://demo.tradovateapi.com/v1/websocket")
    async with tradovate_socket as websocket:
        print("Connected to data socket")
        print("Authorizing...")
        message = f"authorize\n2\n\n{md_token}"
        await websocket.send(message)
        while True:
            resp = await websocket.recv()
            print(resp)
            action = resp[0]
            # Data
            if action == "a":
                data = json.loads(resp[1:])[0]
                if data["s"] == 200:
                    print("Authorized")
                    socket_ready = True
                else:
                    print("Authorization failed")

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
        "symbol":SYMBOL,
        "chartDescription": {
            "underlyingType":"MinuteBar",
            "elementSize":5,
            "elementSizeUnit":"UnderlyingUnits",
            "withHistogram": False
        },
        "timeRange": {
            "asMuchAsElements":1000
        },
    }

    await tradovate_socket.send("md/getChart\n" + json.dumps(request))

def init_socket():
    asyncio.run(connect_to_socket())