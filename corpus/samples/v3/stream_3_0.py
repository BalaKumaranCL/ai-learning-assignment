# title: Stream a reply (3.0)
# acme-sdk: 3.0-3.99
# topic: stream
# tags: stream streaming chunk reply live
from acme_sdk import Client

client = Client(api_key="sk_live_example")
for chunk in client.stream(message="hello"):
    print(chunk.text, end="")
