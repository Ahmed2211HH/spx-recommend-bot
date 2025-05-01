import asyncio
from playwright.__main__ import main

async def run():
    await main(["install"])

asyncio.run(run())
