from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    texttovec_base_url: str = "http://localhost:8099"
    texttovec_dimension: int = 128

    es_mock: bool = True
    es_url: str = "http://localhost:9200"
    es_username: str = ""
    es_password: str = ""
    es_verify_certs: bool = True

    log_dir: str = "logs"

    model_config = {"env_file": ".env"}


settings = Settings()
