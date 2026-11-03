# title: Stream a reply by polling (2.0 to 2.3)
# acme-sdk: 2.0-2.3
# topic: stream
# tags: stream streaming chunk reply live
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))
stream = client.pollStream("hello")
while not stream.done:
    print(stream.next().text, end="")
