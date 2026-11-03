# title: Send a message (2.5 and later)
# acme-sdk: 2.5-2.99
# topic: send
# tags: send message request reply
from acme_sdk import Client

client = Client(api_key="sk_live_example")
response = client.send(message="hello", timeout_ms=5000)
print(response.body)
