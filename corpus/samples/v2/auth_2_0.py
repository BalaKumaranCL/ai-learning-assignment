# title: Authenticate the client (2.0 to 2.4)
# acme-sdk: 2.0-2.4
# topic: auth
# tags: authenticate authentication auth key token credentials login
from acme_sdk import Client, AuthConfig

auth = AuthConfig(token="sk_live_example", region="eu")
client = Client(auth=auth)
