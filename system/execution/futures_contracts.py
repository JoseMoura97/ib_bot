"""Read-only E-mini qualification. No connection setup or order submission."""
from datetime import datetime, timezone
import math
import re


SPECS = {'ES': (50., .25), 'NQ': (20., .25)}
MONTH_CODES = {'03': 'H', '06': 'M', '09': 'U', '12': 'Z'}


def validate_request(root, contract_month, local_symbol):
    if root not in SPECS or not re.fullmatch(r'20[0-9]{2}(03|06|09|12)', contract_month):
        raise ValueError('Explicit quarterly E-mini ES/NQ contract month required')
    match = re.fullmatch(r'(ES|NQ)([HMUZ])([0-9]{1,4})', local_symbol)
    if (not match or match[1] != root or match[2] != MONTH_CODES[contract_month[-2:]]
            or not contract_month[:4].endswith(match[3])):
        raise ValueError('Local symbol disagrees with root/expiry')


def validate_details(details, root, contract_month, local_symbol):
    validate_request(root, contract_month, local_symbol)
    c = details.contract
    multiplier, tick = SPECS[root]
    if (c.secType != 'FUT' or c.symbol != root or c.currency != 'USD'
            or c.exchange != 'CME' or c.localSymbol != local_symbol
            or c.tradingClass != root or c.conId <= 0):
        raise ValueError('IB contract identity mismatch')
    expiry = c.lastTradeDateOrContractMonth
    if not re.fullmatch(r'[0-9]{8}', expiry) or not expiry.startswith(contract_month):
        raise ValueError('IB must return exact dated expiry, not a continuous alias')
    datetime.strptime(expiry, '%Y%m%d')
    if not math.isclose(float(c.multiplier), multiplier, rel_tol=0, abs_tol=1e-10):
        raise ValueError('IB multiplier mismatch')
    if not math.isclose(float(details.minTick), tick, rel_tol=0, abs_tol=1e-10):
        raise ValueError('IB tick mismatch')
    if not details.timeZoneId or not details.tradingHours or not details.liquidHours:
        raise ValueError('IB session metadata missing')
    return {'root': root, 'contract_month': contract_month, 'local_symbol': c.localSymbol,
            'con_id': int(c.conId), 'expiry': expiry, 'multiplier': multiplier, 'tick_size': tick,
            'exchange': c.exchange, 'currency': c.currency, 'timezone': details.timeZoneId,
            'trading_hours': details.tradingHours, 'liquid_hours': details.liquidHours,
            'source': 'IBKR reqContractDetails', 'observed_at': datetime.now(timezone.utc).isoformat(),
            'margin_verified': False, 'live_eligible': False}


def qualify_emini(ib, root, contract_month, local_symbol, *, include_expired=False):
    """Use an already-connected IB session for one read-only metadata request.

    Callers must serialize on their existing IB worker. This function neither
    connects/restarts a gateway nor requests a what-if or real order. Session
    metadata is returned for later calendar validation, not certified here.
    """
    validate_request(root, contract_month, local_symbol)
    if not ib.isConnected():
        raise ConnectionError('IB gateway disconnected: qualification requires an existing read-only session')
    from ib_insync import Future
    request = Future(symbol=root, lastTradeDateOrContractMonth=contract_month,
                     exchange='CME', currency='USD', localSymbol=local_symbol,
                     multiplier=str(int(SPECS[root][0])), includeExpired=include_expired)
    details = ib.reqContractDetails(request)
    if len(details) != 1:
        raise ValueError('IB qualification missing or ambiguous')
    return validate_details(details[0], root, contract_month, local_symbol)
