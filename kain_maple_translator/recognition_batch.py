"""Avoid padding short nicknames to long message widths; preserve input order."""
from types import SimpleNamespace


def recognize_width_buckets(engine,images,max_ratio=2.,max_batch=6):
    if not images:return SimpleNamespace(txts=[],scores=[],word_results=[],batches=0)
    indices=sorted(range(len(images)),key=lambda i:images[i].shape[1]/images[i].shape[0]);groups=[]
    for index in indices:
        ratio=images[index].shape[1]/images[index].shape[0]
        if not groups or len(groups[-1])>=max_batch or ratio>groups[-1][0][1]*max_ratio:groups.append([])
        groups[-1].append((index,ratio))
    texts=['']*len(images);scores=[0.]*len(images);words=[None]*len(images)
    for group in groups:
        result=engine.recognize_txt([images[i] for i,_ in group])
        if len(result.txts or [])!=len(group):raise RuntimeError('OCR bucket result count mismatch')
        info=list(getattr(result,'word_results',None) or [])
        for n,((i,_),text,score) in enumerate(zip(group,result.txts,result.scores)):
            texts[i]=text;scores[i]=score;words[i]=info[n] if n<len(info) else None
    return SimpleNamespace(txts=texts,scores=scores,word_results=words,batches=len(groups))
