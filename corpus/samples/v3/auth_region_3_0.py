# title: Authenticate against the EU region (3.0)
# acme-sdk: 3.0-3.99
# topic: auth
# tags: authenticate authentication auth key token credentials login
from acme_sdk import Client, AuthConfig

auth = AuthConfig(api_key="sk_live_example", region="eu", token_refresh_ms=1800000)
client = Client(auth=auth)
