# title: Send a message (2.2 to 2.4)
# acme-sdk: 2.2-2.4
# topic: send
# tags: send message request reply
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))
response = client.send(message="hello", timeout_ms=5000)
print(response.body)
