# title: Page through messages by page number (2.5)
# acme-sdk: 2.5-2.5
# topic: paginate
# tags: paginate pagination page cursor next list all messages
from acme_sdk import Client

client = Client(api_key="sk_live_example")
page = 1
while True:
    result = client.list_messages(page=page, per_page=50)
    for item in result.items:
        print(item)
    if page >= result.total_pages:
        break
    page += 1
