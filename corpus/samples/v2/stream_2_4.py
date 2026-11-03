# title: Stream a reply (2.4)
# acme-sdk: 2.4-2.4
# topic: stream
# tags: stream streaming chunk reply live
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))
for chunk in client.stream(message="hello"):
    print(chunk.text, end="")
