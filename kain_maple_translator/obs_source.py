"""Loopback-only transparent OBS Browser Source for translated chat.

Serves ONLY non-sensitive nickname and translated text to 127.0.0.1.
No outside network, no public listening address and no game integration.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from .chat_style import normalize_style
from .visual_theme import normalize_variant, radius_px
from .megaphone import tinted_rgba
from urllib.parse import urlsplit

OBS_HTML = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>글클메 애드온 - OBS · 제작자 KAIN</title>
<style>
* {box-sizing:border-box;} html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent;color:white;}
#panel {width:100%;height:100%;overflow:hidden;padding:6px 9px;
  background:rgba(17,29,49,.86);border:1px solid rgba(160,192,233,.42);border-radius:9px;
  font-family:"Malgun Gothic",sans-serif;font-size:13pt;line-height:1.25;}
#lines{width:100%;height:100%;display:flex;flex-direction:column;min-height:0;overflow:hidden;}
.obs-lane{display:flex;flex-direction:column;flex:0 0 auto;min-height:24px;overflow:hidden;}
.channel{flex:1;overflow-y:auto;overflow-x:hidden;min-height:0;scrollbar-width:none;padding-bottom:8px;scroll-padding-bottom:8px;}
.channel::-webkit-scrollbar{display:none;}
/* OBS Interaction: drag either grip to resize the two broadcast-only panes. */
.obs-grip{height:8px;flex:0 0 8px;width:100%;background:transparent;cursor:ns-resize;
  touch-action:none;user-select:none;position:relative;margin:0;padding:0;border:0;}
.obs-grip::after{content:"";position:absolute;left:0;right:0;top:3px;height:1px;background:rgba(156,184,207,.48);}
.obs-grip:hover::after,.obs-grip:active::after{height:2px;background:rgba(123,224,220,.9);}
#normal-resize-handle::after{opacity:.45;}

.line{white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;line-height:1.18;margin:0 0 1px 0;max-width:100%;}
.nick{color:#b5d6ff;}.message{color:#fff;}
</style></head><body><div id="panel"><div id="lines"><div id="mega-shell" class="obs-lane"><div id="mega-lines" class="channel"></div></div><div id="split-handle" class="obs-grip" title="OBS 상호작용: 확성기 영역 높이 조절 · 더블클릭 초기화"></div><div id="normal-shell" class="obs-lane"><div id="normal-lines" class="channel"></div><div id="normal-resize-handle" class="obs-grip" title="OBS 상호작용: 일반채팅 영역 높이 조절 · 더블클릭 초기화"></div></div></div></div>
<script>
"use strict"; let rev=-1;
// OBS-only heights: never write the floating app's saved 7:3 split.
// Ratios are relative to the OBS browser-source viewport. Each grip can be
// moved independently, leaving transparent unused space when desired.
const OBS_LAYOUT_KEY='kain_maple_obs_panes_v046';
let obsHeights=null;
try { const saved=JSON.parse(localStorage.getItem(OBS_LAYOUT_KEY)||'null');
 if(saved && Number.isFinite(saved.mega) && Number.isFinite(saved.normal)){
  obsHeights={mega:saved.mega,normal:saved.normal};
 }
} catch (_e) {}
let defaultMega=.30;
function clamp(value,lo,hi){return Math.max(lo,Math.min(hi,value));}
function saveObsHeights(){try{localStorage.setItem(OBS_LAYOUT_KEY,JSON.stringify(obsHeights));}catch(_e){}}
function adjustObsHeights(){
 const box=document.getElementById('lines');
 const height=box.clientHeight;
 if(height<70)return;
 const separating=8,normalGrip=8,usable=height-separating-normalGrip;
 const minRatio=clamp(36/usable,.05,.40);
 const p=obsHeights || {mega:defaultMega,normal:1-defaultMega};
 let mega=clamp(Number(p.mega)||minRatio,minRatio,1-minRatio);
 let normal=clamp(Number(p.normal)||minRatio,minRatio,1-minRatio);
 if(mega+normal>1){ if(resizeActive==='normal')mega=1-normal; else normal=1-mega; }
 document.getElementById('mega-shell').style.height=Math.round(mega*usable)+'px';
 document.getElementById('normal-shell').style.height=Math.round(normal*usable+normalGrip)+'px';
}
let resizeActive='';
function beginResize(ev,kind){
 if(ev.button!==0)return;
 ev.preventDefault();
 resizeActive=kind;
 const grip=ev.currentTarget;
 grip.setPointerCapture(ev.pointerId);
 const usable=Math.max(1,document.getElementById('lines').clientHeight-16);
 const startY=ev.clientY;
 const current=obsHeights || {mega:defaultMega,normal:1-defaultMega};
 const starting={...current};
 function move(e){
  const delta=(e.clientY-startY)/usable;
  let mega=starting.mega,normal=starting.normal;
  if(kind==='mega'){
   mega=clamp(starting.mega+delta,.08,.92);
   if(mega+normal>1)normal=1-mega;
  } else {
   normal=clamp(starting.normal+delta,.08,.92);
   if(mega+normal>1)mega=1-normal;
  }
  obsHeights={mega:clamp(mega,.08,.92),normal:clamp(normal,.08,.92)};
  adjustObsHeights();
 }
 function finish(){grip.removeEventListener('pointermove',move);grip.removeEventListener('pointerup',finish);
  grip.removeEventListener('pointercancel',finish);resizeActive='';saveObsHeights();}
 grip.addEventListener('pointermove',move);
 grip.addEventListener('pointerup',finish);
 grip.addEventListener('pointercancel',finish);
}
for (const [id,kind] of [['split-handle','mega'],['normal-resize-handle','normal']]){
 const grip=document.getElementById(id);
 grip.addEventListener('pointerdown',ev=>beginResize(ev,kind));
 grip.addEventListener('dblclick',()=>{obsHeights=null;
  try{localStorage.removeItem(OBS_LAYOUT_KEY);}catch(_e){} adjustObsHeights();});
}
if(typeof ResizeObserver!=='undefined')new ResizeObserver(adjustObsHeights).observe(document.getElementById('lines'));
window.addEventListener('resize',adjustObsHeights);
async function refresh(){
 try{
  const rsp=await fetch('/state',{cache:'no-store'});if(!rsp.ok)return;
  const state=await rsp.json();if(state.revision===rev)return;rev=state.revision;
  const panel=document.getElementById('panel'), lines=document.getElementById('lines');
  panel.style.fontSize=state.font_size+'pt';panel.style.fontFamily=state.web_font?'KainWebFont,sans-serif':'"'+String(state.font_family).replace(/["\\]/g,'')+'",sans-serif';
  let ff=document.getElementById('remote-font-style');
  if(state.web_font && !ff){
   ff=document.createElement('style');ff.id='remote-font-style';
   ff.textContent='@font-face{font-family:KainWebFont;src:url("/font.ttf?v='+state.font_revision+'") format("truetype");font-display:swap}';
   document.head.append(ff);
  }else if(ff && state.web_font && !ff.textContent.includes('v='+state.font_revision+'"')){
   ff.textContent='@font-face{font-family:KainWebFont;src:url("/font.ttf?v='+state.font_revision+'") format("truetype");font-display:swap}';
  }
  const style=state.chat_style||{};
  const hex=String(style.background_color||'#111d31');
  const rgba=(hex,alpha)=>'rgba('+[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)||0).join(',')+','+alpha+')';
  panel.style.backgroundColor=rgba(hex,state.opacity/100);
  panel.style.color=style.message_color||'#ffffff';
  panel.style.borderRadius=state.theme_variant==='square'?'0px':'12px';
  const normal=document.getElementById('normal-lines'), mega=document.getElementById('mega-lines');
  const ratio=Math.max(15,Math.min(85,Number(state.split_ratio_general||70)));
  defaultMega=(100-ratio)/100;
  // Application-side resizing never overwrites a manually saved OBS layout.
  adjustObsHeights();
  // Reconcile by message identity instead of replaceChildren on every poll.
  // Emptying and rebuilding both panes on each OCR event caused visible
  // flicker in OBS Browser Source, even though the chat text had not changed.
  const existing = new Map();
  for(const pane of [normal,mega]){
    for(const child of pane.children){if(child.dataset.messageId)existing.set(child.dataset.messageId,child);}
  }
  const desired = {normal:[],mega:[]};
  state.messages.forEach((item,index)=>{
   const entry=Array.isArray(item)?{nickname:item[0],translated:item[1],kind:'normal'}:item;
   const special=entry.kind && entry.kind!=='normal';
   const key=String(entry.id ?? ('fallback-'+index+'-'+entry.nickname+'-'+entry.translated));
   let row=existing.get(key);
   if(!row){row=document.createElement('div');row.className='line';row.dataset.messageId=key;
     const nick=document.createElement('span');nick.className='nick';
     const body=document.createElement('span');body.className='message';
     row.append(nick,body);
   }
   const nick=row.children[0],body=row.children[1];
   const nickname=(entry.prefix?entry.prefix+' ':'')+entry.nickname;
   if(nick.textContent!==nickname)nick.textContent=nickname;
   const translated=' : '+entry.translated;
   const itemColor=special && state.source_chat_colors!==false && (style.megaphone_message_color||'#ffffff').toLowerCase()==='#ffffff' && /^#[0-9a-fA-F]{6}$/.test(String(entry.item_color||''))?entry.item_color:'';
   const bodyKey=translated+'|'+itemColor;
   if(body.dataset.renderKey!==bodyKey){
     body.replaceChildren();
     for(const part of translated.split(/(\[[^\[\]\n]+\])/)){
       if(itemColor && /^\[[^\[\]\n]+\]$/.test(part)){
         const link=document.createElement('span');link.textContent=part;link.style.color=itemColor;body.append(link);
       }else body.append(document.createTextNode(part));
     }
     body.dataset.renderKey=bodyKey;
   }
   const selectedNick=special?(style.megaphone_nickname_color||'#fff38a'):(style.nickname_color||'#b5d6ff');
   nick.style.color=(special && state.source_chat_colors!==false && selectedNick.toLowerCase()==='#fff38a' && /^#[0-9a-fA-F]{6}$/.test(String(entry.nickname_color||'')))?entry.nickname_color:selectedNick;
   nick.style.fontWeight=style.nickname_bold?'bold':'normal';
   nick.style.textDecoration=style.nickname_underline?'underline':'none';
   const selectedBody=special?(style.megaphone_message_color||'#ffffff'):(style.message_color||'#ffffff');
   body.style.color=(special && state.source_chat_colors!==false && selectedBody.toLowerCase()==='#ffffff' && /^#[0-9a-fA-F]{6}$/.test(String(entry.text_color||'')))?entry.text_color:selectedBody;
   body.style.fontWeight=style.message_bold?'bold':'normal';
   body.style.textDecoration=style.message_underline?'underline':'none';
   if(special && /^#[0-9a-fA-F]{6}$/.test(String(entry.band_color||''))){
     row.style.backgroundColor=rgba(entry.band_color,state.source_chat_colors!==false?1:(state.megaphone_opacity??92)/100);
     row.style.padding='1px 4px';
     row.style.borderRadius=state.source_chat_colors!==false || state.theme_variant==='square'?'0':'6px';
   }else{row.style.backgroundColor='transparent';row.style.padding='0';row.style.borderRadius='0';}
   desired[special?'mega':'normal'].push(row);
  });
  for(const [pane,wanted] of [[mega,desired.mega],[normal,desired.normal]]){
    const keep=new Set(wanted);
    for(const child of Array.from(pane.children)){if(!keep.has(child))child.remove();}
    wanted.forEach((child,i)=>{if(pane.children[i]!==child)pane.insertBefore(child,pane.children[i]||null);});
  }
  normal.scrollTop=normal.scrollHeight;
  mega.scrollTop=mega.scrollHeight;
 }catch(_e){}
}
refresh(); setInterval(refresh,300);
</script></body></html>'''


class OBSChatSource:
    def __init__(self, host: str='127.0.0.1', port: int=18754):
        if host != '127.0.0.1':
            raise ValueError('OBS source must be bound to 127.0.0.1 only')
        self._lock=threading.RLock()
        self._state={'revision':0,'messages':[], 'font_size':13, 'font_family':'Malgun Gothic', 'opacity':86, 'chat_style':normalize_style({}), 'web_font':False,'font_revision':0,'theme_variant':'rounded','split_ratio_general':70,'megaphone_opacity':92}
        self._font_bytes=b''
        self._server=None
        self._thread=None
        self.port=port

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.port}/'

    def set_font_data(self, data: bytes):
        if len(data)>25_000_000:raise ValueError('font too large')
        with self._lock:
            self._font_bytes=bytes(data)
            self._state['font_revision']+=1
            self._state['revision']+=1

    def set_state(self, messages, font_size=13, font_family='Malgun Gothic', opacity=86, chat_style=None, web_font=False, theme_variant='rounded',split_ratio_general=70,megaphone_opacity=92,source_chat_colors=True):
        cleaned=[]
        for item in list(messages)[-95:]:
            if isinstance(item,dict):
                cleaned.append({'id':item.get('id'), 'nickname':str(item.get('nickname',''))[:80],
                    'translated':str(item.get('translated',''))[:500],
                    'kind':str(item.get('kind','normal'))[:32],
                    'prefix':str(item.get('prefix',''))[:12],
                    'band_color':str(item.get('band_color',''))[:7], 'text_color':str(item.get('text_color',''))[:7],
                    'nickname_color':str(item.get('nickname_color',''))[:7], 'item_color':str(item.get('item_color',''))[:7]})
            else:
                name,body=item[:2]
                cleaned.append((str(name)[:80],str(body)[:500]))
        with self._lock:
            self._state={
                'revision':self._state['revision']+1,
                'messages':cleaned, 'source_chat_colors':bool(source_chat_colors),
                'font_size':max(8,min(38,int(font_size))),
                'font_family':str(font_family)[:128],
                'opacity':max(0,min(100,int(opacity))),
                'chat_style':normalize_style(chat_style),
                'web_font':bool(web_font and self._font_bytes),
                'theme_variant':normalize_variant(theme_variant),
                'split_ratio_general':max(15,min(85,int(split_ratio_general))),
                'megaphone_opacity':max(0,min(100,int(megaphone_opacity))),
                'font_revision':self._state['font_revision'],
            }

    def state(self) -> dict:
        with self._lock:
            return {'revision':self._state['revision'],
                    'messages':list(self._state['messages']),
                    'source_chat_colors':self._state.get('source_chat_colors',True),
                    'font_size':self._state['font_size'],
                    'font_family':self._state['font_family'],
                    'opacity':self._state['opacity'],
                    'chat_style':dict(self._state['chat_style']),
                    'web_font':self._state['web_font'],
                    'theme_variant':self._state['theme_variant'],
                    'split_ratio_general':self._state['split_ratio_general'],
                    'megaphone_opacity':self._state['megaphone_opacity'],
                    'font_revision':self._state['font_revision']}

    def start(self) -> str:
        if self._server:
            return self.url
        parent=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path=urlsplit(self.path).path
                if path == '/':
                    payload=OBS_HTML.encode('utf-8'); typ='text/html; charset=utf-8'
                elif path == '/font.ttf':
                    with parent._lock:
                        payload=parent._font_bytes
                    if not payload:self.send_error(404);return
                    typ='font/ttf'
                elif path == '/state':
                    payload=json.dumps(parent.state(),ensure_ascii=False).encode('utf-8')
                    typ='application/json; charset=utf-8'
                else:
                    self.send_error(404);return
                self.send_response(200)
                self.send_header('Content-Type',typ)
                self.send_header('Cache-Control','no-store, max-age=0')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; font-src 'self'")
                self.send_header('Access-Control-Allow-Origin','http://127.0.0.1:'+str(parent.port))
                self.send_header('Content-Length',str(len(payload)))
                self.end_headers();self.wfile.write(payload)
            def log_message(self, format, *args):
                return
        # A fixed address is preferred. If occupied, fall back to an available
        # localhost port instead of aborting the translation application.
        try:
            server=ThreadingHTTPServer(('127.0.0.1',self.port),Handler)
        except OSError:
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server.daemon_threads=True
        self._server=server
        self.port=server.server_port
        self._thread=threading.Thread(target=server.serve_forever,daemon=True,name='kain-obs-loopback')
        self._thread.start()
        return self.url

    def close(self):
        server=self._server
        self._server=None
        if server is not None:
            server.shutdown()
            server.server_close()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread=None
