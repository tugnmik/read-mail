from graph_api_service import exchange_refresh_token, get_messages
rt = open('_last_token.txt').read().strip()
CLIENT_ID = '881fbb00-671b-4907-b21e-18c7c7aeb585'
print(f'Token: {rt[:40]}...')
result = exchange_refresh_token(rt, CLIENT_ID, 'consumers')
# Handle both tuple and dict return
info = result[1] if isinstance(result, tuple) else result
print(f'info keys: {list(info.keys()) if isinstance(info, dict) else type(info)}')
if isinstance(info, dict) and 'access_token' in info:
    print(f'api_family: {info.get("api_family")}')
    print(f'new refresh_token: {info.get("refresh_token","?")[:50]}...')
    msgs = get_messages(info)  # pass full TokenInfo dict
    if isinstance(msgs, list):
        print(f'✅ Read {len(msgs)} messages:')
        for m in msgs[:3]:
            print(f'  - {(m.get("subject") or "?")[:60]}')
    else:
        print(f'get_messages: {msgs}')
else:
    print(f'Exchange failed: {info}')
