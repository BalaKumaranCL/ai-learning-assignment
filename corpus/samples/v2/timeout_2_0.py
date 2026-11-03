# title: Handle a timeout (2.0 and 2.1)
# acme-sdk: 2.0-2.1
# topic: errors
# tags: timeout error exception handle failure
from acme_sdk import Client, AuthConfig, TimeoutError

client = Client(auth=AuthConfig(token="sk_live_example"))
try:
    client.sendMessage("hello", timeout_ms=100)
except TimeoutError:
    print("the request timed out")
