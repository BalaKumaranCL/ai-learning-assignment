# title: Page through messages with a cursor (3.0)
# acme-sdk: 3.0-3.99
# topic: paginate
# tags: paginate pagination page cursor next list all messages
from acme_sdk import Client

client = Client(api_key="sk_live_example")
cursor = None
while True:
    result = client.list_messages(limit=50, cursor=cursor)
    for item in result.items:
        print(item)
    cursor = result.next_cursor
    if cursor is None:
        break
