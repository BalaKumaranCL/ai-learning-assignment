# title: Add a request header (3.0)
# acme-sdk: 3.0-3.99
# topic: headers
# tags: header headers custom request options
from acme_sdk import Client, RequestOptions

client = Client(api_key="sk_live_example")
options = RequestOptions(headers={"X-Trace-Id": "abc123"}, body_encoding="json")
response = client.send(message="hello", options=options)
