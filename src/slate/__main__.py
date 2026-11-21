"""Run the production server: ``python -m slate`` (listens on $HOST:$PORT)."""

import uvicorn

from slate.config import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "slate.app:app",
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
