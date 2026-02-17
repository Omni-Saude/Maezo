"""Health check smoke tests."""
import pytest


def test_cib_seven_health(http_client, camunda_base_url):
    """CIB Seven engine should be reachable."""
    resp = http_client.get(f"{camunda_base_url}/engine")
    assert resp.status_code == 200
    engines = resp.json()
    assert len(engines) > 0, "At least one engine expected"


def test_fhir_server_health(http_client, fhir_base_url):
    """HAPI FHIR server should return capability statement."""
    resp = http_client.get(f"{fhir_base_url}/metadata")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("resourceType") == "CapabilityStatement"


def test_redis_ping(redis_client):
    """Redis should respond to ping."""
    assert redis_client.ping() is True


def test_kafka_broker_list(kafka_bootstrap_servers):
    """Kafka brokers should be reachable."""
    from kafka import KafkaConsumer
    consumer = KafkaConsumer(
        bootstrap_servers=kafka_bootstrap_servers.split(","),
        request_timeout_ms=5000,
    )
    topics = consumer.topics()
    consumer.close()
    assert isinstance(topics, set)
