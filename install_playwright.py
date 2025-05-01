import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        print("✅ Playwright initialized.")

asyncio.run(run())
