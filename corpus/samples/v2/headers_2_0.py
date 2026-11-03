# title: Add a custom request header (2.2 to 2.4)
# acme-sdk: 2.2-2.4
# topic: headers
# tags: header headers custom request options
from acme_sdk import Client, AuthConfig, RequestOptions

client = Client(auth=AuthConfig(token="sk_live_example"))
options = RequestOptions(custom_headers={"X-Trace-Id": "abc123"})
response = client.send(message="hello", options=options)
