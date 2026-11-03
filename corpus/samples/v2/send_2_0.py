# title: Send a message (2.0 and 2.1)
# acme-sdk: 2.0-2.1
# topic: send
# tags: send message request reply
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))
reply = client.sendMessage("hello")
print(reply.body)
