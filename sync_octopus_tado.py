import argparse
import asyncio
import requests
from datetime import datetime
from requests.auth import HTTPBasicAuth
from playwright.async_api import async_playwright
from PyTado.interface import Tado


def get_meter_reading_total_consumption(api_key, mprn, gas_serial_number):
    """
    Retrieves total gas consumption from the Octopus Energy API for the given gas meter point and serial number.
    """
    period_from = datetime(2000, 1, 1, 0, 0, 0)
    url = f"https://api.octopus.energy/v1/gas-meter-points/{mprn}/meters/{gas_serial_number}/consumption/?group_by=quarter&period_from={period_from.isoformat()}Z"
    total_consumption = 0.0

    while url:
        response = requests.get(url, auth=HTTPBasicAuth(api_key, ""))

        if response.status_code == 200:
            meter_readings = response.json()
            total_consumption += sum(
                interval["consumption"] for interval in meter_readings["results"]
            )
            url = meter_readings.get("next", "")
        else:
            print(
                f"Failed to retrieve data. Status code: {response.status_code}, Message: {response.text}"
            )
            break

    print(f"Total consumption is {total_consumption}")
    return total_consumption

def get_gas_rates(api_key, short_code, long_code):
    """
    Retrieves all rates from the Octopus Energy API for the given gas product.
    """
    url = f"https://api.octopus.energy/v1/products/{short_code}/gas-tariffs/{long_code}/standard-unit-rates/"
    rates = []

    response = requests.get(
        url, auth=HTTPBasicAuth(api_key, "")
    )

    if response.status_code == 200:
        rates_data = response.json()
        rates = rates_data["results"]

    else:
        print(
            f"Failed to retrieve data. Status code: {response.status_code}, Message: {response.text}"
        )

    return rates


async def browser_login(url, username, password):

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

def send_rate_to_tado(tado, valid_from, valid_to, rate):
    """
    Sends the total consumption reading to Tado using its Energy IQ feature.
    """
    result = tado.set_eiq_tariff(
        from_date=valid_from,
        to_date=valid_to,
        is_period=True,
        tariff=(rate / 100),
        unit="kWh"
    )
    print(result)


def send_reading_to_tado(username, password, reading, rates):
    """
    Sends the total consumption reading to Tado using its Energy IQ feature.
    """

    tado = tado_login(username=username, password=password)

    result = tado.set_eiq_meter_readings(reading=int(reading))
    print(result)

    for rate in rates:
        date_from = datetime.datetime.fromisoformat(rate["valid_from"]).strftime("%Y-%m-%d")
        date_to = datetime.datetime.fromisoformat(rate["valid_to"])
        date_to = date_to - datetime.timedelta(days=1)
        date_to = date_to.strftime("%Y-%m-%d")
        send_rate_to_tado(tado, date_from, date_to, rate["value_inc_vat"])
        break


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
        "--long-code", required=True, help="Long Product Code shown on your account API data"
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Get total consumption from Octopus Energy API
    consumption = get_meter_reading_total_consumption(
        args.octopus_api_key, args.mprn, args.gas_serial_number
    )

    rates = get_gas_rates(
        args.octopus_api_key, args.short_code, args.long_code
    )

    # Send the total consumption to Tado
    send_reading_to_tado(args.tado_email, args.tado_password, consumption, rates)
