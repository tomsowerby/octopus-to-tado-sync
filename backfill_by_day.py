import argparse
import asyncio
import requests
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth
from playwright.async_api import async_playwright
from PyTado.interface import Tado


async def browser_login(url, username, password):
    """
    Performs browser-based login to Tado using Playwright.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True
        )  # Set to True if you don't want a browser window
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(url)

        # Click the "Submit" button before login
        await page.wait_for_selector('text="Submit"', timeout=5000)
        await page.click('text="Submit"')

        # Wait for the login form to appear
        await page.wait_for_selector('input[name="loginId"]')

        # Replace with actual selectors for your site
        await page.fill('input[id="loginId"]', username)
        await page.fill('input[name="password"]', password)

        await page.click('button.c-btn--primary:has-text("Sign in")')

        # Optionally take a screenshot
        await page.screenshot(path="screenshot.png")

        await page.wait_for_selector(
            ".text-center.message-screen.b-bubble-screen__spaced", timeout=10000
        )

        # Take a screenshot (optional)
        await page.screenshot(path="after-message.png")
        await browser.close()


def tado_login(username, password):
    """
    Logs into Tado using device activation with browser login if needed.
    """
    tado = Tado(token_file_path="/tmp/tado_refresh_token")

    status = tado.device_activation_status()

    if status == "PENDING":
        url = tado.device_verification_url()

        asyncio.run(browser_login(url, username, password))

        tado.device_activation()

        status = tado.device_activation_status()

    if status == "COMPLETED":
        print("Login successful")
    else:
        print(f"Login status is {status}")

    return tado


def get_meter_reading_total_consumption(
    api_key, mprn, gas_serial_number, period_from=None
):
    """
    Retrieves total gas consumption from the Octopus Energy API for the given gas meter point and serial number.
    """
    if period_from is None:
        period_from = datetime(2025, 3, 3, 0, 0, 0)
    url = f"https://api.octopus.energy/v1/gas-meter-points/{mprn}/meters/{gas_serial_number}/consumption/?group_by=day&order_by=period&period_from={period_from.isoformat()}Z"
    consumption = []

    while url:
        try:
            response = requests.get(url, auth=HTTPBasicAuth(api_key, ""))

            if response.status_code == 200:
                meter_readings = response.json()
                consumption = consumption + meter_readings["results"]
                url = meter_readings.get("next", "")
            else:
                print(
                    f"Failed to retrieve data. Status code: {response.status_code}, Message: {response.text}"
                )
                break
        except Exception as e:
            print(f"Error fetching meter readings: {e}")
            break

    print(f"Consumption data retrieved: {len(consumption)} records")
    return consumption


def get_gas_rates(api_key, short_code, long_code):
    """
    Retrieves all rates from the Octopus Energy API for the given gas product.
    """
    url = f"https://api.octopus.energy/v1/products/{short_code}/gas-tariffs/{long_code}/standard-unit-rates/"
    rates = []

    try:
        response = requests.get(url, auth=HTTPBasicAuth(api_key, ""))

        if response.status_code == 200:
            rates_data = response.json()
            rates = rates_data["results"]
        else:
            print(
                f"Failed to retrieve rates. Status code: {response.status_code}, Message: {response.text}"
            )
    except Exception as e:
        print(f"Error fetching gas rates: {e}")

    return rates


def send_rate_to_tado(tado, valid_from, valid_to, rate):
    """
    Sends a gas rate to Tado using its Energy IQ feature.
    """
    try:
        result = tado.set_eiq_tariff(
            from_date=valid_from,
            to_date=valid_to,
            is_period=True,
            tariff=(rate / 100),
            unit="kWh",
        )
        print(f"Rate sent successfully for {valid_from} to {valid_to}: {result}")
        return True
    except Exception as e:
        print(f"Error sending rate for {valid_from} to {valid_to}: {e}")
        return False


def send_reading_to_tado(tado, date, reading):
    """
    Sends a meter reading to Tado using its Energy IQ feature.
    """
    try:
        result = tado.set_eiq_meter_readings(reading=int(reading), date=date)
        print(f"Reading sent successfully for {date}: {result}")
        return True
    except Exception as e:
        print(f"Error sending reading for {date}: {e}")
        return False


def parse_args():
    """
    Parses command-line arguments for Tado and Octopus API credentials and meter details.
    """
    parser = argparse.ArgumentParser(
        description="Tado and Octopus API Interaction Script"
    )

    # Tado API arguments
    parser.add_argument("--tado-email", required=True, help="Tado account email")
    parser.add_argument("--tado-password", required=True, help="Tado account password")

    # Octopus API arguments
    parser.add_argument(
        "--mprn",
        required=True,
        help="MPRN (Meter Point Reference Number) for the gas meter",
    )
    parser.add_argument(
        "--gas-serial-number", required=True, help="Gas meter serial number"
    )
    parser.add_argument("--octopus-api-key", required=True, help="Octopus API key")

    # Octopus API Gas Rate arguments
    parser.add_argument(
        "--short-code",
        required=True,
        help="Short Product Code for your product, usually the same as the long one with some digits removed from start and end",
    )
    parser.add_argument(
        "--long-code",
        required=True,
        help="Long Product Code shown on your account API data",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Login to Tado using browser method
    print("Logging into Tado...")
    tado = tado_login(username=args.tado_email, password=args.tado_password)

    # Get gas rates from Octopus Energy API
    print("Fetching gas rates from Octopus Energy...")
    rates = get_gas_rates(args.octopus_api_key, args.short_code, args.long_code)

    # Send rates to Tado
    if rates:
        print(f"Sending {len(rates)} rates to Tado...")
        for rate in rates:
            try:
                date_from = datetime.fromisoformat(rate["valid_from"]).strftime(
                    "%Y-%m-%d"
                )
                date_to = datetime.fromisoformat(rate["valid_to"])
                date_to = date_to - timedelta(days=1)
                date_to = date_to.strftime("%Y-%m-%d")
                send_rate_to_tado(tado, date_from, date_to, rate["value_inc_vat"])
            except Exception as e:
                print(f"Error processing rate: {e}")
                continue
    else:
        print("No rates found to send")

    # Get meter readings from Octopus Energy API
    print("Fetching meter readings from Octopus Energy...")
    consumption = get_meter_reading_total_consumption(
        args.octopus_api_key, args.mprn, args.gas_serial_number
    )

    # Send meter readings to Tado
    if consumption:
        print(f"Sending {len(consumption)} meter readings to Tado...")
        sum_consumption = 0
        for interval in consumption:
            try:
                print(
                    f"Processing: {interval['interval_end']} - Consumption: {interval['consumption']}"
                )
                sum_consumption += interval["consumption"]
                send_reading_to_tado(tado, interval["interval_end"], sum_consumption)
            except Exception as e:
                print(
                    f"Error processing meter reading for {interval.get('interval_end', 'unknown')}: {e}"
                )
                continue
    else:
        print("No consumption data found to send")

    print("Backfill process completed!")
