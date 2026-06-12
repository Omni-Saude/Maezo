"""Smoke test fixtures for MAEZO Healthcare Platform."""
import os
import pytest
import httpx
import redis


@pytest.fixture
def camunda_base_url():
    return os.getenv("CAMUNDA_BASE_URL", "http://localhost:8080/engine-rest")


@pytest.fixture
def fhir_base_url():
    return os.getenv("FHIR_BASE_URL", "http://localhost:8081/fhir")



@pytest.fixture
def kafka_bootstrap_servers():
    return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


@pytest.fixture
def redis_url():
    return os.getenv("REDIS_URL", "redis://localhost:6379")


@pytest.fixture
def http_client():
    with httpx.Client(timeout=10.0) as client:
        yield client


@pytest.fixture
def redis_client(redis_url):
    client = redis.from_url(redis_url, decode_responses=True)
    yield client
    client.close()


VALID_TENANTS = ["austa-hospital", "amh-sp-morumbi", "amh-rj-barra", "amh-mg-bh"]
