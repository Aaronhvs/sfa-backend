FROM python:3.12-slim

ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /code/src

WORKDIR /code

COPY ./requirements /requirements
RUN python -m pip install --upgrade pip && \
    pip install -r /requirements/local.txt -r /requirements/test.txt

COPY . /code/

COPY ./enviroments/development/start /start
RUN sed -i 's/\r//' /start && chmod +x /start

EXPOSE 8000
