import os
import re
from typing import Literal, Optional

from load_dotenv import load_dotenv
from pydantic import BaseModel, Field
import indicate_data_exchange_api_client.hub as hub


DataProvider = Literal['data-exchange-api', 'dummy']


class Configuration(BaseModel):
    debug_mode: bool = Field(
        default=False,
        description="Enable additional debug output.")

    listen_address: str = Field(default="0.0.0.0",
                                description="Address on which the dashboard web-server should listen")
    listen_port: int = Field(default=8080,
                             ge=0,
                             le=65535,
                             description="Port on which the dashboard web-server should listen")

    data_provider: DataProvider = Field(
        default='data-exchange-api',
        description="""The data source to use for the dashboard.
Either 'data-exchange-api' for retrieving data from the INDICATE hub or 'dummy' for displaying randomly generated \
placeholder data.""")

    data_exchange: hub.Configuration = Field(
        ...,
        description="""REST endpoint at which the INDICATE data exchange server should be contacted.""")

    provider_id: Optional[str] = Field(
        default=None,
        pattern=re.compile('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{8}'),
        description="""If provided, unique id of the data provider running the dashboard.
The id is used to identify and highlight the data providers "own" data within the aggregated multi-center data \
obtained from the hub.""")

    provider_name: Optional[str] = Field(
        default=None,
        description="""Name of the data provider for display in the dashboard.
Can be chosen freely and does not impact functional aspects.""")


def load_configuration(config_file: str = ".env") -> Configuration:
    """
    Loads the configuration from a file or environment variables.
    Environment variables take precedence over values in the configuration file.
    """
    load_dotenv(config_file)

    args = {}
    def maybe_from_env(key, variable_name, transform=None):
        value = os.getenv(variable_name)
        if value is None:
            filename = os.getenv(f"{variable_name}_FILE")
            if filename is not None:
                with open(filename) as file:
                    value = file.read().strip()

        if value is not None:
            if transform:
                value = transform(value)
            container = args
            if isinstance(key, tuple):
                for step in key[:-1]:
                    if step not in container:
                        container[step] = {}
                    container = container[step]
                key = key[-1]
            container[key] = value

    maybe_from_env("listen_address", "LISTEN_ADDRESS")
    maybe_from_env("listen_port", "LISTEN_PORT", int)

    maybe_from_env("data_provider", "DATA_PROVIDER")

    maybe_from_env(("data_exchange", "endpoint"), "DATA_EXCHANGE_ENDPOINT")

    maybe_from_env(("data_exchange", "tenant_id"), "DATA_EXCHANGE_TENANT_ID")
    maybe_from_env(("data_exchange", "sp_client_id"), "DATA_EXCHANGE_SP_CLIENT_ID")
    maybe_from_env(("data_exchange", "apim_app_id"), "DATA_EXCHANGE_APIM_APP_ID")

    maybe_from_env(("data_exchange", "sp_client_secret"), "DATA_EXCHANGE_SP_CLIENT_SECRET")

    maybe_from_env(("data_exchange", "cert_thumbprint"), "DATA_EXCHANGE_CERT_THUMBPRINT")
    maybe_from_env(("data_exchange", "cert_key"), "DATA_EXCHANGE_CERT_KEY")

    maybe_from_env("provider_id", "PROVIDER_ID")
    maybe_from_env("provider_name", "PROVIDER_NAME")

    configuration = Configuration(**args)
    if (configuration.data_provider == 'data-exchange-api'
            and configuration.data_exchange.endpoint is None):
        raise RuntimeError(f"When backend '{configuration.data_provider}' is used, DATA_EXCHANGE_ENDPOINT must be \
configured.")
    return configuration
