"""Exact decimal conversion without changing interpreter-wide digit settings.

Callers validate syntax/ranges. Chunking preserves large declared slacks rather
than silently imposing Python's optional string-to-int conversion ceiling.
"""

def parse_decimal(value):
    if type(value) is int:return value
    negative=value.startswith('-');digits=value[1:] if negative else value
    digits=digits.lstrip('0') or '0';result=0
    for start in range(0,len(digits),9):
        chunk=digits[start:start+9];result=result*10**len(chunk)+int(chunk)
    return -result if negative else result


def decimal_text(value):
    if value==0:return '0'
    negative=value<0;value=abs(value);chunks=[]
    while value:
        value,remainder=divmod(value,1_000_000_000);chunks.append(remainder)
    text=str(chunks.pop())+''.join(f'{part:09d}' for part in reversed(chunks))
    return '-'+text if negative else text
