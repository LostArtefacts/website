run:
    uv sync && uv run flask --app trx_website/app.py run

dev:
    uv sync && FLASK_ENV=development uv run flask --app trx_website/app.py run --reload -h 0.0.0.0

deps:
    uv sync

trx-releases:
    uv run trx_website/trx_releases.py

trx-docs:
    uv run trx_website/trx_docs.py

clean:
    rm -f trx_website/cache/releases.json
