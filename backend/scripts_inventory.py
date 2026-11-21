"""Stage-0 inventory: counts, text layer, hashes, DOI duplicates (no OCR)."""
import json, collections, sys
sys.path.insert(0, '.')
from backend.app.settings import DOMAINS, SPLITS, list_pdfs, REPORTS_DIR
from backend.app.core.pdftext import extract_document, sha256_file, find_doi
rows=[]
for dom in DOMAINS:
    for sp in SPLITS:
        for p in list_pdfs(dom, sp):
            d=extract_document(p, dom, f"{sp}_{p.stem}", do_ocr=False)
            rows.append(dict(domain=dom, split=sp, pid=p.stem, pages=d['page_count'], text_pages=d['text_layer_pages'],
              scan=d['is_scan'], sha=sha256_file(p), doi=find_doi(d), pypdf_error=d['pypdf_error'], bytes=p.stat().st_size))
json.dump(rows, open(REPORTS_DIR/'inventory.json','w'), indent=1)
for dom in DOMAINS:
  for sp in SPLITS:
    r=[x for x in rows if x['domain']==dom and x['split']==sp]
    print(dom, sp, 'pdfs',len(r),'pages',sum(x['pages'] for x in r),'scans',[x['pid'] for x in r if x['scan']],
          'partial', [(x['pid'],x['text_pages'],x['pages']) for x in r if not x['scan'] and x['text_pages']<x['pages']][:20],
          'pypdf_err',[x['pid'] for x in r if x['pypdf_error']])
sh=collections.defaultdict(list); do=collections.defaultdict(list)
for x in rows:
    sh[x['sha']].append(f"{x['domain']}/{x['split']}/{x['pid']}")
    if x['doi']: do[x['doi'].lower()].append(f"{x['domain']}/{x['split']}/{x['pid']}")
print('sha dups', [v for v in sh.values() if len(v)>1]); print('doi dups',[ (k,v) for k,v in do.items() if len(v)>1]); print('no doi', sum(1 for x in rows if not x['doi']))
