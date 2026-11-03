# title: Handle a timeout (2.5 and later)
# acme-sdk: 2.5-2.99
# topic: errors
# tags: timeout error exception handle failure
from acme_sdk import Client, TimeoutError

client = Client(api_key="sk_live_example")
try:
    client.send(message="hello", timeout_ms=100)
except TimeoutError:
    print("the request timed out")
