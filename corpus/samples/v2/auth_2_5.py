# title: Authenticate the client (2.5 and later)
# acme-sdk: 2.5-2.99
# topic: auth
# tags: authenticate authentication auth key token credentials login
from acme_sdk import Client, AuthConfig

auth = AuthConfig(api_key="sk_live_example", region="eu")
client = Client(auth=auth)
