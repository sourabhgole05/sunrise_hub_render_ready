
var PL=__PL__;
var T_FAV='\\u2605 Favorites',T_REC='\\u23F0 Recent';
var ISMOBILE=/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
var IS_CLOUD=__CLOUD__;
var CHUNK=ISMOBILE?60:120,CONC=ISMOBILE?3:4,MAXAUTO=ISMOBILE?80:240,
 TTL=20*60*1000;
var S={pl:'in',chans:[],cat:'all',q:'',shown:0,queue:[],busy:0,autoN:0,
 now:{},cache:{},loadToken:0,loadAbort:null,checkAbort:{}};
S.favs=JSON.parse(localStorage.getItem('iptv-favs')||'[]');
S.hist=JSON.parse(localStorage.getItem('iptv-hist')||'[]');
// NEW: Universal personalization state (single source-of-truth)
S.universal=(function(){
 try{
  var u=JSON.parse(localStorage.getItem('iptv-universal')||'{}');
  // Normalize missing keys for backward compatibility
  u.favorites=u.favorites||{}; u.history=u.history||[]; u.continueItems=u.continueItems||[];
  u.preferences=u.preferences||{}; u.quickActions=u.quickActions||[];
  return u;
 }catch(e){ return {favorites:{},history:[],continueItems:[],preferences:{},quickActions:[]}};
})();
function $u(k,def){return S.universal[k]!==undefined?S.universal[k]:def;}
function $uS(k,v){try{S.universal[k]=v;localStorage.setItem('iptv-universal',JSON.stringify(S.universal));}catch(e){}}
// Persist changes to localStorage immediately
(function(){
 var u=S.universal; if(u.changed){$uS(); u.changed=false;}
})();
S.chk=(function(){try{
 var c=JSON.parse(localStorage.getItem('iptv-chk')||'{}');
 var cut=Date.now()-TTL*4,o={};
 for(var k in c)if(c[k].t>cut)o[k]=c[k];return o}catch(e){return{}}})();
function $(i){return document.getElementById(i)}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(m){
 return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]})}
function toast(m,c){var t=$('toast');t.textContent=m;t.className=c||'';
 t.classList.add('show');clearTimeout(t._h);
 t._h=setTimeout(function(){t.classList.remove('show')},2600)}
