# Build the data exchange API client in a staging container. We do
# this here so that we don't have to set up workflows for some Python
# package repository.

FROM python:3.13-slim-trixie AS client-library

RUN DEBIAN_FRONTEND=noninteractive apt-get update                  \
    && DEBIAN_FRONTEND=noninteractive apt-get install --assume-yes \
         git

RUN git clone https://github.com/umg-minai/indicate-data-exchange-api-client

WORKDIR indicate-data-exchange-api-client

RUN python3 -m venv .venv

RUN . .venv/bin/activate && pip install -r requirements.txt && pip install build

RUN . .venv/bin/activate && python3 -m build

RUN cp dist/indicate_data_exchange_api_client-1.0.0-py3-none-any.whl \
       /indicate_data_exchange_api_client-1.0.0-py3-none-any.whl

# Install the data exchange API client and prepare the application.

FROM python:3.13-slim-trixie

RUN DEBIAN_FRONTEND=noninteractive apt-get update                  \
    && DEBIAN_FRONTEND=noninteractive apt-get install --assume-yes \
         curl                                                      \
    && apt-get clean

COPY --from=client-library                                       \
       /indicate_data_exchange_api_client-1.0.0-py3-none-any.whl \
       /tmp
RUN pip install /tmp/indicate_data_exchange_api_client-1.0.0-py3-none-any.whl

COPY requirements.txt /app/
COPY *.py             /app/
COPY static           /app/static
COPY templates        /app/templates

WORKDIR /app

RUN pip install --root-user-action=ignore -r requirements.txt

ENV LISTEN_ADDRESS=0.0.0.0
ENV LISTEN_PORT=8080

EXPOSE ${LISTEN_PORT}

CMD [ "sh", "-c", \
      "exec uvicorn app:app --host ${LISTEN_ADDRESS} --port ${LISTEN_PORT}" ]

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:${LISTEN_PORT}/healthcheck
