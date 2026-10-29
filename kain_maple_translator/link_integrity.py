"""Preserve complete item labels across every translation route."""
from collections import Counter
import re
LINK=re.compile(r'\[[^\[\]\r\n]+\]')


def preserve_link_labels(source,result):
    from .trade_stats import _link_terms
    expected=[_link_terms(m.group()) for m in LINK.finditer(source)]
    if not expected:return result
    actual=list(LINK.finditer(result))
    if [m.group() for m in actual]==expected:return result
    if len(actual)==len(expected):
        for match,label in reversed(list(zip(actual,expected))):result=result[:match.start()]+label+result[match.end():]
        return result
    remaining=Counter(expected)
    for match in actual:
        if remaining[match.group()]:remaining[match.group()]-=1
        else:return source
    missing=[]
    for label in expected:
        if remaining[label]:
            remaining[label]-=1;bare=label[1:-1]
            if bare and bare in result:result=result.replace(bare,label,1)
            else:missing.append(label)
    return (' · '.join(missing)+' · ' if missing else '')+result
