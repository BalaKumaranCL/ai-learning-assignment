# title: Send a message (3.0)
# acme-sdk: 3.0-3.99
# topic: send
# tags: send message request reply
from acme_sdk import Client

client = Client(api_key="sk_live_example")
response = client.send(message="hello", timeout_ms=5000)
print(response.body)
