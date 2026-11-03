# title: Page through messages by page number (2.0 to 2.4)
# acme-sdk: 2.0-2.4
# topic: paginate
# tags: paginate pagination page cursor next list all messages
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))
page = 1
while True:
    result = client.list_messages(page=page, per_page=50)
    for item in result.items:
        print(item)
    if page >= result.total_pages:
        break
    page += 1
