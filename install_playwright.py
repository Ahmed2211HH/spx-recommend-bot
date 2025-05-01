import asyncio
import subprocess
from playwright.async_api import async_playwright

async def main():
    subprocess.run(["playwright", "install", "chromium"])
    async with async_playwright() as p:
        print("✅ Playwright and Chromium installed!")

if __name__ == "__main__":
    asyncio.run(main())
