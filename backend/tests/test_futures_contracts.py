from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from system.execution.futures_contracts import qualify_emini, validate_details, validate_request
from system.execution.ib_executor import IBExecutor


def detail(root='ES'):
    c=SimpleNamespace(secType='FUT',symbol=root,currency='USD',exchange='CME',
        localSymbol=root+'H5',tradingClass=root,conId=123,lastTradeDateOrContractMonth='20250321',
        multiplier='50' if root=='ES' else '20')
    return SimpleNamespace(contract=c,minTick=.25,timeZoneId='US/Central',
        tradingHours='20250317:1700-20250318:1600',liquidHours='20250318:0830-20250318:1500')


@pytest.mark.parametrize('root',['ES','NQ'])
def test_read_only_qualification_uses_existing_adapter(root):
    executor=IBExecutor.__new__(IBExecutor);executor.ib=MagicMock()
    executor.ib.isConnected.return_value=True
    executor.ib.reqContractDetails.return_value=[detail(root)]
    result=executor.qualify_emini_contract(root,'202503',root+'H5',include_expired=True)
    assert result['con_id']==123 and result['expiry']=='20250321'
    assert result['live_eligible'] is False and result['margin_verified'] is False
    request=executor.ib.reqContractDetails.call_args.args[0]
    assert request.secType=='FUT' and request.includeExpired
    executor.ib.placeOrder.assert_not_called();executor.ib.connect.assert_not_called()
    executor.ib.whatIfOrder.assert_not_called()


def test_disconnected_gateway_is_not_started():
    ib=MagicMock();ib.isConnected.return_value=False
    with pytest.raises(ConnectionError):qualify_emini(ib,'ES','202503','ESH5')
    ib.reqContractDetails.assert_not_called();ib.connect.assert_not_called()
    ib.placeOrder.assert_not_called()


@pytest.mark.parametrize('field,value',[('secType','CONTFUT'),('symbol','MES'),('currency','EUR'),
    ('exchange','SMART'),('localSymbol','ESM5'),('tradingClass','MES'),('conId',0),
    ('lastTradeDateOrContractMonth','202503'),('lastTradeDateOrContractMonth','20250620'),('multiplier','5')])
def test_wrong_contract_refused(field,value):
    d=detail();setattr(d.contract,field,value)
    with pytest.raises(ValueError):validate_details(d,'ES','202503','ESH5')


@pytest.mark.parametrize('field,value',[('minTick',.5),('minTick',float('nan')),('timeZoneId',''),('tradingHours',''),('liquidHours','')])
def test_bad_tick_or_missing_sessions_refused(field,value):
    d=detail();setattr(d,field,value)
    with pytest.raises(ValueError):validate_details(d,'ES','202503','ESH5')


@pytest.mark.parametrize('root,month,symbol',[('ES','202503','ESM5'),('ES','202503','ESH6'),
    ('ES','202502','ESH5'),('MES','202503','MESH5'),('ES','202503','ES.v.0')])
def test_request_identity_is_consistent(root,month,symbol):
    with pytest.raises(ValueError):validate_request(root,month,symbol)


@pytest.mark.parametrize('count',[0,2])
def test_no_arbitrary_selection_from_ambiguous_details(count):
    ib=MagicMock();ib.isConnected.return_value=True;ib.reqContractDetails.return_value=[detail()]*count
    with pytest.raises(ValueError,match='ambiguous'):qualify_emini(ib,'ES','202503','ESH5')
    ib.placeOrder.assert_not_called()
