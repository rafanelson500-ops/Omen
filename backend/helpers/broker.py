import os
import asyncio
import json
from datetime import datetime, timedelta, timezone
import dotenv
import requests
import pandas as pd
import time
import requests
from .config_handler import load_setting, load_config, set_setting
from .logs import log

dotenv.load_dotenv()

prop_url = os.getenv("PROP_URL")
live_url = os.getenv("LIVE_URL")
paper_url = os.getenv("PAPER_URL")
access_token = None

SYMBOL = "ES"

def _is_paper_mode(mode):
    """Returns True if mode is paper trading (paper or prop), False for live"""
    return mode in ["paper", "prop"]

def get_webhook_url(mode):
    if mode == "paper":
        return paper_url
    elif mode == "live":
        return live_url
    elif mode == "prop":
        return prop_url
    else:
        return paper_url

def get_positions(default=0):
    return load_setting("current_position") or default

def buy():
    config = load_config()
    contract_lots = config["lots_size"]
    mode = config.get("mode", "paper")
    url = get_webhook_url(mode)

    current = get_positions()
    cons_to_buy = contract_lots - current
    if cons_to_buy > 0:
        log(f"Enter long")
        headers = {
            "Content-Type": "application/json",
        }
        body = {
            "ticker": SYMBOL,
            "action": "buy",
            "quantity": cons_to_buy,
        }

        response = requests.post(url, headers=headers, json=body)
        set_setting("current_position", contract_lots)
        print(response.text)


def sell():
    config = load_config()
    contract_lots = config["lots_size"]
    mode = config.get("mode", "paper")
    url = get_webhook_url(mode)

    current = get_positions()
    cons_to_sell = current + contract_lots
    if cons_to_sell > 0:
        log(f"Enter short")
        headers = {
            "Content-Type": "application/json",
        }
        body = {
            "ticker": SYMBOL,
            "action": "sell",
            "quantity": cons_to_sell,
        }

        response = requests.post(url, headers=headers, json=body)
        set_setting("current_position", -contract_lots)
        print(response.text)

def close_all():
    try:
        config = load_config()
        mode = config.get("mode", "paper")
        url = get_webhook_url(mode)

        current = get_positions(0)
        cons_to_buy = -current
        cons_to_sell = current
        if cons_to_buy > 0:
            log(f"Flatten short")
            headers = {
                "Content-Type": "application/json",
            }
            body = {
                "ticker": SYMBOL,
                "action": "buy",
                "quantity": cons_to_buy,
            }

            response = requests.post(url, headers=headers, json=body)
            set_setting("current_position", 0)
            print(response.text)

        if cons_to_sell > 0:
            log(f"Flatten long")
            headers = {
                "Content-Type": "application/json",
            }
            body = {
                "ticker": SYMBOL,
                "action": "sell",
                "quantity": cons_to_sell,
            }

            response = requests.post(url, headers=headers, json=body)
            set_setting("current_position", 0)
            print(response.text)

    except Exception as e:
        print(f"Error closing all: {e}")