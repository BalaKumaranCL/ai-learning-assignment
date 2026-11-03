# title: Handle a timeout (3.0)
# acme-sdk: 3.0-3.99
# topic: errors
# tags: timeout error exception handle failure
from acme_sdk import Client, TimeoutError

client = Client(api_key="sk_live_example")
try:
    client.send(message="hello", timeout_ms=100, max_retries=1)
except TimeoutError:
    print("the request timed out")