function lsSet(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}
function fresh(u){var c=S.chk[u];return(c&&Date.now()-c.t<TTL)?c:null}
function cur(){return S.pl==='recent'?S.hist:S.pl==='favs'?S.favs:S.chans}
function plain(s){return String(s).replace(/&[#\\w]+;/g,'')}
function isTV(pl){return PL[pl]&&PL[pl].t!=='radio'}
function showModal(id,on){$(id).className=on?'modal open':'modal'}
window.showModal=showModal;

// ============================================================
// UNIVERSAL PERSONALIZATION SYSTEM (reusable across all modules)
// ============================================================
var PS={
 getFavorites:function(cat){
  var f=$u('favorites',{});
  if(!cat)return f;
  return f[cat]||[];
 },
 toggleFavorite:function(cat,item){
  var f=$u('favorites',{});
  if(!f[cat])f[cat]=[];
  var key=item.t||item.n||'';
  var exists=f[cat].findIndex(function(x){return (x.t||x.n||'')===key})>-1;
  if(exists){f[cat]=f[cat].filter(function(x){return (x.t||x.n||'')!==key})}
  else{f[cat].push(item)}
  S.universal.favorites=f;
  $uS();return!exists;
 },
 isFavorite:function(cat,item){
  var f=$u('favorites',{});
  if(!f[cat])return false;
  var key=item.t||item.n||'';
  return f[cat].findIndex(function(x){return (x.t||x.n||'')===key})>-1;
 },
 addHistory:function(item,tp){
  var h=$u('history',[]);
  var key=(item.t||item.n||'').toLowerCase().replace(/[^a-z0-9]/g,'');
  h=h.filter(function(x){return((x.t||x.n||'').toLowerCase().replace(/[^a-z0-9]/g,''))!==key});
  h.unshift({t:item.t||item.n||'',u:item.u||item.url||'',tp:tp||'unknown',ts:Date.now()});
  h=h.slice(0,200);
  S.universal.history=h;
  $uS();
 },
 getHistory:function(){return $u('history',[]);},
 saveContinue:function(item,tp,pos){
  var c=$u('continueItems',[]);
  var key=(item.t||item.n||'').toLowerCase().replace(/[^a-z0-9]/g,'');
  c=c.filter(function(x){return((x.t||x.n||'').toLowerCase().replace(/[^a-z0-9]/g,''))!==key});
  c.push({t:item.t||item.n||'',u:item.u||item.url||'',tp:tp||'unknown',pos:pos||0,ts:Date.now()});
  if(c.length>100)c=c.slice(0,100);
  S.universal.continueItems=c;
  $uS();
 },
 getContinue:function(tp){
  var c=$u('continueItems',[]);
  if(tp)return c.filter(function(x){return x.tp===tp});
  return c;
 },
 addQuickAction:function(a){
  var q=$u('quickActions',[]);
  var key=(a.t||a.label||'').toLowerCase().replace(/[^a-z0-9]/g,'');
  q=q.filter(function(x){return((x.t||x.label||'').toLowerCase().replace(/[^a-z0-9]/g,''))!==key});
  q.unshift({t:a.t||a.label||'',u:a.u||a.url||'',icon:a.icon||'📌',tp:a.tp||'action'});
  q=q.slice(0,30);
  S.universal.quickActions=q;
  $uS();
 },
 getQuickActions:function(){return $u('quickActions',[]);},
 clearAll:function(){
  S.universal={favorites:{},history:[],continueItems:[],preferences:{},quickActions:[]};
  $uS();
 }
};
window.PS=PS;

// ============================================================
// GLOBAL MEDIA PLAYER + QUEUE SERVICE
// ============================================================
var GM={
 player:AU,
 queue:[],
 playing:false,
 current:null,
 volume:parseFloat(localStorage.getItem('iptv-vol')||'0.85'),
 mute:false,
 init:function(){
  this.volume=this.volume||parseFloat(localStorage.getItem('iptv-vol')||'0.85');
  AU.volume=this.volume;
  this.radioTimer=null;
 },
 play:function(item){
  if(this.current&&this.current===item&&!AU.paused){this.pause();return}
  this.current=item;
  if(/\\.m3u8/i.test(item.u)){
   this._playHLS(item);return}
  AU.src=item.u;
  AU.play().catch(function(){toast('Tap PLAY to start',false)});
  this.playing=true;
  this._trackRadio();
 },
 _playHLS:function(item){
  toast('HLS station - opening in VLC', 'bad');
  fetch('/play?url='+encodeURIComponent(item.u)).then(function(r){return r.json()})
   .then(function(j){toast(j.msg,j.ok?'ok':'bad')});
 },
 pause:function(){
  AU.pause();
  this.playing=false;
  this._untrackRadio();
 },
 toggle:function(){
  if(AU.paused){this.play(this.current)}
  else{this.pause()}
 },
 next:function(){
  if(this.queue.length>0){
   var next=this.queue.shift();
   this.play(next);
   this._saveQueue();
  }else{toast('No more in queue', 'bad')}
 },
 prev:function(){
  toast('No previous', 'bad')
 },
 setVolume:function(v){
  this.volume=v;
  AU.volume=v;
  localStorage.setItem('iptv-vol',v);
  this.volume=v;
 },
 toggleMute:function(){
  this.mute=!this.mute;
  AU.muted=this.mute;
  localStorage.setItem('iptv-mute',this.mute);
  this.mute=!this.mute;
 },
 _trackRadio:function(){
  // Keep radio playing while navigating - only stop when user pauses or changes mode explicitly
  if(!this.radioTimer){
   this.radioTimer=setInterval(function(){
    if(AU.paused||!GM.playing)return;
    // Check if current station is still playing
    if(AU.readyState>=2){
     // Keep alive
    }
   },10000)
  }
 },
 _untrackRadio:function(){
  if(this.radioTimer){clearInterval(this.radioTimer);this.radioTimer=null}
 },
 _saveQueue:function(){
  try{localStorage.setItem('gm-queue',JSON.stringify(this.queue))}catch(e){}
 }
};
GM.init();
window.GM=GM;

// Queue UI buttons
$('pbfav').onclick=function(){
 if(GM.current){PS.addQuickAction({t:GM.current.n||GM.current.t||'stream',u:GM.current.u,icon:'★',tp:GM.current?GM.current.t:'radio'})}
 toast('Added to favorites','ok')
};
$('pbnext').onclick=function(){
 GM.next();
};
$('pbqueue').onclick=function(){
 // Show queue modal - display current queue from localStorage
 var q=JSON.parse(localStorage.getItem('gm-queue')||'[]');
 var h='<div style="max-height:400px;overflow:auto"><div class="spa-cards">';
 if(!q.length){h+='<div class="pempty">Queue is empty</div>'}
 else{q.slice(0,20).forEach(function(a,i){h+='<div class="spa-card"><div class="spa-icon">'+(i+1)+'.</div><div class="spa-title">'+(a.t||'')+'</div><div class="spa-sub">'+(a.u?.substring(0,30)||'')+'</div><button class="small" onclick="GM.queue=a;GM.play(a)">Play</button></div>'})}
 h+='</div></div>';
 toast(h,'ok')
};
function hhmm(ep){if(!ep)return'';
 return new Date(ep*1000).toLocaleTimeString([],
 {hour:'2-digit',minute:'2-digit'})}
function norm(s){return(s||'').toLowerCase().replace(/[^a-z0-9]+/g,'')}
function plTypeOf(pl){
 if(pl==='favs')return S.favs[0]&&S.favs[0].tp;
 if(pl==='recent')return S.hist[0]&&S.hist[0].tp;
 return PL[pl]?PL[pl].t:'tv'}

/* ===== MODE SWITCHER (media pipeline untouched) ===== */
var MODE='tv';
function setMode(m){
 MODE=m;document.body.setAttribute('data-mode',m);
 var nb=document.querySelectorAll('#mainnav button');
 for(var i=0;i<nb.length;i++){
  var btn=nb[i];
  btn.className=(btn.dataset.mode===m)?'on':'';
  btn.onclick=function(){navigateTo(this.dataset.mode);};
 }
 var med=(m==='media'||m==='tv'||m==='radio');
 $('chips').style.display=med?'flex':'none';
 document.querySelector('.legend').style.display=med?'block':'none';
 document.querySelector('.note').style.display=med?'flex':'none';
 document.querySelector('.row2').style.display=med?'flex':'none';
 document.querySelector('.tabs').style.display=med?'flex':'none';
 $('guide').style.display=(m==='tv'||m==='media')?'':'none';
 $('grid').style.display=med?'grid':'none';
 if(m==='news'&&!NEWS.loaded)nShow(NEWS.cat);
 if(m==='podcasts'&&!POD.loaded)podShow();
 if(m==='markets'){mkPaint();mkStart()}else mkStop();
 if(m==='books'&&!BK.init)bInit();
 if(m==='tv'&&S.pl!=='in')load('in');
 if(m==='radio'&&S.pl!=='rin')load('rin');
}
window.setMode=setMode;

// ===== SPA ROUTING SYSTEM (hash-based navigation) =====
var ROUTES={
 'home':function(){showHomeDashboard()},
 'favorites':function(){showFavoritesPage()},
 'history':function(){showHistoryPage()},
 'continue':function(){showContinuePage()},
 'search':function(){showGlobalSearch()},
 'tv':function(){setMode('tv');load('in')},
 'radio':function(){setMode('radio');load('rin')},
 'news':function(){setMode('news')},
 'podcasts':function(){setMode('podcasts')},
 'markets':function(){setMode('markets')},
 'books':function(){setMode('books')}
};
function routeChange(hash){
 var route=(hash||window.location.hash.slice(1)||'home').toLowerCase();
 // Close modals
 document.querySelectorAll('.modal.open').forEach(function(m){m.className='modal'});
 // Clear active nav
 var cur=$('mainnav').querySelector('button.on');
 if(cur)cur.className='';
 // Route
 if(ROUTES[route])ROUTES[route]();
 else{setMode('tv');load('in')}
}
window.addEventListener('hashchange',function(){routeChange(window.location.hash.slice(1))});
// Init: if no hash, default to home
if(!window.location.hash){window.location.hash='#home';routeChange('home')}
else{routeChange(window.location.hash.slice(1))}
// Auto-load TV/Radio cards when navigated directly
(function(){var h=window.location.hash.slice(1).toLowerCase();
 if(h==='tv'||h==='radio')setTimeout(function(){load(h==='tv'?'in':'rin')},800)});
window.navigateTo=function(path){window.location.hash='#'+path}

// ===== SPA PAGES =====
function showHomeDashboard(){
 var h='';
 h+='<div class="spa-home"><div class="spa-hero"><div><h2>What can I watch, listen to or read right now?</h2><p>Continue where you left off, discover what&#39;s live, and jump back into favorites.</p></div></div>';
 // Quick actions
 var qa=$u('quickActions',[]);
 h+='<section class="spa-section"><h3>Quick Actions</h3><div class="spa-cards">';
 if(!qa.length){h+='<div class="pempty">No quick actions yet - tap a channel or station to pin it.</div>'}
 else{qa.forEach(function(a){h+='<div class="spa-card" onclick="navigateTo(\''+(a.tp||'tv')+'\')"><div class="spa-icon">'+(a.icon||'📌')+'</div><div class="spa-title">'+esc(a.t)+'</div></div>'})}
 h+='</div></section>';
 // Continue watching
 var c=$u('continueItems',[]);
 h+='<section class="spa-section"><h3>Continue Watching / Listening / Reading</h3><div class="spa-cards">';
 if(!c.length){h+='<div class="pempty">Nothing to continue yet - start something and it will appear here.</div>'}
 else{c.slice(0,6).forEach(function(a){h+='<div class="spa-card" onclick="navigateTo(\''+(a.tp||'tv')+'\')"><div class="spa-icon">'+(a.tp==='radio'?'🎧':a.tp==='books'?'📖':'📺')+'</div><div class="spa-title">'+esc(a.t)+'</div><div class="spa-sub">'+esc(a.tp||'media')+'</div></div>'})}
 h+='</div></section>';
 // Live now
 h+='<section class="spa-section"><h3>Live Now</h3><div class="spa-cards"><div class="spa-card live"><div class="spa-icon">🔴</div><div class="spa-title">Watch live TV</div><div class="spa-sub">Browse what\'s on now</div></div><div class="spa-card live"><div class="spa-icon">🎧</div><div class="spa-title">Listen to live radio</div><div class="spa-sub">500+ stations worldwide</div></div></div></section>';
 // Favorites
 var f=$u('favorites',{});
 var favCount=0;for(var cat in f)favCount+=f[cat].length;
 h+='<section class="spa-section"><h3>Favorites ('+favCount+')</h3><div class="spa-cards">';
 if(!favCount){h+='<div class="pempty">Star your favorite TV, radio, podcasts, books and markets to see them here.</div>'}
 else{var shown=0;for(var cat in f){f[cat].slice(0,3).forEach(function(a){if(shown>=6)return;h+='<div class="spa-card" onclick="navigateTo(\''+(cat||'tv')+'\')"><div class="spa-icon">⭐</div><div class="spa-title">'+esc(a.t||a.n||'')+'</div><div class="spa-sub">'+esc(cat)+'</div></div>';shown++})}}
 h+='</div></section>';
 // Today's useful content
 h+='<section class="spa-section"><h3>Today\'s Useful Content</h3><div class="spa-cards"><div class="spa-card" onclick="navigateTo(\'news\')"><div class="spa-icon">📰</div><div class="spa-title">Latest news headlines</div><div class="spa-sub">60+ stories from top sources</div></div><div class="spa-card" onclick="navigateTo(\'markets\')"><div class="spa-icon">📈</div><div class="spa-title">Market snapshot</div><div class="spa-sub">NIFTY • SENSEX • US markets</div></div><div class="spa-card" onclick="navigateTo(\'books\')"><div class="spa-icon">📚</div><div class="spa-title">Free books</div><div class="spa-sub">70,000+ public domain titles</div></div></div></section>';
 $('grid').innerHTML=h;
 $('grid').style.display='grid';
 document.querySelector('.row2').style.display='none';
 document.querySelector('.legend').style.display='none';
 document.querySelector('.note').style.display='none';
}
function showFavoritesPage(){
 var f=$u('favorites',{});
 var h='<div class="spa-home"><h2>⭐ Favorites</h2><div class="spa-sections">';
 var cats=['tv','radio','news','podcasts','books','markets'];
 cats.forEach(function(cat){
  var items=f[cat]||[];
  if(!items.length)return;
  h+='<section class="spa-section"><h3>'+esc(cat.charAt(0).toUpperCase()+cat.slice(1))+'</h3><div class="spa-cards">';
  items.forEach(function(a){h+='<div class="spa-card"><div class="spa-icon">⭐</div><div class="spa-title">'+esc(a.t||a.n||'')+'</div><div class="spa-sub">'+esc(a.u||a.url||'')+'</div></div>'});
  h+='</div></section>';
 });
 h+='</div></div>';
 $('grid').innerHTML=h;
 $('grid').style.display='grid';
 document.querySelector('.row2').style.display='none';
 document.querySelector('.legend').style.display='none';
 document.querySelector('.note').style.display='none';
}
function showHistoryPage(){
 var h=$u('history',[]);
 var out='<div class="spa-home"><h2>🕘 Recently Used</h2><div class="spa-sections">';
 if(!h.length){out+='<div class="pempty">Your recent activity will appear here.</div>'}
 else{out+='<div class="spa-cards">';h.slice(0,20).forEach(function(a){out+='<div class="spa-card" onclick="navigateTo(\''+(a.tp||'tv')+'\')"><div class="spa-icon">🕘</div><div class="spa-title">'+esc(a.t)+'</div><div class="spa-sub">'+esc(a.tp||'media')+'</div></div>'});out+='</div>'}
 out+='</div></div>';
 $('grid').innerHTML=out;
 $('grid').style.display='grid';
 document.querySelector('.row2').style.display='none';
 document.querySelector('.legend').style.display='none';
 document.querySelector('.note').style.display='none';
}
function showContinuePage(){
 var c=$u('continueItems',[]);
 var out='<div class="spa-home"><h2>▶ Continue Watching / Listening / Reading</h2><div class="spa-sections">';
 if(!c.length){out+='<div class="pempty">Nothing to continue yet.</div>'}
 else{out+='<div class="spa-cards">';c.slice(0,20).forEach(function(a){out+='<div class="spa-card" onclick="navigateTo(\''+(a.tp||'tv')+'\')"><div class="spa-icon">▶</div><div class="spa-title">'+esc(a.t)+'</div><div class="spa-sub">'+esc(a.tp||'media')+'</div></div>'});out+='</div>'}
 out+='</div></div>';
 $('grid').innerHTML=out;
 $('grid').style.display='grid';
 document.querySelector('.row2').style.display='none';
 document.querySelector('.legend').style.display='none';
 document.querySelector('.note').style.display='none';
}
function showGlobalSearch(){
 var q=($('q').value||'').toLowerCase();
 var out='<div class="spa-home"><h2>🔍 Search Everything</h2><div class="spa-sections">';
 if(!q){out+='<div class="pempty">Type in the search bar above to search TV, Radio, News, Podcasts, Books and Markets.</div>'}
 else{
  var cats=['tv','radio','news','podcasts','books','markets'];
  var found=0;
  cats.forEach(function(cat){
   var items=[];
   if(cat==='tv')items=S.chans;
   else if(cat==='radio')items=S.chans;
   else if(cat==='news')items=(NEWS.items||[]);
   else if(cat==='podcasts')items=(POD.items||[]);
   else if(cat==='books')items=(BK.items||[]);
   else if(cat==='markets')items=(MKT.rows||[]);
   var matches=items.filter(function(x){return((x.t||x.n||x.s||x.sym||'').toLowerCase().indexOf(q)>-1)}).slice(0,10);
   if(matches.length){
    found++;
    out+='<section class="spa-section"><h3>'+esc(cat.charAt(0).toUpperCase()+cat.slice(1))+'</h3><div class="spa-cards">';
    matches.forEach(function(a){out+='<div class="spa-card"><div class="spa-icon">🔍</div><div class="spa-title">'+esc(a.t||a.n||a.s||a.sym||'')+'</div></div>'});
    out+='</div></section>';
   }
  });
  if(!found)out+='<div class="pempty">No results found. Try a different search term.</div>';
 }
 out+='</div></div>';
 $('grid').innerHTML=out;
 $('grid').style.display='grid';
 document.querySelector('.row2').style.display='flex';
 document.querySelector('.legend').style.display='none';
 document.querySelector('.note').style.display='none';
}

/* ===== THEME ===== */
(function(){var t=localStorage.getItem('iptv-theme');
 if(t==='dark'){document.documentElement.setAttribute('data-theme','dark');
  $('themebtn').innerHTML='\\u263D'}
 $('themebtn').onclick=function(){
  var d=document.documentElement.getAttribute('data-theme')==='dark';
  if(d){document.documentElement.removeAttribute('data-theme');
   this.innerHTML='\\u263C';localStorage.setItem('iptv-theme','light')}
  else{document.documentElement.setAttribute('data-theme','dark');
   this.innerHTML='\\u263D';localStorage.setItem('iptv-theme','dark')}}})();

/* ===== RADIO ENGINE v3 ===== */
var AU=new Audio();AU.preload='auto';AU.playbackRate=1;
AU.volume=parseFloat(localStorage.getItem('iptv-vol')||'0.85');
var PB={on:false,cur:null,tries:0,timer:null,wd:null,bt:null,
        lastT:-1,stall:0,fired:false,vlcTried:false};
function pbSet(txt,live){
 var st=$('pbstate');if(st)st.textContent=txt;
 var eq=$('pbeq');if(eq)eq.className=live?'eq':'eq off'}
function pbShow(it){
 if(it.l){$('pblogo').src=it.l;$('pblogo').style.display=''}
 else{$('pblogo').style.display='none'}
 $('pbname').textContent=plain(esc(it.n)).slice(0,48);
 var st=$('pbstate');if(st)st.textContent='';
 $('pbar').style.display='flex';
 document.body.classList.add('playing');PB.on=true}
function radioStop(msg){
 AU.pause();try{AU.removeAttribute('src');AU.load()}catch(e){}
 AU.onplaying=AU.onpause=AU.onended=AU.onerror=null;
 clearInterval(PB.wd);clearTimeout(PB.timer);clearInterval(PB.bt);
 document.body.classList.remove('playing');PB.on=false;PB.cur=null;PB.tries=0;
 $('pbplay').innerHTML='\\u25B6';$('pbstate').textContent='Stopped';
 $('pbslp').value='0';
 if(msg)toast(msg,'bad')}
function radioConnect(it){
 PB.cur=it;PB.fired=false;pbShow(it);
 pbSet('Connecting...',true);
 clearTimeout(PB.timer);clearInterval(PB.wd);clearInterval(PB.bt);
 try{AU.pause();AU.removeAttribute('src');AU.load()}catch(e){}
 AU.src=it.u;
 var t0=Date.now();
 PB.bt=setInterval(function(){
  if(!PB.on||PB.cur!==it||AU.readyState>=3)return;
  var b=AU.buffered,end=b.length?b.end(b.length-1):0;
  var ahead=Math.max(0,end-(AU.currentTime||0));
  pbSet('Buffering '+ahead.toFixed(1)+'s ('+
   Math.round((Date.now()-t0)/1000)+'s)...',true)},300);
 var go=function(){
  if(PB.fired||PB.cur!==it)return;
  var b=AU.buffered,end=b.length?b.end(b.length-1):0;
  var ahead=Math.max(0,end-(AU.currentTime||0));
  if(AU.readyState<3&&ahead<1&&(Date.now()-t0)<7000){
   clearTimeout(PB.timer);PB.timer=setTimeout(go,400);return}
  PB.fired=true;clearInterval(PB.bt);
  var pr=AU.play();
  if(pr&&pr.catch)pr.catch(function(){pbSet('Tap PLAY to start',false)})};
 clearTimeout(PB.timer);PB.timer=setTimeout(go,7200);
 AU.onplaying=function(){PB.tries=0;PB.lastT=-1;PB.stall=0;pbSet('\\u266A LIVE - on air',true)};
 AU.onpause=function(){$('pbplay').innerHTML='\\u25B6'};
 // Live streams often fire a synthetic 'ended' event in browsers; ignore it
 // unless the user actually paused us. Only react to real errors.
 AU.onended=function(){if(!PB.on||AU.paused||!PB.cur)return;};
 AU.onerror=function(){if(!PB.on||!PB.cur)return;pbRetry('connection dropped')};
 AU.onstalled=function(){/* ignore - browser stalls on rebuffer are normal */};
 AU.onwaiting=function(){/* ignore - live streams wait when buffer drains */};
 PB.lastT=-1;PB.stall=0;clearInterval(PB.wd);
 PB.wd=setInterval(function(){
  if(!PB.on||PB.cur!==it||AU.paused)return;
  var ct=AU.currentTime||0;
  // For live streams, currentTime can stay pinned; require a long stall
  // and only count it as a stall if the buffer has actually been drained.
  if(Math.abs(ct-PB.lastT)<0.05){
   var b=AU.buffered,end=b.length?b.end(b.length-1):0;
   var ahead=Math.max(0,end-(AU.currentTime||0));
   if(ahead<0.5){PB.stall++;
    if(PB.stall>=8){PB.stall=0;pbRetry('stalled')}}
   else PB.stall=0;
  } else PB.stall=0;
  PB.lastT=ct},4000)}
function pbRetry(reason){
 if(!PB.cur)return;
 PB.tries++;
 // Offer VLC handoff only after several retries, not on first failure
 if(PB.tries>=3&&!PB.vlcTried){PB.vlcTried=true;
  var u=PB.cur.u,nm=plain(esc(PB.cur.n)).slice(0,28);
  toast('Browser struggling - tap VLC button to switch','bad');
  // Don't auto-stop: keep the player visible so the user can still retry
  // or manually invoke VLC. The normal retry cycle continues.
 }
 if(PB.tries>6){radioStop('Station not responding ('+reason+')');return}
 pbSet('Reconnecting '+PB.tries+'/6...',true);
 var it=PB.cur,delay=Math.min(5000,800*PB.tries);
 setTimeout(function(){if(PB.cur===it)radioConnect(it)},delay)}
function radioPlay(it){
 if(/\\.m3u8/i.test(it.u)){
  toast('HLS station - opening in VLC','bad');
  fetch('/play?url='+encodeURIComponent(it.u)).then(function(r){return r.json()})
  .then(function(j){toast(j.msg,j.ok?'ok':'bad')});
  PS.addHistory(it,'radio');
  PS.saveContinue(it,'radio',0);
  pushHist(it,'radio');return}
 PB.vlcTried=false;$('pbplay').innerHTML='\\u23F8';
 toast('\\u266B '+plain(esc(it.n)).slice(0,36));
 radioConnect(it);
 // Track with universal personalization
 PS.addHistory(it,'radio');
 PS.saveContinue(it,'radio',0);
 PS.addQuickAction({t:it.n||'stream',u:it.u,icon:'🎧',tp:'radio'});
 pushHist(it,'radio')}
$('pbplay').onclick=function(){
 if(!PB.cur)return;
 if(AU.paused){var pr=AU.play();if(pr&&pr.catch)pr.catch(function(){});
  this.innerHTML='\\u23F8'}
 else{AU.pause();this.innerHTML='\\u25B6'}};
AU.onplay=function(){$('pbplay').innerHTML='\\u23F8'};
$('pbvol').value=Math.round(AU.volume*100);
$('pbvol').oninput=function(){AU.volume=this.value/100;
 localStorage.setItem('iptv-vol',this.value/100)};
$('pbstop').onclick=function(){radioStop()};
$('pbvlc').onclick=function(){if(!PB.cur)return;
 fetch('/play?url='+encodeURIComponent(PB.cur.u)).then(function(r){return r.json()})
 .then(function(j){toast(j.msg,j.ok?'ok':'bad')})};
$('pbslp').onchange=function(){clearTimeout(PB.timer);
 var m=parseInt(this.value,10);
 if(m){PB.timer=setTimeout(function(){AU.pause();
  pbSet('Sleep timer done',false);toast('Sleep timer done','ok')},m*60000);
  toast('Sleep in '+m+' min')}};

/* ===== EPG ===== */
function nowFor(it){
 var a=S.now[it.id&&it.id.toLowerCase()];
 if(a)return a;
 return S.now[norm(it.n)]||S.now[norm(it.n).split('.').pop()]}
function paintNow(){
 document.querySelectorAll('.card').forEach(function(c){
  var it=findAny(c.dataset.u);if(!it)return;
  var a=nowFor(it),el=c.querySelector('.now');if(!el)return;
  el.textContent=a&&a.n?(a.n.t+' - till '+hhmm(a.n.e)):
   (a&&a.x?('next: '+a.x.t+' @ '+hhmm(a.x.s)):'')})}
function loadNow(){
 if(!isTV(S.pl)||S.pl==='world'){S.now={};paintNow();return}
 fetch('/api/now?p='+S.pl).then(function(r){return r.json()})
 .then(function(j){
  if(j.status==='ready'){S.now=j.channels||{};paintNow()}
  else if(j.status==='loading')setTimeout(loadNow,4000)})
 .catch(function(){})}

/* ===== TABS/GRID (media - unchanged pipeline) ===== */
function buildTabs(){var h='';
 var mk=function(id,l,rad){return '<button data-pl="'+id+'" class="'+
  (rad?'radio ':'')+(S.pl===id?'active':'')+'">'+l+'</button>'};
 h+=mk('favs',T_FAV+' ('+S.favs.length+')');
 h+=mk('recent',T_REC+' ('+S.hist.length+')');
 for(var k in PL)h+=mk(k,PL[k].n,PL[k].t==='radio');
 $('tabs').innerHTML=h}
function filtered(){var base=cur(),q=S.q.toLowerCase(),out=[];
 for(var i=0;i<base.length;i++){var it=base[i];
  var hay=(it.n+' '+it.g+' '+(it.lg||'')).toLowerCase();
  if(q&&hay.indexOf(q)===-1)continue;
  if(S.cat!=='all'&&it.g!==S.cat)continue;
  out.push(it)}
 if($('okfirst').checked){out=out.slice().sort(function(a,b){
  var ca=fresh(a.u),cb=fresh(b.u);
  var va=!ca?1:(ca.ok===true?0:(ca.ok===false?2:1));
  var vb=!cb?1:(cb.ok===true?0:(cb.ok===false?2:1));
  return va-vb})}
 return out}
function buildChips(){var src=cur(),q=S.q.toLowerCase(),
 counts={},order=[],tot=0;
 for(var i=0;i<src.length;i++){var g=src[i].g||'';
  if(q&&(src[i].n+' '+g).toLowerCase().indexOf(q)===-1)continue;
  if(!(g in counts)){counts[g]=0;order.push(g)}counts[g]++}
 order.sort(function(a,b){return counts[b]-counts[a]||a.localeCompare(b)});
 for(var j=0;j<order.length;j++)tot+=counts[order[j]];
 if(S.cat!=='all'&&order.indexOf(S.cat)===-1)S.cat='all';
 var h='<button data-c="all" class="'+(S.cat==='all'?'active':'')+
  '">All <b>'+tot+'</b></button>';
 for(var k2=0;k2<order.length;k2++){var g2=order[k2];
  h+='<button data-c="'+esc(g2)+'" class="'+(S.cat===g2?'active':'')+'">'+
   esc(g2||'Other')+' <b>'+counts[g2]+'</b></button>'}
 $('chips').innerHTML=h;
 $('hint').textContent=src.length
  ? 'Tap a category to filter. Categories come from the channel source; status dots show likely playback: ✓ online, ~ probe blocked, ? VLC-only, ✕ unavailable.'
  : 'Choose a TV or radio source to see its categories.'}
function badges(it){var b='',nm=' '+String(it.n).toUpperCase()+' ';
 var lg=(it.lg||'').split(',')[0].trim();
 if(nm.indexOf(' 4K ')>-1||nm.indexOf(' UHD ')>-1)b+='<span class="bd bhd">4K</span>';
 else if(nm.indexOf(' FHD ')>-1||nm.indexOf(' HD ')>-1)b+='<span class="bd bhd">HD</span>';
 else if(nm.indexOf(' SD ')>-1)b+='<span class="bd bsd">SD</span>';
 if(lg&&lg.length<=14)b+='<span class="bd blang">'+esc(lg)+'</span>';
 return '<div class="bds">'+b+'</div>'}
function render(reset){
 if(reset){$('grid').innerHTML='';S.shown=0}
 var view=filtered(),end=Math.min(view.length,S.shown+CHUNK),h='';
 var rad=plTypeOf(S.pl)==='radio';
 if(end===0&&reset){
  h='<div class="empty">'+(S.pl==='favs'
   ?'No favorites yet - tap the star'
   :S.pl==='recent'
   ?'Nothing here yet!'
   :'No channels match your search')+'</div>'}
 for(var i=S.shown;i<end;i++){var it=view[i];
  var cached=fresh(it.u);
  var isHttp=/^https?:/i.test(it.u);
  var dcls=cached?(cached.ok===true?'online':
   (cached.ok===false?'dead':(isHttp?'unknown':'nonhttp'))):'';
  var dtxt=dcls==='online'?'\\u2713':(dcls==='dead'?'\\u2715':
   (dcls==='unknown'?'~':(!isHttp?'?':'\\u00B7')));
  var isFav=S.favs.some(function(f){return f.u===it.u});
  // Universal favorites check
  var uFav=PS.isFavorite(rad?'radio':'tv',it);
  var cont=PS.getContinue(rad?'radio':'tv').find(function(c){return c.u===it.u});
  var contMark=cont?'<span class="conti" title="Continue watching">▶</span>':'';
  h+='<div class="card" data-u="'+esc(it.u)+'">'+
   '<div class="top"><button class="dot '+dcls+'" data-u="'+esc(it.u)+
    '" title="stream check">'+dtxt+'</button>'+
   '<button class="fav'+(isFav||uFav?' on':'')+'" data-u="'+esc(it.u)+
    '" title="Favorite">\\u2605</button></div>'+
   (it.l?'<img src="'+esc(it.l)+'" loading="lazy" onerror="this.remove()">':'')+
   '<div class="cname">'+esc(it.n)+contMark+'</div>'+
   '<div class="now"></div>'+badges(it)+
   '<div class="grp">'+esc(it.g)+'</div>'+
   '<button class="watch" data-u="'+esc(it.u)+'">'+
   (rad?'\\u266A Listen':'\\u25B6 Watch')+'</button>'+
   (rad?'<button class="altvlc" data-vlc="'+esc(it.u)+
    '">Open in VLC</button>':'')+'</div>'}
 $('grid').insertAdjacentHTML('beforeend',h);
 S.shown=end;
 var extra=(S.pl==='recent'&&S.hist.length)
   ?' <button class="big grey" style="padding:2px 10px;font-size:11px"'
    +' onclick="clearHist()">Clear history</button>':'';
 $('cnt').textContent='Showing '+Math.min(end,view.length)+' of '+view.length;
 $('cnt').insertAdjacentHTML('beforeend',extra);
 observeDots();paintNow()}

/* ===== HEALTH DOTS ===== */
var dotIO=new IntersectionObserver(function(es){es.forEach(function(e){
 if(e.isIntersecting)schedule(e.target.dataset.u)})},{rootMargin:'200px'});
function observeDots(){if(!$('auto').checked)return;
 document.querySelectorAll('.dot').forEach(function(d){
  if(!d.classList.contains('online')&&!d.classList.contains('dead'))
   dotIO.observe(d)})}
function schedule(u){if(S.autoN>=MAXAUTO)return;
 if(fresh(u))return;if(S.queue.indexOf(u)!==-1)return;
 S.queue.push(u);pump()}
function pump(){while(S.busy<CONC&&S.queue.length){var u=S.queue.shift();
 S.busy++;S.autoN++;test(u,false).then(function(){S.busy--;pump()})}}
function findDot(u){var ds=document.querySelectorAll('.dot');
 for(var i=0;i<ds.length;i++)if(ds[i].dataset.u===u)return ds[i];return null}
function setDot(u,state,txt,title){
 document.querySelectorAll('.dot').forEach(function(d){
  if(d.dataset.u!==u)return;
  d.className='dot '+state;d.textContent=txt;
  if(title)d.title=title;
  try{dotIO.unobserve(d)}catch(e){}})}
function test(u,manual){
 if(!/^https?:/i.test(u)){var e0=findDot(u);
  if(e0)setDot(u,'nonhttp','?','Direct/VLC stream');
  return Promise.resolve()}
 var el=findDot(u);
 if(manual&&el){el.className='dot checking';el.textContent='\\u25CB'}
 var c=fresh(u);if(c&&!manual)return Promise.resolve();
 var controller=new AbortController();
 S.checkAbort[u]=controller;
 return fetch('/check?url='+encodeURIComponent(u),{signal:controller.signal})
  .then(function(r){return r.json()})
  .then(function(j){S.chk[u]={ok:j.ok,code:j.code,ms:j.ms,t:Date.now()};
   lsSet('iptv-chk',S.chk);
   setDot(u,j.ok===true?'online':(j.ok===false?'dead':'unknown'),
    j.ok===true?'\\u2713':(j.ok===false?'\\u2715':'~'),
    'HTTP '+j.code+(j.ms?', '+j.ms+' ms':''))})
  .catch(function(err){if(err&&err.name!=='AbortError')setDot(u,'unknown','~','Check failed')})
  .then(function(){delete S.checkAbort[u]})}

/* ===== ACTIONS ===== */
function pushHist(it,tp){if(!it||!it.u)return;
 // Universal personalization tracking
 var cat = (S.pl==='favs'||S.pl==='recent')?tp:(plTypeOf(S.pl)==='radio'?'radio':'tv');
 PS.addHistory(it,cat);
 PS.saveContinue(it,cat,0);
 S.hist=S.hist.filter(function(x){return x.u!==it.u});
 S.hist.unshift({n:it.n,u:it.u,l:it.l,g:it.g,tp:tp||it.tp||'tv'});
 S.hist=S.hist.slice(0,60);lsSet('iptv-hist',S.hist);buildTabs();
 if(S.pl==='recent'){buildChips();render(true)}}
function findAny(u){var pools=[cur(),S.favs,S.hist,S.chans];
 for(var p=0;p<pools.length;p++)
  for(var i=0;i<pools[p].length;i++)
   if(pools[p][i].u===u)return pools[p][i];
 return null}
var PLAYER={url:'',item:null};
function closePlayer(){
 var v=$('tvplayer');v.pause();v.removeAttribute('src');v.load();
 showModal('playermodal',false);PLAYER.url='';PLAYER.item=null}
window.closePlayer=closePlayer;
function vlcLink(u){
 var p=urlparseForPlayer(u);
 if(/Android/i.test(navigator.userAgent))
  return 'intent://'+p.hostpath+'#Intent;scheme='+p.scheme+
   ';package=org.videolan.vlc;end';
 if(/iPhone|iPad|iPod/i.test(navigator.userAgent))
  return 'vlc-x-callback://x-callback-url/stream?url='+encodeURIComponent(u);
 return '';
}
function urlparseForPlayer(u){
 var p=u.indexOf('://'),m=p>0?[u.slice(0,p),u.slice(p+3)]:null;
 return {scheme:m?m[0]:'http',hostpath:m?m[1]:u};
}
function playerPlay(){
 var v=$('tvplayer');
 if(!PLAYER.url)return;
 if(v.src!==PLAYER.url)v.src=PLAYER.url;
 v.preload='auto';v.play().catch(function(){
  $('playerhint').textContent='Tap the play button if autoplay is blocked by your browser.'
 });
 $('playerhint').textContent='Playing in the phone browser. Source quality is automatic.';
}
function openVlcMobile(){
 if(!PLAYER.url)return;
 var link=vlcLink(PLAYER.url);
 if(link){window.location.href=link;
  $('playerhint').textContent='If VLC is installed, your phone will open it. Otherwise use Play here.';
  return}
 if(!IS_CLOUD){
  fetch('/play?url='+encodeURIComponent(PLAYER.url)).then(function(r){return r.json()})
   .then(function(j){toast(j.msg,j.ok?'ok':'bad')})
   .catch(function(){toast('Could not reach the local player','bad')});
  return;
 }
 $('playerhint').textContent='Your phone cannot launch VLC from this browser. Use Play here.';
}
function openPlayer(it,u){
 PLAYER.url=u;PLAYER.item=it;
 $('playertitle').textContent='Watch '+plain(it.n||'stream').slice(0,60);
 $('playerhint').textContent=/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
  ?'VLC can be opened when installed; otherwise play in this browser.'
  :'Choose a playback option.';
 $('playervlc').style.display=(vlcLink(u)||!IS_CLOUD)?'':'none';
 $('playerplay').style.display=/^https?:/i.test(u)?'':'none';
 $('playerexternal').style.display=/^https?:/i.test(u)?'':'none';
 showModal('playermodal',true);
 if(/^https?:/i.test(u))playerPlay();
}
$('tvplayer').addEventListener('waiting',function(){
 $('playerhint').textContent='Buffering... keeping the stream ready.';
});
$('tvplayer').addEventListener('canplay',function(){
 $('playerhint').textContent='Playing. Source quality is automatic.';
});
$('tvplayer').addEventListener('error',function(){
 $('playerhint').textContent='Stream paused. Try Play here again or open VLC.';
});
$('playerfit').onchange=function(){$('tvplayer').style.objectFit=this.value};
$('playerspeed').onchange=function(){$('tvplayer').playbackRate=parseFloat(this.value)};
$('playerplay').onclick=playerPlay;
$('playervlc').onclick=openVlcMobile;
$('playerexternal').onclick=function(){
 if(PLAYER.url)window.open(PLAYER.url,'_blank','noopener')};
function route(it,u){
 var tp=it.tp||plTypeOf(S.pl)||'tv';
 if(tp==='radio'){radioPlay(it);return}
 if(/^https?:/i.test(u)){pushHist(it,'tv');openPlayer(it,u);return}
 if(IS_CLOUD){toast('This stream requires VLC or a compatible player','bad');return}
 toast('Opening '+plain(esc(it.n)).slice(0,40)+'...');
 fetch('/play?url='+encodeURIComponent(u)).then(function(r){return r.json()})
  .then(function(j){toast(j.msg,j.ok?'ok':'bad')})
  .catch(function(){toast('Server not running','bad')})}
function toggleFav(u){var i=-1;
 for(var k=0;k<S.favs.length;k++)if(S.favs[k].u===u){i=k;break}
 if(i>=0){S.favs.splice(i,1);toast('Removed from favorites')}
 else{var src=cur();
  for(var k2=0;k2<src.length;k2++)if(src[k2].u===u){
   var o=src[k2];o.tp=o.tp||plTypeOf(S.pl);
   S.favs.unshift({n:o.n,u:o.u,l:o.l,g:o.g,tp:o.tp});
   toast('\\u2605 Added to favorites');break}}
 lsSet('iptv-favs',S.favs);
 document.querySelectorAll('.fav').forEach(function(b){
  b.classList.toggle('on',S.favs.some(function(f){return f.u===b.dataset.u}))});
 if(S.pl==='favs'){buildChips();render(true)}
 buildTabs()}
window.clearHist=function(){S.hist=[];lsSet('iptv-hist',S.hist);
 buildTabs();buildChips();render(true);toast('History cleared')};
window.clearCache=function(){
 var btn=$('cacheclear'),top=$('cachetop');
 if(btn)btn.disabled=true;if(top)top.disabled=true;
 try { localStorage.removeItem('iptv-chk'); }
 catch(e){}
 S.chk={};S.cache={};S.queue=[];S.autoN=0;
 Object.keys(S.checkAbort).forEach(function(u){
  try{S.checkAbort[u].abort()}catch(e){}
 });
 if(S.loadAbort){try{S.loadAbort.abort()}catch(e){}}
 fetch('/api/cache?scope=data')
  .then(function(r){if(!r.ok)throw new Error('cache clear failed');return r.json()})
  .then(function(){
   buildTabs();buildChips();render(true);
   toast('Cached data cleared. Reload a source when you need fresh data.','ok');
  })
  .catch(function(){toast('Could not clear server caches. Try again.','bad')})
  .then(function(){if(btn)btn.disabled=false;if(top)top.disabled=false});
 if(PB&&PB.cur)radioStop();
};
window.wbDone=function(){lsSet('iptv-welcomed',1);showModal('welcome',false)};
window.addCustom=function(){
 var u=$('seturl').value.trim(),n=$('setname').value.trim()||'My IPTV';
 if(u.indexOf('://')<0){toast('Enter a valid http(s) URL','bad');return}
 fetch('/add?url='+encodeURIComponent(u)+'&name='+encodeURIComponent(n))
 .then(function(r){return r.json()})
 .then(function(j){toast(j.msg,j.ok?'ok':'bad');
  if(j.ok)setTimeout(function(){location.reload()},900)})};

/* ===== GUIDE ===== */
function openGuide(){
 if(!isTV(S.pl)||S.pl==='world'){
  $('glist').innerHTML='<p style="color:var(--mut)">Open a TV tab (not Worldwide).</p>';
  showModal('guidepanel',true);return}
 showModal('guidepanel',true);
 $('gstat').textContent='Loading guide (first time ~10-40s)...';
 $('glist').innerHTML='';
 fetch('/api/now?p='+S.pl).then(function(r){return r.json()})
 .then(function(x){
  if(x.status==='loading'){$('gstat').textContent='Still loading...';
   setTimeout(openGuideRefresh,5000);return}
  if(x.status!=='ready'){$('gstat').innerHTML='Guide unavailable: '+
   esc(x.status)+' <button class="mini" onclick="openGuide()">Retry</button>';return}
  S.now=x.channels||{};$('gstat').textContent='';paintNow();drawGuide()})
 .catch(function(){$('gstat').textContent='Could not reach server.'})}
function openGuideRefresh(){
 if($('guidepanel').className.indexOf('open')<0)return;
 fetch('/api/now?p='+S.pl).then(function(r){return r.json()})
 .then(function(x){
  if(x.status==='ready'){S.now=x.channels||{};
   $('gstat').textContent='';paintNow();drawGuide()}
  else if(x.status==='loading')setTimeout(openGuideRefresh,5000)
  else $('gstat').innerHTML='Guide unavailable: '+esc(x.status)+
   ' <button class="mini" onclick="openGuide()">Retry</button>'})}
function drawGuide(){
 var q=norm($('gsearch').value),rows=[],src=cur();
 for(var i=0;i<src.length;i++){
  var a=nowFor(src[i]);
  if(a&&(a.n||a.x)){
   if(q&&norm(src[i].n).indexOf(q)===-1)continue;
   rows.push({n:src[i].n,u:src[i].u,a:a});if(rows.length>=200)break}}
 var h='';
 for(var r2=0;r2<rows.length;r2++){var rr=rows[r2];
  h+='<div class="grow" data-u="'+esc(rr.u)+'"><b title="'+esc(rr.n)+'">'+
   esc(rr.n)+'</b>'+
   '<span class="np">'+(rr.a.n?('\\u25B6 '+esc(rr.a.n.t)+
    ' <span class=tm>till '+hhmm(rr.a.n.e)+'</span>'):'')+'</span>'+
   '<span class="nx">'+(rr.a.x?('next: '+esc(rr.a.x.t)+
    ' <span class=tm>@ '+hhmm(rr.a.x.s)+'</span>'):'')+'</span></div>'}
 $('glist').innerHTML=h||'<p style="color:var(--mut)">No guide data matched.</p>'}
$('gsearch').addEventListener('input',function(){
 if($('guidepanel').className.indexOf('open')>-1)drawGuide()});
$('glist').onclick=function(e){var r=e.target.closest('.grow');
 if(!r||!r.dataset.u)return;var it=findAny(r.dataset.u);
 if(it)route(it,r.dataset.u)};

/* ================= NEWS PANEL ================= */
var NEWS={cat:'top',items:[],loaded:false};
var NCATS=[['top','Top'],['india','India'],['business','Business'],
 ['markets','Markets'],['tech','Tech'],['sports','Sports'],
 ['world','World'],
 ['hindi','&#2361;&#2367;&#2344;&#2381;&#2342;&#2368;']];
function nChips(){var h='';
 NCATS.forEach(function(c){
  h+='<button data-c="'+c[0]+'" class="'+(NEWS.cat===c[0]?'active':'')+
   '">'+c[1]+'</button>'});
 $('nchips').innerHTML=h}
function nShow(cat){NEWS.cat=cat;nChips();
 $('nlist').innerHTML='<div class="pempty">Loading&#8230;</div>';
 fetch('/api/news?cat='+cat).then(function(r){return r.json()})
 .then(function(j){NEWS.items=j.items||[];NEWS.loaded=true;nPaint()})
 .catch(function(){$('nlist').innerHTML=
  '<div class="pempty">Could not load news.<br><button class="big" '+
  'onclick="nShow(NEWS.cat)">Retry</button></div>'})}
window.nShow=nShow;
function agoT(ep){if(!ep)return'';
 var m=Math.floor((Date.now()-ep*1000)/60000);
 if(m<1)return'now';if(m<60)return m+'m';
 var h=(m/60)|0;if(h<24)return h+'h';return((h/24)|0)+'d'}
function nPaint(){
 var q=$('nq').value.trim().toLowerCase(),idxs=[];
 for(var i=0;i<NEWS.items.length;i++){var it=NEWS.items[i];
  if(q&&(it.t+' '+it.s+' '+(it.b||'')).toLowerCase().indexOf(q)===-1)continue;
  idxs.push(i)}
 if(!idxs.length){$('nlist').innerHTML=
  '<div class="pempty">Nothing matched.</div>';return}
 var h='';
 for(var k=0;k<idxs.length;k++){var i2=idxs[k],a=NEWS.items[i2];
  var thumb=a.d?'<img src="'+esc(a.d)+'" loading="lazy" '+
   'onerror="this.remove()">':'';
  // Add favorite icon
  var favIcon=PS.isFavorite('news',a)?'⭐':'☆';
  // Add continue indicator
  var contIcon='';
  var cont=PS.getContinue('news').find(function(c){return c.t===a.t});
  if(cont)contIcon='<span class="conti" title="Continue reading">▶</span>';
  h+='<article class="ni'+(k===0&&!q?' hero':'')+'" data-i="'+i2+'">'+
   '<div class="nifav" onclick="PS.toggleFavorite(\'news\',a);nPaint();event.stopPropagation()">'+favIcon+'</div>'+
   thumb+'<div class="nitxt"><h3>'+esc(a.t)+'</h3>'+
   (k===0&&!q&&a.b?'<p>'+esc(a.b)+'</p>':'')+
   '<span class="nimeta">'+esc(a.s)+(a.pub?' &middot; '+agoT(a.pub):'')+
   ' '+contIcon+'</span></div></article>'}
 $('nlist').innerHTML=h}
$('nchips').onclick=function(e){var b=e.target.closest('button');
 if(b)nShow(b.dataset.c)};
$('nq').addEventListener('input',function(){clearTimeout(window._nqt);
 window._nqt=setTimeout(nPaint,180)});
$('nlist').onclick=function(e){var a=e.target.closest('.ni');if(!a)return;
 nOpen(parseInt(a.dataset.i,10))};
function nOpen(i){var a=NEWS.items[i];if(!a)return;
 // Track with universal personalization
 PS.addHistory(a,'news');
 PS.saveContinue(a,'news',0);
 $('rvtitle').textContent=a.t;
 $('rvmeta').textContent=a.s+(a.pub?(' - '+new Date(a.pub*1000)
  .toLocaleString()):'');
 $('rvbody').textContent=a.b||'Full story at source.';
 $('rvlink').href=/^https?:/.test(a.l)?a.l:'#';
 showModal('readerview',true)}
window.nOpen=nOpen;
(function(){var fs=parseInt(localStorage.getItem('srt-nfs')||'15',10);
 function ap(){$('rvbody').style.fontSize=fs+'px'}ap();
 $('rvfm').onclick=function(){fs=Math.max(12,fs-1);ap();
  localStorage.setItem('srt-nfs',fs)};
 $('rvfp').onclick=function(){fs=Math.min(24,fs+1);ap();
  localStorage.setItem('srt-nfs',fs)}})();

var POD={loaded:false,loading:false,request:null};
var POD_SRC = '';
function podPopulateSrc(){var h='<option value=\"\">All</option>';PODCAST_FEEDS.forEach(function(a){var sel=(a[0]===POD_SRC)?' selected=\"selected\"':'';h+='<option value=\"'+a[0]+'\"'+sel+'>'+esc(a[0])+'</option>'});
 // Add directory categories as filter options
 for(var cat in PODCAST_DIRECTORY_FEEDS){var name=cat.replace(/_/g,' ');name=name.charAt(0).toUpperCase()+name.slice(1);
  h+='<option value=\"dir:'+cat+'\"'+((POD_SRC==='dir:'+cat)?' selected=\"selected\"':'')+'>'+esc(name)+' feeds</option>';}
 $('podsrc').innerHTML=h;}
$('podsrc').onchange=function(){POD_SRC=this.value;podPaint();};
function podPopulateChips(){
 var h='<button data-fc="all" class="active">All</button>';
 h+='<button data-fc="hindi">Hindi</button>';
 h+='<button data-fc="en">English</button>';
 h+='<button data-fc="news">News</button>';
 h+='<button data-fc="stories">Stories</button>';
 h+='<button data-fc="entertainment">Entertainment</button>';
 $('podchips').innerHTML=h;}
$('podchips').onclick=function(e){
 var b=e.target.closest('button');if(!b)return;
 var fc=b.dataset.fc;
 $('podchips').querySelectorAll('button').forEach(function(x){x.classList.remove('active')});
 b.classList.add('active');
 if(fc==='all'){POD_SRC='';podPopulateSrc();}
 else if(['hindi','en'].indexOf(fc)>=0){POD_SRC='lang:'+fc;}
 else{POD_SRC='dir:'+fc;}
 podPaint();};
function podShow(){
 if(POD.loading)return;
 POD.loading=true;
 var refresh=$('podrefresh');if(refresh)refresh.disabled=true;
 $('podlist').innerHTML='<div class="pempty">Loading podcasts...</div>';
 POD.request=fetch('/api/podcasts').then(function(r){return r.json()})
  .then(function(j){
   POD.loaded=true;POD.items=j.items||[];
   // Initialize chips and src select
   podPopulateChips();
   podPopulateSrc();
   // Build discover links including directory feeds
   var links='';
   (j.directories||[]).forEach(function(a){
    links+='<a class="big" target="_blank" rel="noopener" href="'+esc(a.url)+
     '">'+esc(a.name)+'</a>'});
   if(j.directory_feeds&&j.directory_feeds.length>0){
    links+='<span class="note">Directory feeds:</span>';
    j.directory_feeds.forEach(function(a){
     links+='<a class="mini" target="_blank" rel="noopener" href="'+esc(a.url)+'">'+esc(a.name)+' ('+esc(a.category)+')</a> ';});}
   $('podfeeds').innerHTML='<span class="note">Discover more:</span>'+links;
   // Reset filter state
   POD_SRC='';
   podPaint();
   })
   .catch(function(err){if(err&&err.name==='AbortError')return;
   $('podlist').innerHTML=
   '<div class="pempty">Could not load podcasts. <button class="big" onclick="podShow()">Retry</button></div>'})
   .then(function(){POD.loading=false;POD.request=null;
    if(refresh)refresh.disabled=false})}
 function podPaint(){
   var q=($('podq').value||'').toLowerCase(),
       items=POD.items||[],
       grouped={};
   // Extract filter from POD_SRC (could be "source_name" or "dir:category")
   var filterType = 'source', filterVal = POD_SRC;
   if(POD_SRC && POD_SRC.indexOf('dir:') === 0){
     filterType = 'dir'; filterVal = POD_SRC.substring(4);
   }
   for(var i=0;i<items.length;i++){
     var a=items[i];
     if(q&&(a.t+' '+a.s+' '+(a.b||'')).toLowerCase().indexOf(q)<0)continue;
     // Filter by source or directory category/language
     if(POD_SRC){
       if(filterType === 'source' && a.s !== filterVal)continue;
       if(filterType === 'dir'){
         // Filter by directory category or language
         var itemCat = a.cat || '';
         var itemLang = a.lang || '';
         if(itemCat !== filterVal && itemLang !== filterVal)continue;
       }
     }
     if(!grouped[a.s]) grouped[a.s]=[];
     grouped[a.s].push(a);
   }
   var h='';
   for(var source in grouped){
     if(!grouped.hasOwnProperty(source))continue;
     h+='<div class="podsource"><h4>'+esc(source)+'</h4>';
     for(var j=0;j<grouped[source].length;j++){
       var a=grouped[source][j];
       var fav=PS.isFavorite('podcasts',a)?'⭐':'☆';
       var cont='';
       var cItems=PS.getContinue('podcasts');
       if(cItems.find(function(c){return c.t===a.t}))cont=' <span class="conti">▶</span>';
       h+='<article class="podcard">'+(a.d?'<img src="'+esc(a.d)+
          '" loading="lazy" onerror="this.remove()">':'')+
          '<div class="podtext"><b>'+esc(a.t)+'</b><div class="nimeta">'+
          esc(a.s)+(a.pub?' &middot; '+agoT(a.pub):'')+
          ' <span class="podfav" onclick="PS.toggleFavorite(\'podcasts\',a);podPaint();event.stopPropagation()">'+fav+'</span>'+
          cont+'</div>'+
          (a.b?'<p>'+esc(a.b)+'</p>':'')+'</div>'+
          (a.audio?'<audio controls preload="none" src="'+esc(a.audio)+'"></audio>':'')+
          (a.l?'<a class="big blue" target="_blank" rel="noopener" href="'+
           esc(a.l)+'">Open</a>':'')+'</article>';
     }
     h+='</div>';
   }
   $('podlist').innerHTML=h||'<div class="pempty">No matching episodes.</div>';
 }
 $('podq').addEventListener('input',podPaint);
 $('podrefresh').onclick=function(){POD.loaded=false;podShow()};

/* ================= MARKETS PANEL ================= */
var MKT={timer:null,rows:null,watch:[],loading:false,request:null};
try{MKT.watch=JSON.parse(localStorage.getItem('srt-watch')||'null')||[]}
catch(e){}
if(!MKT.watch.length)MKT.watch=['RELIANCE.NS','TCS.NS','INFY.NS',
 'HDFCBANK.NS','AAPL','MSFT','NVDA'];
var IDX_IN=[['^NSEI','NIFTY 50'],['^BSESN','SENSEX'],
 ['^NSEBANK','BANK NIFTY'],['INR=X','USD/INR']];
var IDX_US=[['^DJI','DOW JONES'],['^GSPC','S&P 500'],['^IXIC','NASDAQ']];
function mkSyms(){return IDX_IN.concat(IDX_US).concat(
 MKT.watch.map(function(s){return[s,s]}))}
function money(n,cur){
 if(n==null||isNaN(n))return'-';
 var s=(Math.abs(n)>=1000)?
  n.toLocaleString('en-IN',{maximumFractionDigits:2}):n.toFixed(2);
 return(cur==='INR'?'\\u20B9':cur==='USD'?'$':'')+s}
function chgHtml(pr,pv){
 if(pr==null||!pv)return'<span class="mchg">-</span>';
 var d=pr-pv,p=d/pv*100,up=d>=0;
 return'<span class="mchg '+(up?'up':'down')+'">'+
  (up?'\\u25B2 ':'\\u25BC ')+Math.abs(p).toFixed(2)+'%</span>'}
function sparkV(vals,w,h){
 if(!vals||vals.length<2)return'';
 var mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals);
 var rng=(mx-mn)||1,col=vals[vals.length-1]>=vals[0]?'#16a34a':'#dc2626';
 var pts=[];
 for(var i=0;i<vals.length;i++){
  pts.push(((i/(vals.length-1))*w).toFixed(1)+','+
   (h-3-((vals[i]-mn)/rng)*(h-6)).toFixed(1))}
 return'<svg width="'+w+'" height="'+h+'"><polyline fill="none" stroke="'+
  col+'" stroke-width="2" points="'+pts.join(' ')+'"/></svg>'}
 function candleV(rows,w,h){
 if(!rows||rows.length<2)return'';
 rows=rows.slice(-80);var lo=Math.min.apply(null,rows.map(function(x){return x.l})),
  hi=Math.max.apply(null,rows.map(function(x){return x.h})),rng=(hi-lo)||1,step=w/rows.length;
 var s='<svg width="'+w+'" height="'+h+'" role="img" aria-label="candlestick chart">';
 rows.forEach(function(x,i){var up=x.c>=x.o,col=up?'#16a34a':'#dc2626',
   y=function(v){return h-4-((v-lo)/rng)*(h-8)},x0=i*step+step/2,
   top=y(Math.max(x.o,x.c)),bot=y(Math.min(x.o,x.c));
  s+='<line x1="'+x0.toFixed(1)+'" y1="'+y(x.h).toFixed(1)+'" x2="'+x0.toFixed(1)+'" y2="'+y(x.l).toFixed(1)+'" stroke="'+col+'"/>'+
   '<rect x="'+(i*step+1).toFixed(1)+'" y="'+top.toFixed(1)+'" width="'+Math.max(2,step-2).toFixed(1)+'" height="'+Math.max(1,bot-top).toFixed(1)+'" fill="'+col+'"/>'});
 return s+'</svg>'}
function barV(vals,w,h){
 if(!vals||vals.length<2)return'';
 var mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals),rng=(mx-mn)||1;
 var step=w/vals.length,b='';
 for(var i=0;i<vals.length;i++){
  var bh=Math.max(2,((vals[i]-mn)/rng)*(h-8));
  b+='<rect x="'+(i*step).toFixed(1)+'" y="'+(h-bh).toFixed(1)+
  '" width="'+Math.max(1,step-1).toFixed(1)+'" height="'+bh.toFixed(1)+
  '" fill="'+(vals[i]>=vals[0]?'#16a34a':'#dc2626')+'"/>'}
 return'<svg width="'+w+'" height="'+h+'">'+b+'</svg>'}
function mkRow(q,label,canRm){
 var live=q.state==='REGULAR'||q.state==='OPEN';
 var fav=PS.isFavorite('markets',q)?'⭐':'☆';
 return'<div class="mkrow" data-sym="'+esc(q.sym)+'" onclick="PS.addHistory({t:\''+(label||q.name||q.sym)+'\',u:\'/api/quote?sym='+esc(q.sym)+'\',tp:\'markets\'},\'markets\');PS.saveContinue({t:\''+(label||q.name||q.sym)+'\',u:\'/api/quote?sym='+esc(q.sym)+'\',tp:\'markets\'},\'markets\',0)">'+
  '<div class="mkid"><b>'+esc(label||q.name||q.sym)+'</b>'+
  '<span class="mkst '+(live?'live':'off')+'">'+(live?'LIVE':'CLOSED')+
  '</span>'+fav+(canRm?'<button class="rm" data-sym="'+esc(q.sym)+
  '" title="Remove">\\u2715</button>':'')+'</div>'+
  '<div class="mknum"><span class="mkp">'+money(q.price,q.cur)+'</span>'+
  chgHtml(q.price,q.prev)+'<small>O '+money(q.open,q.cur)+
  ' H '+money(q.high,q.cur)+' L '+money(q.low,q.cur)+
  ' C '+money(q.close,q.cur)+'</small></div>'+
  '<div class="mksk">'+sparkV(q.cl40,120,36)+'</div></div>'}
function mkPaint(){
 if(!MKT.rows)$('mkwrap').innerHTML=
  '<div class="pempty">Loading quotes&#8230;</div>';
 else mkRender()}
function mkRender(){
 var by={};(MKT.rows||[]).forEach(function(r){by[r.sym]=r});
 function sec(t,list,rm){
  var h='<h4 class="mksec">'+t+'</h4>';
  list.forEach(function(p){var q=by[p[0]];
   if(!q){h+='<div class="mkrow na"><div class="mkid"><b>'+esc(p[1])+
    '</b></div><span>unavailable</span></div>';return}
   h+=mkRow(q,p[1],rm)});
  return h}
 $('mkwrap').innerHTML=
  sec('&#127470;&#127475; INDIA',IDX_IN,false)+
  sec('&#127482;&#127480; US MARKETS',IDX_US,false)+
  '<h4 class="mksec">&#9733; MY WATCHLIST'+
  '<button class="mini" id="mkadd">+ add symbol</button></h4>'+
  (MKT.watch.length?
   MKT.watch.map(function(s){var q=by[s];
    return q?mkRow(q,null,true):
     '<div class="mkrow na"><div class="mkid"><b>'+esc(s)+
     '</b></div><span>unavailable</span></div>'}).join(''):
   '<div class="pempty">Tap + add to track stocks</div>');
 var ad=$('mkadd');if(ad)ad.onclick=mkAdd}
function saveWatch(){localStorage.setItem('srt-watch',
 JSON.stringify(MKT.watch))}
function mkRefresh(){
 if(MKT.loading)return;
 MKT.loading=true;
 MKT.request=fetch('/api/markets?symbols='+
  encodeURIComponent(mkSyms().map(function(p){return p[0]}).join(',')))
 .then(function(r){return r.json()})
 .then(function(j){MKT.rows=j.quotes||[];mkRender()})
 .catch(function(err){if(err&&err.name==='AbortError')return;
 $('mkwrap').innerHTML=
  '<div class="pempty">Quotes unavailable right now.<br>'+
  '<button class="big" onclick="mkRefresh()">Retry</button></div>'})
 .then(function(){MKT.loading=false;MKT.request=null})}
window.mkRefresh=mkRefresh;
function mkStart(){mkRefresh();clearInterval(MKT.timer);
 MKT.timer=setInterval(function(){if(MODE==='markets')mkRefresh()},60000)}
function mkStop(){clearInterval(MKT.timer)}
function mkAdd(){
 var s=(prompt('Stock symbol:\\nIndia: TATAMOTORS.NS, WIPRO.NS, SBIN.NS\\nUS: GOOG, AMZN, TSLA')||'').trim().toUpperCase();
 if(!s)return;
 if(!/^[A-Z0-9^.=-]{1,15}$/.test(s)){toast('Invalid symbol','bad');return}
 if(MKT.watch.indexOf(s)<0){MKT.watch.push(s);saveWatch();mkRefresh()}}
function mkRemove(sym){
 MKT.watch=MKT.watch.filter(function(x){return x!==sym});
 saveWatch();mkRefresh()}
$('mkwrap').onclick=function(e){
 if(e.target.id==='mkadd')return mkAdd();
 var rm=e.target.closest('.rm');
 if(rm)return mkRemove(rm.dataset.sym);
 var r=e.target.closest('.mkrow');
 if(r&&!r.classList.contains('na'))openChart(r.dataset.sym)};
/* market news sidebar */
function mkNews(){
 fetch('/api/news?cat=markets').then(function(r){return r.json()})
 .then(function(j){
  var it=(j.items||[]).slice(0,6),h='';
  for(var i=0;i<it.length;i++){
   h+='<article class="ni" data-mkl="'+esc(it[i].l)+'"><div class="nitxt">'+
    '<h3>'+esc(it[i].t)+'</h3><span class="nimeta">'+esc(it[i].s)+
    (it[i].pub?' &middot; '+agoT(it[i].pub):'')+'</span></div></article>'}
  $('mknews').innerHTML=h||
   '<div class="pempty">No market news loaded.</div>';
  var as=$('mknews').querySelectorAll('.ni');
  for(var k=0;k<as.length;k++)as[k].onclick=function(){
   var l=this.dataset.mkl;
   if(/^https?:/.test(l))window.open(l,'_blank','noopener')}})
 .catch(function(){$('mknews').innerHTML=
  '<div class="pempty">news unavailable</div>'})}
/* chart modal */
var CR={'1D':['1d','5m'],'5D':['5d','15m'],'1M':['1mo','60m'],
 '6M':['6mo','1d'],'1Y':['1y','1d']};
var CS={sym:null,range:'1M',type:'line'};
function openChart(sym){
 CS.sym=sym;CS.range='1M';
 $('chartsym').textContent=sym;
 showModal('chartmodal',true);loadChart()}
window.openChart=openChart;
function loadChart(){
 var rr=CR[CS.range],ph='';
 for(var k in CR)ph+='<button data-r="'+k+'" class="'+
  (k===CS.range?'active':'')+'">'+k+'</button>';
 $('chartpills').innerHTML=ph;
 var pb=$('chartpills').querySelectorAll('button');
 for(var i=0;i<pb.length;i++)pb[i].onclick=function(){
  CS.range=this.dataset.r;loadChart()};
 document.querySelectorAll('[data-ct]').forEach(function(b){
  b.className='mini '+(b.dataset.ct===CS.type?'active':'');
  b.onclick=function(){CS.type=this.dataset.ct;loadChart()}});
 $('bigchart').innerHTML='<div class="pempty">Loading&#8230;</div>';
 $('chkstats').textContent='';
 fetch('/api/mchart?sym='+encodeURIComponent(CS.sym)+
  '&range='+rr[0]+'&interval='+rr[1])
 .then(function(r){return r.json()})
 .then(function(j){
  var cl=j.cl||[];
  if(cl.length<2){$('bigchart').innerHTML=
   '<div class="pempty">No chart data</div>';return}
  $('bigchart').innerHTML=CS.type==='bar'?barV(cl,560,220):
   (CS.type==='candle'?candleV(j.candles,560,220):sparkV(cl,560,220));
  var lo=Math.min.apply(null,cl),hi=Math.max.apply(null,cl);
  $('chkstats').innerHTML='<b>'+money(j.price,j.cur)+'</b>'+
   chgHtml(j.price,j.prev)+'<span>low '+money(lo,j.cur)+'</span>'+
   '<span>high '+money(hi,j.cur)+'</span>'+
  '<span>open '+money(j.open,j.cur)+'</span><span>close '+
  money(j.close,j.cur)+'</span>'+
  (j.state?'<span>'+esc(j.state)+'</span>':'')+
  (j.name?'<span>'+esc(j.name)+'</span>':'')+
  (j.exchangeName?'<span>'+esc(j.exchangeName)+'</span>':'');
  fetch('/api/fundamentals?sym='+encodeURIComponent(CS.sym))
   .then(function(r){return r.json()}).then(function(f){
    if(f.error)return;
    $('chkstats').innerHTML+='<span>PE '+(f.pe==null?'-':f.pe.toFixed?
     f.pe.toFixed(2):f.pe)+'</span><span>mcap '+money(f.marketCap,j.cur)+
     '</span><span>'+esc(f.sector||'')+'</span><span>'+
     esc(f.industry||'')+'</span>';
   }).catch(function(){});
  })
 .catch(function(){$('bigchart').innerHTML=
  '<div class="pempty">Failed to load</div>'})}

/* ================= BOOKS PANEL ================= */
var BK={init:false,q:'',lang:'en,hi',page:1,hasNext:false,hasPrev:false,
 items:[],cur:null,pages:1,pg:0,total:0,
 rfs:parseInt(localStorage.getItem('srt-rfs')||'18',10)};
function bLangBtns(){var h='';
 [['en,hi','All'],['en','English'],
  ['hi','&#2361;&#2367;&#2344;&#2381;&#2342;&#2368;']].forEach(function(p){
  h+='<button data-l="'+p[0]+'" class="'+(BK.lang===p[0]?'active':'')+
   '">'+p[1]+'</button>'});
 $('bklang').innerHTML=h}
function bInit(){
 BK.init=true;
 var sv=localStorage.getItem('srt-blang');
 if(sv)BK.lang=sv;
 bLangBtns();bRestoreStrip();bSearch(true)}
function bSearch(reset){
 if(reset)BK.page=1;
 $('bkgrid').innerHTML='<div class="pempty">Searching&#8230;</div>';
 var u='/api/books?page='+BK.page+'&lang='+encodeURIComponent(BK.lang);
 if(BK.q)u+='&q='+encodeURIComponent(BK.q);
 fetch(u).then(function(r){return r.json()})
 .then(function(j){BK.items=j.items||[];
  BK.hasNext=!!j.next;BK.hasPrev=!!j.prev;bPaint();bPager()})
 .catch(function(){$('bkgrid').innerHTML=
  '<div class="pempty">Could not reach library.<br>'+
  '<button class="big" onclick="bSearch(true)">Retry</button></div>'})}
window.bSearch=bSearch;
function bPager(){$('bkpage').textContent='Page '+BK.page;
 $('bkprev').disabled=!BK.hasPrev;$('bknext').disabled=!BK.hasNext}
function bPaint(){
 if(!BK.items.length){$('bkgrid').innerHTML=
  '<div class="pempty">No books found.</div>';return}
 var h='';
 for(var i=0;i<BK.items.length;i++){var b=BK.items[i];
  var pos=null;
  try{pos=JSON.parse(localStorage.getItem('srt-book-'+b.id)||'null')}
  catch(e){}
  var fav=PS.isFavorite('books',b)?'⭐':'☆';
  h+='<div class="card book" data-id="'+b.id+'">'+
   (b.cov?'<img src="'+esc(b.cov)+'" loading="lazy" '+
    'onerror="this.replaceWith(document.createElement(\'div\'))">':
    '<div class="nocov">&#128214;</div>')+
   '<div class="cname" title="'+esc(b.t)+'">'+esc(b.t)+'</div>'+
   '<div class="grp">'+esc(b.a)+'</div>'+
   '<div class="grp">&#11015; '+(b.d||0).toLocaleString()+
   (pos&&pos.pc?' &middot; '+pos.pc+'%':'')+'</div>'+
   '<button class="watch" data-id="'+b.id+'">'+fav+' &#128214; '+
   (pos?'Continue':'Read')+'</button></div>'}
 $('bkgrid').innerHTML=h}
$('bkgrid').onclick=function(e){
 var c=e.target.closest('.book');if(!c)return;
 if(e.target.closest('.watch')){
  var b=BK.items.find(function(x){return x.id===parseInt(c.dataset.id,10)});
  if(b)PS.toggleFavorite('books',b);
  bPaint();return}
 var t=c.querySelector('.cname');
 var b=BK.items.find(function(x){return x.id===parseInt(c.dataset.id,10)});
 if(b){PS.addHistory(b,'books');PS.saveContinue(b,'books',0)}
 openBook(parseInt(c.dataset.id,10),t?t.textContent:'Book')};
$('bklang').onclick=function(e){var b=e.target.closest('button');if(!b)return;
 BK.lang=b.dataset.l;localStorage.setItem('srt-blang',BK.lang);
 bLangBtns();bSearch(true)};
$('bks').onclick=function(){BK.q=$('bq').value.trim();bSearch(true)};
var BQT=null;
$('bq').addEventListener('input',function(){clearTimeout(BQT);
 BQT=setTimeout(function(){BK.q=$('bq').value.trim();bSearch(true)},450)});
$('bkprev').onclick=function(){if(BK.hasPrev){BK.page--;bSearch(false)}};
$('bknext').onclick=function(){if(BK.hasNext){BK.page++;bSearch(false)}};
function bRestoreStrip(){
 var arr=[];
 try{
  for(var i=0;i<localStorage.length;i++){
   var k=localStorage.key(i);
   if(k&&k.indexOf('srt-book-')===0){
    var v=JSON.parse(localStorage.getItem(k)||'null');
    if(v&&v.pc>0&&v.pc<100&&v.t)
     arr.push({id:k.slice(9),pc:v.pc,t:v.t})}}}
 catch(e){}
 arr.sort(function(a,b){return b.pc-a.pc});
 if(!arr.length){$('bkcont').innerHTML='';return}
 var h='<b>Continue:</b>';
 arr.slice(0,4).forEach(function(p){
  h+='<button class="mini contb" data-id="'+p.id+'" data-t="'+
   esc(p.t)+'">'+esc(p.t.slice(0,22))+' '+p.pc+'%</button>'});
 $('bkcont').innerHTML=h;
 var bs=$('bkcont').querySelectorAll('.contb');
 for(var j=0;j<bs.length;j++)bs[j].onclick=function(){
  openBook(parseInt(this.dataset.id,10),this.dataset.t)}}
/* fullscreen reader */
function openBook(id,title){
 BK.cur={id:id,t:title};
 $('bvtitle').textContent=title;
 $('bookview').setAttribute('data-bv',
  localStorage.getItem('srt-bvtheme')||'paper');
 $('bvtext').style.fontSize=BK.rfs+'px';
 var pos=null;
 try{pos=JSON.parse(localStorage.getItem('srt-book-'+id)||'null')}
 catch(e){}
 loadPage(pos?pos.pg:0);
 $('bookview').style.display='flex';
 document.body.style.overflow='hidden'}
window.openBook=openBook;
function closeBook(){
 if(BK.cur)savePos();
 $('bookview').style.display='none';
 document.body.style.overflow=''}
window.closeBook=closeBook;
function savePos(){
 if(!BK.cur||!BK.total)return;
 var pc=Math.min(100,Math.round(((BK.pg+1)/BK.pages)*100));
 lsSet('srt-book-'+BK.cur.id,{pg:BK.pg,pc:pc,t:BK.cur.t});
 bRestoreStrip()}
function loadPage(pg){
 BK.pg=pg;
 $('bvtext').innerHTML='<div class="pempty">Loading&#8230;</div>';
 fetch('/api/booktext?id='+BK.cur.id+'&page='+pg)
 .then(function(r){return r.json()})
 .then(function(j){
  BK.pages=j.pages;BK.total=j.total;BK.pg=j.page;
  $('bvtext').textContent=j.text;
  $('bvtext').scrollTop=0;
  $('bvprog').textContent=(j.page+1)+' / '+j.pages+' pages';
  savePos()})
 .catch(function(){$('bvtext').innerHTML=
  '<div class="pempty">Failed to load text.</div>'})}
$('bvprev').onclick=function(){if(BK.pg>0)loadPage(BK.pg-1)};
$('bvnext').onclick=function(){if(BK.pg<BK.pages-1)loadPage(BK.pg+1)};
$('bvclose').onclick=closeBook;
$('bvfa').onclick=function(){BK.rfs=Math.max(12,BK.rfs-2);
 $('bvtext').style.fontSize=BK.rfs+'px';
 localStorage.setItem('srt-rfs',BK.rfs)};
$('bvfb').onclick=function(){BK.rfs=Math.min(30,BK.rfs+2);
 $('bvtext').style.fontSize=BK.rfs+'px';
 localStorage.setItem('srt-rfs',BK.rfs)};
$('bvtheme').onclick=function(){
 var T=['paper','sepia','night'];
 var cur=$('bookview').getAttribute('data-bv')||'paper';
 $('bookview').setAttribute('data-bv',
  T[(T.indexOf(cur)+1)%T.length]);
 localStorage.setItem('srt-bvtheme',
  $('bookview').getAttribute('data-bv'))};

/* ===== CHECKS / WELCOME ===== */
function runChecks(){
 fetch('/api/health').then(function(r){return r.json()}).then(function(j){
  var row=function(l,v,t){return '<div class="wb"><span>'+l+
   '</span><b class="'+v+'">'+t+'</b></div>'};
  $('wbchecks').innerHTML=
   row('Internet',j.net?'pass':'fail',j.net?'OK':'offline?')+
   row('VLC on PC',j.vlc?'pass':'warn',
    j.vlc?'found':'not found (TV needs it)')+
   row('Phone access',(j.lan||j.ts)?'pass':'warn',
    j.ts?'Wi-Fi + Anywhere ready':(j.lan?'home Wi-Fi ready':'no network'))+
   row('Firewall rule',j.fw?'pass':'warn',j.fw?'exists':'may need rule')+
   row('TV+Radio DB',j.radio?'pass':'warn',
    j.radio?'reachable':'blocked?')+
   row('News RSS',j.news?'pass':'warn',j.news?'OK':'blocked?')+
   row('Markets API',j.yax?'pass':'warn',j.yax?'OK':'blocked?')+
   row('Books API',j.books?'pass':'warn',j.books?'OK':'blocked?')})
 .catch(function(){$('wbchecks').innerHTML=
  '<p>Could not run checks.</p>'})}
function maybeWelcome(){
 if(!localStorage.getItem('iptv-welcomed')){
  showModal('welcome',true);runChecks()}}
$('help').onclick=function(){runChecks();showModal('welcome',true)};
$('home').onclick=function(){setMode('tv');load('in');
 window.scrollTo(0,0)};

/* ===== LOAD SOURCE (media) ===== */
function load(pl){var token=++S.loadToken;
 if(S.loadAbort){try{S.loadAbort.abort()}catch(e){}}
 S.loadAbort=new AbortController();
 S.pl=pl;S.cat='all';S.q='';$('q').value='';
 buildTabs();
 $('playall').disabled=(pl==='favs'||pl==='recent');
 document.title=plain(pl==='favs'?T_FAV:pl==='recent'?T_REC:
  (PL[pl]?PL[pl].n:'Sg_ent_media_radio'))+' - Sg_ent_media_radio';
 if(pl==='favs'||pl==='recent'){S.now={};buildChips();render(true);return}
 if(S.cache[pl]){S.chans=S.cache[pl];S.now={};buildChips();render(true);
  if(isTV(pl))loadNow();return}
 $('loader').style.display='grid';
 fetch('/api/channels?p='+pl,{signal:S.loadAbort.signal})
 .then(function(r){if(!r.ok)throw new Error('channel request failed');return r.json()})
 .then(function(j){S.chans=j.channels.map(function(c){
   return{n:c.name,u:c.url,l:c.logo,g:c.group,lg:c.lang||'',id:c.id||''}});
  if(token!==S.loadToken)return;
  S.cache[pl]=S.chans;
  $('loader').style.display='none';
  if(isTV(pl)){S.now={};loadNow()}
  buildChips();render(true)})
 .catch(function(err){if(err&&err.name==='AbortError'){
  if(token===S.loadToken)$('loader').style.display='none';
  return}
  $('loader').style.display='none';
  $('grid').innerHTML='<div class="errbox"><h3>Could not load</h3>'+
   '<br>Check your internet connection.<br><br>'+
   '<button class="big" onclick="load(\''+pl+'\')">Retry</button></div>'})}

/* ===== EVENTS ===== */
$('mainnav').onclick=function(e){
 var b=e.target.closest('button');if(b)setMode(b.dataset.mode)};
$('tabs').onclick=function(e){if(e.target.dataset.pl)load(e.target.dataset.pl)};
$('chips').onclick=function(e){var b=e.target.closest('button');if(!b)return;
 S.cat=b.dataset.c;buildChips();render(true)};
$('grid').onclick=function(e){
 var v=e.target.closest('.altvlc');
 if(v){fetch('/play?url='+encodeURIComponent(v.dataset.vlc))
  .then(function(r){return r.json()})
  .then(function(j){toast(j.msg,j.ok?'ok':'bad')});return}
 var w=e.target.closest('.watch');
 if(w)return route(findAny(w.dataset.u)||{n:'?',u:w.dataset.u},w.dataset.u);
 var f=e.target.closest('.fav');if(f)return toggleFav(f.dataset.u);
 var d=e.target.closest('.dot');if(d)return test(d.dataset.u,true)};
$('q').addEventListener('input',function(){clearTimeout(window._qt);
 window._qt=setTimeout(function(){
  S.q=$('q').value.trim();
  if(window.location.hash==='#home'){
   if(S.q.length>2){showGlobalSearch();}
   else{showHomeDashboard();}
  }else{
   if(!S.q)S.cat='all';
   buildChips();render(true);
  }
 },200)});
document.addEventListener('keydown',function(e){
 if($('bookview').style.display==='flex'){
  if(e.key==='ArrowRight'&&BK.pg<BK.pages-1)loadPage(BK.pg+1);
  if(e.key==='ArrowLeft'&&BK.pg>0)loadPage(BK.pg-1);
  if(e.key==='Escape')closeBook();
  return}
 if(e.key==='/'&&!ISMOBILE&&document.activeElement!==$('q')&&
  MODE==='media'){e.preventDefault();$('q').focus()}
 if(e.key==='Escape'){
  ['mobpanel','guidepanel','setpanel','welcome','readerview','chartmodal','playermodal']
   .forEach(function(m){showModal(m,false)});
  if(document.activeElement===$('q')&&MODE==='media'){
   $('q').value='';$('q').dispatchEvent(new Event('input'))}}});
$('okfirst').addEventListener('change',function(){render(true)});
$('mob').onclick=function(){showModal('mobpanel',true)};
$('set').onclick=function(){showModal('setpanel',true)};
$('cacheclear').onclick=window.clearCache;
$('cachetop').onclick=function(){if(confirm('Clear downloaded data and stream checks?'))clearCache()};
$('guide').onclick=openGuide;
$('more').onclick=function(){showModal('utilitypanel',true)};
$('moreguide').onclick=function(){showModal('utilitypanel',false);openGuide()};
$('moreset').onclick=function(){showModal('utilitypanel',false);showModal('setpanel',true)};
$('moretheme').onclick=function(){showModal('utilitypanel',false);$('themebtn').click()};
$('morehelp').onclick=function(){showModal('utilitypanel',false);runChecks();showModal('welcome',true)};
$('playall').onclick=function(){
 if(S.pl==='favs'||S.pl==='recent')return;
 if(ISMOBILE&&!confirm('Play this list on the PC?'))return;
 fetch('/playall?p='+S.pl).then(function(r){return r.json()})
 .then(function(j){toast(j.msg,j.ok?'ok':'bad')})};
$('quit').onclick=function(){
 if(!confirm('Stop the Sg_ent_media_radio server for ALL devices?'))return;
 fetch('/quit').then(function(){toast('Server stopped','ok')})};
new IntersectionObserver(function(es){es.forEach(function(e){
 if(e.isIntersecting&&S.shown<filtered().length)render(false)})
 }).observe($('sentinel'));

(function(){
 if(ISMOBILE||IS_CLOUD){$('quit').style.display='none'}
 if(ISMOBILE){$('mob').style.display='none';
  if($('setupPhone'))$('setupPhone').style.display='none'}
 if(IS_CLOUD){$('playall').style.display='none';$('pbvlc').style.display='none'}
 var h='';
 for(var k in PL)h+='<a class="big '+(PL[k].t==='radio'?'cy':'blue')+
  '" href="/m3u?p='+k+'">&#11015; '+plain(PL[k].n)+' (.m3u)</a>';
 $('mlinks').innerHTML=h;
})();
window.load=load;load('in');setMode('tv');maybeWelcome();
