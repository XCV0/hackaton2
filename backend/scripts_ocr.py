import sys, json, time; sys.path.insert(0,'.')
from backend.app.settings import list_pdfs
from backend.app.core.pdftext import extract_document
inv=json.load(open('reports/inventory.json'))
todo=[x for x in inv if x['text_pages']<x['pages']]
for x in sorted(todo,key=lambda x:(x['split'],x['pid'])):
    t=time.time(); p=[q for q in list_pdfs(x['domain'],x['split']) if q.stem==x['pid']][0]
    d=extract_document(p,x['domain'],f"{x['split']}_{x['pid']}",do_ocr=True)
    print(x['domain'],x['split'],x['pid'],'ocr pages',sum(1 for q in d['pages'] if q.get('ocr_done')),'conf',[round(q['ocr_conf'] or 0) for q in d['pages'] if q.get('ocr_done')][:5],round(time.time()-t),'s',flush=True)
