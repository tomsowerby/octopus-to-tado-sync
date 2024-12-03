import argparse
import requests
from requests.auth import HTTPBasicAuth
from PyTado.interface import Tado


def get_meter_reading_rates(api_key, short_code, long_code):
    """
    Retrieves all rates from the Octopus Energy API for the given gas product.
    """
    url = f"https://api.octopus.energy/v1/products/{short_code}/gas-tariffs/{long_code}/standard-unit-rates/"
    rate = null

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


def send_rate_to_tado(username, password, valid_from, valid_to, rate):
    """
    Sends the total consumption reading to Tado using its Energy IQ feature.
    """
    tado = Tado(username, password)
    result = tado.set_eiq_tariff(
        from_date=valid_from,
        to_date=valid_to,
        is_period=True,
        tariff=(rate / 100),
        unit="kWh"
    )
    print(result)


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
        "--short-code",
        required=True,
        help="Short Product Code for your product, usually the same as the long one with some digits removed from start and end",
    )
    parser.add_argument(
        "--long-code", required=True, help="Long Product Code shown on your account API data"
    )
    parser.add_argument("--octopus-api-key", required=True, help="Octopus API key")

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    # Get total consumption from Octopus Energy API
    rates = get_meter_reading_rates(
        args.octopus_api_key, args.short_code, args.long_code
    )

    for rate in rates:
        date_from = datetime.datetime.fromisoformat(rate["valid_from"]).strftime("%Y-%m-%d")
        date_to = datetime.datetime.fromisoformat(rate["valid_to"]).strftime("%Y-%m-%d")
        send_rate_to_tado(args.tado_email, args.tado_password, date_from, date_to, rate["value_inc_vat"])
        break

    # Send the total consumption to Tado
    # send_reading_to_tado(args.tado_email, args.tado_password, consumption)
