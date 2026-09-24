FROM python:3.12-slim

WORKDIR /code

COPY poetry.lock* pyproject.toml ./

RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-root --without dev,test \
    && rm -rf $(poetry config cache-dir)/{cache,artifacts}

COPY ./app /code/app
# Migrations ship with the image: the service refuses to create tables
# itself, so the schema has to travel with the code that expects it.
COPY ./migrations /code/migrations
COPY ./alembic.ini /code/alembic.ini

EXPOSE 8085

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085"]
