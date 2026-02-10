from broker import get_data, init_socket
import time
import asyncio
import threading

threading.Thread(target=init_socket).start()

async def main():
    await get_data()

time.sleep(2)
asyncio.run(main())
