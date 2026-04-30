from ib_insync import IB
ib = IB()
try:
    ib.connect('172.17.0.1', 4001, clientId=99, timeout=10)
    print('IB Gateway connected:', ib.isConnected())
    accounts = ib.managedAccounts()
    print('Accounts:', accounts)
    portfolio = ib.portfolio()
    print('Portfolio items:', len(portfolio))
    ib.disconnect()
    print('TEST PASSED')
except Exception as e:
    print('FAILED:', e)
