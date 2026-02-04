import os
import dotenv
from ib_insync import IB

dotenv.load_dotenv()

IB_PORT = int(os.getenv("IB_PORT"))  # <-- convert to int

ib = IB()
ib.connect(host='127.0.0.1', port=IB_PORT, clientId=1)

print("Connected:", ib.isConnected())