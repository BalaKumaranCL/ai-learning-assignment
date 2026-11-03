# title: Handle a timeout (2.2 to 2.4)
# acme-sdk: 2.2-2.4
# topic: errors
# tags: timeout error exception handle failure
from acme_sdk import Client, AuthConfig, TimeoutError

client = Client(auth=AuthConfig(token="sk_live_example"))
try:
    client.send(message="hello", timeout_ms=100)
except TimeoutError:
    print("the request timed out")
