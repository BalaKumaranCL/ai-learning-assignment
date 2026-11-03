# title: Add a request header (2.5 and later)
# acme-sdk: 2.5-2.99
# topic: headers
# tags: header headers custom request options
from acme_sdk import Client, RequestOptions

client = Client(api_key="sk_live_example")
options = RequestOptions(headers={"X-Trace-Id": "abc123"})
response = client.send(message="hello", options=options)
