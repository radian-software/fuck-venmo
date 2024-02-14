FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y curl python3-pip python3-venv tini && rm -rf /var/lib/apt/lists/*
RUN pip3 install "poetry>=1.7,<1.8"

RUN python3 -m venv /venv
ENV VIRTUAL_ENV=/venv
ENV PATH=/venv/bin:$PATH

COPY pyproject.toml poetry.lock /src/
WORKDIR /src
RUN poetry install --no-root

RUN curl -fsSL https://eddie.website/repository/keys/eddie_maintainer_gpg.key | gpg --dearmor -o /usr/share/keyrings/eddie.gpg
RUN echo "deb [signed-by=/usr/share/keyrings/eddie.gpg] https://eddie.website/repository/apt stable main" > /etc/apt/sources.list.d/eddie.list

RUN apt-get update && apt-get install -y eddie-cli && rm -rf /var/lib/apt/lists/*

COPY fuck_venmo/ /src/fuck_venmo/

ENTRYPOINT ["tini", "--"]
CMD ["python3", "-u", "-m", "fuck_venmo"]
