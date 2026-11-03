# title: Control retries (3.0)
# acme-sdk: 3.0-3.99
# topic: retries
# tags: retry retries attempts backoff failed failure
from acme_sdk import Client

client = Client(api_key="sk_live_example")
response = client.send(message="hello", retry_backoff_ms=2000, max_retries=5)
print(response.status_code)
