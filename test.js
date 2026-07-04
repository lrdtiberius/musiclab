
const API='http://'+location.hostname+':8091/api';
let selectedArtist=null, selectedAlbum=null;
let browserMode='artist';
let lastRunning=false;
let uiBusy=false;
let reference=null;

function fmt(n,d=1){return n===null||n===undefined?'':Number(n).toFixed(d)}
function dur(s){s=Number(s||0);let h=Math.floor(s/3600),m=Math.floor((s%3600)/60);return h?`${h}h ${m}m`:`${m}m`}
function trackNo(t){if(!t.track_number)return'';return (!t.track_total || Number(t.track_total)===0) ? String(t.track_number) : `${t.track_number}/${t.track_total}`}
function relPath(p){return String(p||'').replace(/^\/music\//,'')}
function escHtml(v){return String(v ?? '').replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function j(url,opt){
  const r = await fetch(url,opt);
  if(!r.ok){
    const txt = await r.text().catch(()=>'');
    throw new Error(`${r.status} ${r.statusText} ${txt}`);
  }
  return r.json();
}

function setBusy(isBusy){
  uiBusy=!!isBusy;
  [btnAnalyze,btnNorm,btnRef].forEach(b=>{ if(b) b.disabled = isBusy || !selectedAlbum; });
}

function albumCard(x){
  const ref=isReferenceAlbum(selectedArtist,x.album);
  const selected=x.album===selectedAlbum;
  const cls=`album ${selected?'sel':''} ${ref?'ref':''}`;
  const title=`${x.album}`;
  return `<div class="${cls}" title="${escHtml(title)}" onclick='selectAlbum(${JSON.stringify(x.album)})'><b>${ref?'⭐ ':''}${escHtml(x.album)}</b><br><span class="small">${x.tracks} Titel · ${x.analyzed}/${x.tracks} analysiert</span><br><span class="small">Ø ${x.avg_lufs??'-'} LUFS · TP ${x.max_true_peak??'-'} · LRA ${x.avg_lra??'-'}</span></div>`;
}

async function loadSettings(){
  let s=await j(API+'/settings');
  targetLufs.value=s.target_lufs;
  truePeak.value=s.true_peak;
  lra.value=s.lra;
}

async function saveSettings(){
  await j(API+'/settings',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({target_lufs:targetLufs.value,true_peak:truePeak.value,lra:lra.value})
  })
}


async function loadReference(){
  try{
    reference=await j(API+'/reference');
    if(reference && reference.is_set){
      referenceBox.className='small';
      referenceBox.innerHTML=`<span class="refpill">${escHtml(reference.artist_label || reference.artist || 'Verschiedene Interpreten')} – ${escHtml(reference.album)} · Ø ${reference.avg_lufs ?? '-'} LUFS · TP ${reference.max_true_peak ?? '-'} · LRA ${reference.avg_lra ?? '-'}</span>`;
      btnUseRef.disabled = reference.avg_lufs === null || reference.avg_lufs === undefined;
    }else{
      referenceBox.className='small refempty';
      referenceBox.textContent='Noch kein Referenzalbum festgelegt.';
      btnUseRef.disabled=true;
    }
  }catch(e){
    referenceBox.textContent='Referenz konnte nicht geladen werden.';
    btnUseRef.disabled=true;
  }
}

function isReferenceAlbum(artist, album){
  if(!reference || !reference.is_set || reference.album!==album) return false;
  if(reference.artist) return reference.artist===artist;
  return !artist;
}

async function setReference(){
  if(!selectedArtist || !selectedAlbum) return;
  try{
    let ref=await j(API+'/reference',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({artist:selectedArtist || '', album:selectedAlbum})
    });
    reference=ref;
    await loadSettings();
    await loadReference();
    if(selectedArtist) await selectArtist(selectedArtist,true);
    if(selectedAlbum) await selectAlbum(selectedAlbum);
    status.textContent='Referenzalbum gesetzt';
  }catch(e){
    status.textContent='Referenz-Fehler';
    alert('Referenz konnte nicht gesetzt werden:\n'+e.message+'\n\nHinweis: Das Album muss zuerst analysiert sein.');
  }
}

function useReferenceTarget(){
  if(reference && reference.is_set && reference.avg_lufs!==null && reference.avg_lufs!==undefined){
    targetLufs.value=reference.avg_lufs;
  }
}

async function loadStats(){
  let s=await j(API+'/stats');
  sArtists.textContent=s.artists;
  sAlbums.textContent=s.albums;
  sTracks.textContent=s.tracks;
  sAnalyzed.textContent=s.analyzed;
  sDuration.textContent=dur(s.duration);
  sSchema.textContent=s.schema_version;
}

function setBrowserMode(mode){
  browserMode=mode;
  search.value='';
  modeArtist.classList.toggle('active', mode==='artist');
  modeAlbum.classList.toggle('active', mode==='album');
  browserTitle.textContent = mode==='artist' ? 'Interpreten' : 'Alben';
  search.placeholder = mode==='artist' ? 'Interpreten suchen...' : 'Alben suchen...';
  loadBrowser();
}

async function loadBrowser(){
  if(browserMode==='album') return loadAlbumBrowser();
  return loadArtists();
}

async function loadArtists(){
  let q=encodeURIComponent(search.value||'');
  let a=await j(API+'/artists?q='+q);
  browserList.innerHTML=a.map(x=>`<div class="row ${x.artist===selectedArtist?'sel':''}" onclick='selectArtist(${JSON.stringify(x.artist)})'><b>${escHtml(x.artist)}</b><br><span class="small">${x.albums} Alben · ${x.tracks} Titel</span></div>`).join('') || '<div class="empty">Keine Interpreten gefunden.</div>';
}

async function loadAlbumBrowser(){
  let q=encodeURIComponent(search.value||'');
  let a=await j(API+'/library_albums?q='+q);
  browserList.innerHTML=a.map(x=>`<div class="row ${x.artist===selectedArtist && x.album===selectedAlbum?'sel':''}" onclick='selectAlbumFromBrowser(${JSON.stringify(x.album)})'><b>${escHtml(x.album)}</b><br><span class="small">${escHtml(x.artist)} · ${x.tracks} Titel · ${x.analyzed}/${x.tracks} analysiert</span></div>`).join('') || '<div class="empty">Keine Alben gefunden.</div>';
}

async function selectAlbumFromBrowser(album){
  selectedArtist=null;
  selectedAlbum=album;
  await loadBrowser();
  await loadAlbums();
  await selectAlbum(album);
}

async function selectArtist(a, keepAlbum=false){
  selectedArtist=a;
  if(!keepAlbum){
    selectedAlbum=null;
  }

  await loadBrowser();
  await loadAlbums();

  if(!keepAlbum){
    tracks.innerHTML='';
    albumSummary.textContent='';
    setBusy(false);
    btnRef.disabled=true;
    btnAnalyze.disabled=true;
    btnNorm.disabled=true;
  }
}

async function loadAlbums(){
  if(!selectedArtist && selectedAlbum){
    const x=await j(API+'/library_album?album='+encodeURIComponent(selectedAlbum));
    albumsCount.textContent = `${x.artist} · Album`;
    albums.innerHTML = albumCard(x);
    return;
  }
  if(!selectedArtist){
    albums.innerHTML='<div class="empty">Bitte links einen Interpreten oder ein Album auswählen.</div>';
    albumsCount.textContent='Keine Auswahl';
    return;
  }
  const list=await j(API+'/albums?artist='+encodeURIComponent(selectedArtist));
  albumsCount.textContent = `${selectedArtist} · ` + (list.length===1 ? '1 Album' : `${list.length} Alben`);
  albums.innerHTML=list.length ? list.map(albumCard).join('') : '<div class="empty">Kein Album gefunden.</div>';

  if(selectedAlbum && !list.some(x=>x.album===selectedAlbum)){
    selectedAlbum=null;
    tracks.innerHTML='';
    albumSummary.textContent='';
    btnRef.disabled=true;
    btnAnalyze.disabled=true;
    btnNorm.disabled=true;
  }
}


async function selectAlbum(a){
  selectedAlbum=a;

  document.querySelectorAll('.album').forEach(e=>e.classList.remove('sel'));
  [...document.querySelectorAll('.album')].find(e=>(e.querySelector('b')?.textContent||'').replace(/^⭐\s*/, '')===a)?.classList.add('sel');

  let url=API+'/tracks?album='+encodeURIComponent(a);
  if(selectedArtist) url+='&artist='+encodeURIComponent(selectedArtist);
  let t=await j(url);
  tracks.innerHTML=t.map(x=>`<tr><td>${trackNo(x)}</td><td>${escHtml(x.title)}<br><span class="small">Pfad: ${escHtml(relPath(x.path))}</span></td><td class="right">${fmt(x.input_i,1)}</td><td class="right">${fmt(x.input_tp,1)}</td><td class="right">${fmt(x.input_lra,1)}</td><td class="right">${x.bitrate?Math.round(x.bitrate/1000):''}</td><td>${escHtml(x.codec)}</td></tr>`).join('');

  let anUrl=API+'/album_analysis?album='+encodeURIComponent(a);
  if(selectedArtist) anUrl+='&artist='+encodeURIComponent(selectedArtist);
  let an=await j(anUrl);
  albumSummary.textContent=`${an.tracks} Titel · ${an.analyzed} analysiert · Ø ${an.avg_lufs??'-'} LUFS · TP ${an.max_true_peak??'-'} · LRA ${an.avg_lra??'-'}`;

  btnRef.disabled=false;
  btnAnalyze.disabled=false;
  btnNorm.disabled=false;
}

async function scan(){
  try{
    lastRunning=true;
    status.textContent='Scan wird gestartet...';
    await j(API+'/scan',{method:'POST'});
    await poll();
  }catch(e){
    status.textContent='Scan-Fehler';
    logBox.textContent='Scan konnte nicht gestartet werden:\n'+e.message;
    console.error(e);
  }
}
async function analyzeAll(){
  try{
    lastRunning=true;
    status.textContent='Analyse wird gestartet...';
    await j(API+'/analyze',{method:'POST'});
    await poll();
  }catch(e){
    status.textContent='Analyse-Fehler';
    logBox.textContent='Analyse konnte nicht gestartet werden:\n'+e.message;
    console.error(e);
  }
}
async function analyzeAlbum(){if(selectedAlbum){lastRunning=true;let url=API+'/analyze?album='+encodeURIComponent(selectedAlbum);if(selectedArtist)url+='&artist='+encodeURIComponent(selectedArtist);await j(url,{method:'POST'});poll()}}
async function normalizeAlbum(){if(!selectedAlbum)return;if(!confirm('Album wird direkt überschrieben. Fortfahren?'))return;lastRunning=true;let url=API+'/normalize?album='+encodeURIComponent(selectedAlbum);if(selectedArtist)url+='&artist='+encodeURIComponent(selectedArtist);await j(url,{method:'POST'});poll()}

async function loadLog(){
  try{
    let l=await j(API+'/log');
    let lines=[...(l.errors||[]), ...(l.lines||[]).slice(-25)];
    logBox.textContent=lines.length ? lines.join('\n') : 'Noch kein Log.';
    logBox.scrollTop=logBox.scrollHeight;
  }catch(e){}
}

async function poll(){
  let s=await j(API+'/status');
  let p=s.total?Math.round(s.done/s.total*100):0;

  progress.style.width=p+'%';
  progressText.textContent=`${s.mode} · ${s.done}/${s.total} · Fehler ${s.errors} · ${s.current||s.message}`;
  status.textContent=s.message;
  const running=!!s.running;
  if(running){
    btnAnalyze.disabled=true; btnNorm.disabled=true; btnRef.disabled=true;
  }else if(selectedAlbum){
    btnAnalyze.disabled=false; btnNorm.disabled=false; btnRef.disabled=false;
  }

  // Nur nach Abschluss eines Jobs neu laden. Kein permanentes Re-Rendering im Idle-Zustand,
  // damit die Albumauswahl nicht wieder zuklappt.
  await loadLog();

  if(lastRunning && !s.running){
    await loadStats();
    await loadReference();
    await loadBrowser();
    if(selectedArtist){
      await selectArtist(selectedArtist,true);
      if(selectedAlbum) await selectAlbum(selectedAlbum);
    }else if(selectedAlbum){
      await loadAlbums();
      await selectAlbum(selectedAlbum);
    }
  }

  lastRunning=s.running;
}

setInterval(poll,2000);
loadSettings();
loadStats();
loadReference();
loadBrowser();
loadAlbums();
loadLog();
poll();
