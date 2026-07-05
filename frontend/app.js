const API='http://'+location.hostname+':8091/api';
const APP_VERSION='1.3.7';
let selectedArtist=null, selectedAlbum=null, selectedTagFolder=null;
let browserMode='artist';
let lastRunning=false;
let uiBusy=false;
let reference=null;
let selectedAlbumAnalysis=null;
let selectedBatch=new Map();
let selectedTracks=new Map();

function fmt(n,d=1){return n===null||n===undefined?'':Number(n).toFixed(d)}
function dur(s){s=Number(s||0);let h=Math.floor(s/3600),m=Math.floor((s%3600)/60);return h?`${h}h ${m}m`:`${m}m`}
function trackNo(t){if(!t.track_number)return'';return (!t.track_total || Number(t.track_total)===0) ? String(t.track_number) : `${t.track_number}/${t.track_total}`}
function relPath(p){return String(p||'').replace(/^\/music\//,'')}
function escHtml(v){return String(v ?? '').replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function clearSearch(){
  if(!search) return;
  search.value='';
  loadBrowser();
}
function handleSearchInput(){
  // Im Album-Modus soll eine eingegebene Suche immer global suchen –
  // auch wenn vorher ein Interpret angeklickt wurde.
  // Ohne diese Entkopplung blieb die Albumliste optisch/inhaltlich auf
  // "Alben von <Interpret>" hängen.
  if(browserMode==='album' && (search.value||'').trim()){
    selectedArtist=null;
  }
  loadBrowser();
}
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
  [btnAnalyze,btnRef].forEach(b=>{ if(b) b.disabled = isBusy || !selectedAlbum; });
  renderBatchBar();
  updateNormalizeGuard();
  updateTrackSelectionUI();
}

function batchKey(artist, album){return `${artist||''}\u0000${album||''}`}
function batchItem(artist, album){return {artist:artist||null, album:album}}
function albumCard(x){
  const itemArtist = selectedArtist || (Number(x.artist_count||0)===1 ? x.artist : null);
  const ref=isReferenceAlbum(itemArtist,x.album);
  const selected=x.album===selectedAlbum && ((selectedArtist||null)===(itemArtist||null) || !selectedArtist);
  const key=batchKey(itemArtist,x.album);
  const checked=selectedBatch.has(key);
  const cls=`album ${selected?'sel':''} ${ref?'ref':''}`;
  const title=`${itemArtist?itemArtist+' – ':''}${x.album}`;
  const label=ref?' <span class="reflabel">Referenz</span>':'';
  return `<div class="${cls}" title="${escHtml(title)}" data-album="${encodeURIComponent(x.album)}" data-artist="${itemArtist?encodeURIComponent(itemArtist):''}"><input class="pick" type="checkbox" ${checked?'checked':''} title="Album auswählen"><b>${ref?'⭐ ':''}${escHtml(x.album)}${label}</b><br><span class="small">${x.tracks} Titel · ${x.analyzed}/${x.tracks} analysiert</span><br><span class="small">Ø ${x.avg_lufs??'-'} LUFS · TP ${x.max_true_peak??'-'} · LRA ${x.avg_lra??'-'}</span></div>`;
}

function renderBatchBar(){
  const count=selectedBatch.size;
  batchBar.classList.toggle('show', count>0);
  batchInfo.textContent = count===1 ? '1 Album ausgewählt' : `${count} Alben ausgewählt`;
  if(typeof albumAction !== 'undefined' && albumAction){
    const optRef=albumAction.querySelector('option[value="reference"]');
    const optAnalyze=albumAction.querySelector('option[value="analyze"]');
    const optNorm=albumAction.querySelector('option[value="normalize"]');
    if(optRef) optRef.disabled = count!==1;
    if(optAnalyze) optAnalyze.disabled = count===0;
    if(optNorm) optNorm.disabled = count===0;
    if(count!==1 && albumAction.value==='reference') albumAction.value='';
    if(count===0 && ['reference','analyze','normalize'].includes(albumAction.value)) albumAction.value='';
  }
  if(typeof btnAlbumAction !== 'undefined' && btnAlbumAction){
    btnAlbumAction.disabled = uiBusy || !(albumAction && albumAction.value);
  }
}

async function runAlbumAction(){
  if(!albumAction || !albumAction.value) return;
  const action=albumAction.value;
  if(action==='selectVisible'){ selectVisibleAlbums(); albumAction.value=''; renderBatchBar(); return; }
  if(action==='clear'){ clearBatchSelection(); albumAction.value=''; renderBatchBar(); return; }
  if(action==='reference'){ await setSelectedBatchReference(); albumAction.value=''; renderBatchBar(); return; }
  if(action==='analyze'){ await analyzeSelectedAlbums(); albumAction.value=''; renderBatchBar(); return; }
  if(action==='normalize'){ await normalizeSelectedAlbums(); albumAction.value=''; renderBatchBar(); return; }
}

function clearTrackSelection(){
  selectedTracks.clear();
  document.querySelectorAll('.trackPick').forEach(c=>c.checked=false);
  if(trackSelectAll) trackSelectAll.checked=false;
  updateTrackSelectionUI();
}
function toggleTrack(path, title, checked){
  if(checked) selectedTracks.set(path, {path, title});
  else selectedTracks.delete(path);
  updateTrackSelectionUI();
}
function toggleAllTracks(checked){
  document.querySelectorAll('.trackPick').forEach(cb=>{
    cb.checked=checked;
    toggleTrack(cb.dataset.path, cb.dataset.title || cb.dataset.path, checked);
  });
}
function selectedTrackPaths(){return Array.from(selectedTracks.values()).map(x=>x.path)}
function updateTrackSelectionUI(){
  const count=selectedTracks.size;
  if(btnTrackNorm){
    btnTrackNorm.disabled = uiBusy || count===0;
    btnTrackNorm.textContent = count>1 ? `${count} Titel normalisieren` : 'Titel normalisieren';
  }
  if(trackSelectAll){
    const all=[...document.querySelectorAll('.trackPick')];
    trackSelectAll.checked = all.length>0 && all.every(x=>x.checked);
    trackSelectAll.indeterminate = count>0 && !trackSelectAll.checked;
  }
}

function toggleBatchAlbum(artist, album, checked){
  const key=batchKey(artist, album);
  if(checked) selectedBatch.set(key, batchItem(artist, album));
  else selectedBatch.delete(key);
  renderBatchBar();
}

function selectedBatchArray(){return Array.from(selectedBatch.values())}
async function setSelectedBatchReference(){
  const items=selectedBatchArray();
  if(items.length!==1) return;
  const item=items[0];
  try{
    const ref=await j(API+'/reference',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({artist:item.artist || '', album:item.album})
    });
    reference=ref;
    selectedArtist=item.artist || selectedArtist;
    selectedAlbum=item.album;
    await loadSettings();
    await loadReference();
    await loadBrowser();
    await loadAlbums();
    await selectAlbum(item.album);
    status.textContent='Referenzalbum gesetzt';
  }catch(e){
    alert('Referenz konnte nicht gesetzt werden:\n'+e.message+'\n\nHinweis: Das Album muss zuerst analysiert sein.');
  }
}
function clearBatchSelection(){selectedBatch.clear();document.querySelectorAll('.album .pick').forEach(c=>c.checked=false);renderBatchBar()}
function selectVisibleAlbums(){
  document.querySelectorAll('#albums .album[data-album]').forEach(el=>{
    const album=decodeURIComponent(el.dataset.album||'');
    const artist=el.dataset.artist ? decodeURIComponent(el.dataset.artist) : null;
    const cb=el.querySelector('.pick');
    if(album){ selectedBatch.set(batchKey(artist,album), batchItem(artist,album)); if(cb) cb.checked=true; }
  });
  renderBatchBar();
}

async function loadSettings(){
  let s=await j(API+'/settings');
  targetLufs.value=s.target_lufs;
  truePeak.value=s.true_peak;
  lra.value=s.lra;
  if(s.backup_mode) backupMode.value=s.backup_mode;
  if(s.parallel_analysis) parallelAnalysis.value=s.parallel_analysis;
  if(typeof musicRoot!=='undefined' && s.music_root) musicRoot.value=s.music_root;
  if(typeof watchMode!=='undefined' && s.watch_mode) watchMode.value=s.watch_mode;
  updateTargetInfo();
  if(typeof syncSettingsPageFromMain==='function') syncSettingsPageFromMain();
}

function updateTargetInfo(){
  const bm={on:'/data/backups',sidecar:'.bak',off:'kein Backup'}[backupMode.value]||backupMode.value;
  const bmShort={on:'ein',sidecar:'.bak',off:'aus'}[backupMode.value]||backupMode.value;
  targetInfo.textContent=`Ziel ${targetLufs.value} LUFS · TP ${truePeak.value} · LRA ${lra.value} · Backup ${bm} · ${parallelAnalysis.value}×`;
  const mr=(typeof musicRoot!=='undefined' && musicRoot.value) ? musicRoot.value : '/music';
  const wm=(typeof watchMode!=='undefined' && watchMode.value && watchMode.value!=='off') ? ` · Watch: ${watchMode.options[watchMode.selectedIndex].text}` : '';
  if(typeof settingsLine!=='undefined') settingsLine.textContent=`Backup: ${bmShort} · Parallel: ${parallelAnalysis.value}× · Musik: ${mr}${wm}`;
}

async function saveSettings(){
  await j(API+'/settings',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({target_lufs:targetLufs.value,true_peak:truePeak.value,lra:lra.value,backup_mode:backupMode.value,parallel_analysis:parallelAnalysis.value,music_root:musicRoot.value,watch_mode:watchMode.value})
  });
  updateTargetInfo();
}


async function checkMusicRoot(){
  try{
    const path=(musicRoot.value||'/music').trim();
    const res=await j(API+'/settings/check_music_root?path='+encodeURIComponent(path));
    if(musicRootStatus){
      if(res.ok){
        const suffix=res.sample_audio_files>0 ? ` · Audiodateien gefunden` : ' · keine Audiodateien im Stichprobentest';
        musicRootStatus.textContent=`✓ Pfad erreichbar${suffix}`;
        musicRootStatus.className='small okText';
      }else{
        musicRootStatus.textContent=`⚠ Pfad nicht nutzbar: ${res.exists?'kein lesbarer Ordner':'nicht gefunden'}`;
        musicRootStatus.className='small warnText';
      }
    }
  }catch(e){
    if(musicRootStatus){
      musicRootStatus.textContent='⚠ Prüfung fehlgeschlagen: '+e.message;
      musicRootStatus.className='small warnText';
    }
  }
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
    updateTargetInfo();
  }
}
function albumFullyAnalyzed(){
  return selectedAlbumAnalysis && Number(selectedAlbumAnalysis.tracks||0)>0 && Number(selectedAlbumAnalysis.analyzed||0)===Number(selectedAlbumAnalysis.tracks||0);
}

function updateNormalizeGuard(){
  const ok = !!selectedAlbum && albumFullyAnalyzed() && !uiBusy;
  btnNorm.disabled = !ok;
  if(!selectedAlbum && selectedTagFolder===null){
    normalizePreview.textContent='';
  }else if(!albumFullyAnalyzed()){
    normalizePreview.textContent='Normalisierung gesperrt: Album zuerst vollständig analysieren.';
  }else{
    normalizePreview.textContent='Normalisierung möglich. Vor dem Überschreiben erscheint eine Vorschau.';
  }
}


async function loadStats(){
  let s=await j(API+'/stats');
  sArtists.textContent=s.artists;
  sAlbums.textContent=s.albums;
  sTracks.textContent=s.tracks;
  sAnalyzed.textContent=s.analyzed;
  sDuration.textContent=dur(s.duration);
}

function setBrowserMode(mode){
  browserMode=mode;
  search.value='';
  modeArtist.classList.toggle('active', mode==='artist');
  modeAlbum.classList.toggle('active', mode==='album');
  if(typeof modeNew !== 'undefined' && modeNew) modeNew.classList.toggle('active', mode==='new');
  browserTitle.textContent = mode==='artist' ? 'Interpreten' : (mode==='album' ? 'Alben' : 'Neu gefunden');
  search.placeholder = mode==='artist' ? 'Interpreten suchen...' : (mode==='album' ? 'Alben suchen...' : 'Neue Alben suchen...');
  loadBrowser();
}

async function loadBrowser(){
  if(browserMode==='album') return loadAlbumBrowser();
  if(browserMode==='new') return loadNewBrowser();
  return loadArtists();
}

function bindArtistRows(){
  document.querySelectorAll('#browserList .row[data-artist]').forEach(el=>{
    el.onclick=()=>selectArtist(decodeURIComponent(el.dataset.artist));
  });
}

function bindAlbumRows(){
  document.querySelectorAll('#browserList .row[data-album], #browserList .row[data-folder]').forEach(el=>{
    el.onclick=()=>{
      if(el.dataset.folder && currentView==='tags'){
        return selectTagFolder(
          decodeURIComponent(el.dataset.folder),
          decodeURIComponent(el.dataset.album || ''),
          el.dataset.artist ? decodeURIComponent(el.dataset.artist) : null
        );
      }
      return selectAlbumFromBrowser(
        decodeURIComponent(el.dataset.album),
        el.dataset.artist ? decodeURIComponent(el.dataset.artist) : null
      );
    };
  });
}

function bindAlbumCards(){
  document.querySelectorAll('#albums .album[data-album]').forEach(el=>{
    const album=decodeURIComponent(el.dataset.album||'');
    const artist=el.dataset.artist ? decodeURIComponent(el.dataset.artist) : null;
    const cb=el.querySelector('.pick');
    if(cb){
      cb.onclick=(ev)=>{ev.stopPropagation();toggleBatchAlbum(artist, album, cb.checked)};
    }
    el.onclick=(ev)=>{
      if(ev.target && ev.target.classList && ev.target.classList.contains('pick')) return;
      if(artist && artist!==selectedArtist){
        selectedArtist=artist;
        selectArtist(artist,true).then(()=>selectAlbum(album));
      }else{
        selectAlbum(album);
      }
    };
  });
  renderBatchBar();
}

async function loadArtists(){
  let q=encodeURIComponent(search.value||'');
  let a=await j(API+'/artists?q='+q);
  browserList.innerHTML=a.map(x=>`<div class="row ${x.artist===selectedArtist?'sel':''}" data-artist="${encodeURIComponent(x.artist)}"><b>${escHtml(x.artist)}</b><br><span class="small">${x.albums} Alben · ${x.tracks} Titel</span></div>`).join('') || '<div class="empty">Keine Interpreten gefunden.</div>';
  bindArtistRows();
}

async function loadAlbumBrowser(){
  const rawQ=(search.value||'').trim();
  let q=encodeURIComponent(rawQ);
  let a;
  if(rawQ){
    // Sobald im Album-Tab gesucht wird, wird immer global gesucht.
    // Das verhindert, dass ein vorher ausgewählter Interpret die Treffer begrenzt.
    selectedArtist=null;
  }
  // Tags-Ansicht: Wenn ein Interpret gewählt ist und kein Suchbegriff gesetzt ist,
  // zeigen wir dessen Alben. Sobald gesucht wird, sucht der Album-Tab wieder global.
  // Dadurch funktioniert die Albumsuche auch nach einem vorherigen Interpreten-Klick.
  if(currentView==='tags'){
    const url = API+'/tag_albums?q='+q + (selectedArtist && !rawQ ? '&artist='+encodeURIComponent(selectedArtist) : '');
    a=await j(url);
    browserTitle.textContent = selectedArtist && !rawQ ? 'Albumordner von '+selectedArtist : (rawQ ? 'Albumordner suchen' : 'Albumordner');
    browserList.innerHTML=a.map(x=>{
      const active = x.folder===selectedTagFolder;
      const artistData = x.artist && Number(x.artist_count||0)===1 ? ` data-artist="${encodeURIComponent(x.artist)}"` : '';
      const tagHint = x.tag_album && x.tag_album!==x.album ? ` · Tag: ${escHtml(x.tag_album)}` : '';
      return `<div class="row ${active?'sel':''}" data-folder="${encodeURIComponent(x.folder||'')}" data-album="${encodeURIComponent(x.album)}"${artistData}><b>${escHtml(x.album)}</b><br><span class="small">${escHtml(x.artist)} · ${x.tracks} Titel · ${x.analyzed}/${x.tracks} analysiert${tagHint}</span></div>`;
    }).join('') || '<div class="empty">Keine Albumordner gefunden.</div>';
    bindAlbumRows();
    return;
  }
  a=await j(API+'/library_albums?q='+q);
  browserTitle.textContent= rawQ ? 'Alben suchen' : 'Alben';
  browserList.innerHTML=a.map(x=>{
    const oneArtist = Number(x.artist_count||0)===1;
    const artistData = oneArtist ? ` data-artist="${encodeURIComponent(x.artist)}"` : '';
    const active = x.album===selectedAlbum && (!selectedArtist || x.artist===selectedArtist || !oneArtist);
    return `<div class="row ${active?'sel':''}" data-album="${encodeURIComponent(x.album)}"${artistData}><b>${escHtml(x.album)}</b><br><span class="small">${escHtml(x.artist)} · ${x.tracks} Titel · ${x.analyzed}/${x.tracks} analysiert</span></div>`;
  }).join('') || '<div class="empty">Keine Alben gefunden.</div>';
  bindAlbumRows();
}

async function loadNewBrowser(){
  let q=encodeURIComponent(search.value||'');
  let a=await j(API+'/new_albums?q='+q);
  browserList.innerHTML=a.map(x=>{
    const oneArtist = Number(x.artist_count||0)===1;
    const artistData = oneArtist ? ` data-artist="${encodeURIComponent(x.artist)}"` : '';
    const active = x.album===selectedAlbum && (!selectedArtist || x.artist===selectedArtist);
    const missing = Math.max(0, Number(x.tracks||0)-Number(x.analyzed||0));
    return `<div class="row ${active?'sel':''}" data-album="${encodeURIComponent(x.album)}"${artistData}><b>${escHtml(x.album)}</b><br><span class="small">${escHtml(x.artist)} · ${x.tracks} Titel · ${missing} offen</span></div>`;
  }).join('') || '<div class="empty">Keine neuen/offenen Alben.</div>';
  bindAlbumRows();
}

async function selectAlbumFromBrowser(album, artist=null){
  selectedTagFolder=null;
  selectedArtist=artist;
  selectedAlbum=album;
  await loadBrowser();
  await loadAlbums();
  await selectAlbum(album);
}

async function selectTagFolder(folder, displayAlbum, artist=null){
  selectedTagFolder=folder || '';
  selectedAlbum=displayAlbum || folder || '';
  selectedArtist=artist || null;
  await loadBrowser();
  await loadTagsPage();
}

async function selectArtist(a, keepAlbum=false){
  selectedArtist=a;
  if(!keepAlbum){
    selectedAlbum=null;
    selectedTagFolder=null;
  }

  // Tags-Ansicht: ein Klick auf einen Interpreten zeigt sofort dessen Alben in der linken Liste.
  if(currentView==='tags' && !keepAlbum){
    browserMode='album';
    modeArtist.classList.remove('active');
    modeAlbum.classList.add('active');
    if(typeof modeNew !== 'undefined' && modeNew) modeNew.classList.remove('active');
    search.value='';
    search.placeholder='Alben suchen...';
  }

  await loadBrowser();
  await loadAlbums();

  if(!keepAlbum){
    tracks.innerHTML='';
    clearTrackSelection();
    albumSummary.textContent='';
    selectedAlbumAnalysis=null;
    normalizePreview.textContent='';
    setBusy(false);
    btnRef.disabled=true;
    btnAnalyze.disabled=true;
    btnNorm.disabled=true;
    if(currentView==='tags') loadTagsPage();
  }
}

async function loadAlbums(){
  if(!selectedArtist && selectedAlbum){
    const x=await j(API+'/library_album?album='+encodeURIComponent(selectedAlbum));
    albumsCount.textContent = `${x.artist} · Album`;
    albums.innerHTML = albumCard(x);
    bindAlbumCards();
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
  bindAlbumCards();

  if(selectedAlbum && !list.some(x=>x.album===selectedAlbum)){
    selectedAlbum=null;
    tracks.innerHTML='';
    clearTrackSelection();
    albumSummary.textContent='';
    selectedAlbumAnalysis=null;
    normalizePreview.textContent='';
    btnRef.disabled=true;
    btnAnalyze.disabled=true;
    btnNorm.disabled=true;
  }
}


async function selectAlbum(a){
  selectedAlbum=a;

  document.querySelectorAll('.album').forEach(e=>e.classList.remove('sel'));
  [...document.querySelectorAll('.album')].find(e=>decodeURIComponent(e.dataset.album||'')===a)?.classList.add('sel');

  let url=API+'/tracks?album='+encodeURIComponent(a);
  if(selectedArtist) url+='&artist='+encodeURIComponent(selectedArtist);
  let t=await j(url);
  selectedTracks.clear();
  tracks.innerHTML=t.map(x=>`<tr><td><input type="checkbox" class="trackPick" data-path="${escHtml(relPath(x.path))}" data-title="${escHtml(x.title)}"></td><td>${trackNo(x)}</td><td>${escHtml(x.title)}<br><span class="small">${escHtml(relPath(x.path))}</span></td><td class="right">${fmt(x.input_i,1)}</td><td class="right">${fmt(x.input_tp,1)}</td><td class="right">${fmt(x.input_lra,1)}</td><td class="right">${x.bitrate?Math.round(x.bitrate/1000):''}</td><td>${escHtml(x.codec)}</td></tr>`).join('');
  document.querySelectorAll('.trackPick').forEach(cb=>{cb.onchange=()=>toggleTrack(cb.dataset.path, cb.dataset.title || cb.dataset.path, cb.checked)});
  updateTrackSelectionUI();

  let anUrl=API+'/album_analysis?album='+encodeURIComponent(a);
  if(selectedArtist) anUrl+='&artist='+encodeURIComponent(selectedArtist);
  let an=await j(anUrl);
  selectedAlbumAnalysis=an;
  albumSummary.textContent=`${an.tracks} Titel · ${an.analyzed} analysiert · Ø ${an.avg_lufs??'-'} LUFS · TP ${an.max_true_peak??'-'} · LRA ${an.avg_lra??'-'}`;

  btnRef.disabled=false;
  btnAnalyze.disabled=false;
  updateNormalizeGuard();
  if(currentView==='tags') loadTagsPage();
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
async function normalizeAlbum(){
  if(!selectedAlbum)return;
  try{
    let previewUrl=API+'/normalize_preview?album='+encodeURIComponent(selectedAlbum);
    if(selectedArtist) previewUrl+='&artist='+encodeURIComponent(selectedArtist);
    let pv=await j(previewUrl);
    if(!pv.can_normalize){
      alert('Normalisierung nicht möglich:\n' + (pv.reason || 'Unbekannter Grund'));
      return;
    }
    const backupText = backupMode.value==='off' ? 'kein Backup' : (backupMode.value==='sidecar' ? '.bak neben der Datei' : 'Backup unter /data/backups');
    const delta = pv.gain_delta===null ? '-' : (pv.gain_delta>0 ? '+'+pv.gain_delta : String(pv.gain_delta));
    const msg = `Album normalisieren?

${pv.album}
Titel: ${pv.tracks}
Aktuell: ${pv.current_lufs} LUFS
Ziel: ${pv.target_lufs} LUFS
Änderung: ${delta} dB
True Peak: ${pv.true_peak}
LRA: ${pv.lra}
Backup: ${backupText}

Dateien werden überschrieben.`;
    if(!confirm(msg)) return;
    lastRunning=true;
    let url=API+'/normalize?album='+encodeURIComponent(selectedAlbum)+'&backup='+encodeURIComponent(backupMode.value);
    if(selectedArtist)url+='&artist='+encodeURIComponent(selectedArtist);
    await j(url,{method:'POST'});
    poll();
  }catch(e){
    status.textContent='Normalisierungs-Fehler';
    alert('Normalisierung konnte nicht gestartet werden:\n' + e.message);
  }
}

async function normalizeSelectedTracks(){
  const paths=selectedTrackPaths();
  if(!paths.length) return;
  try{
    const pv=await j(API+'/normalize_preview_tracks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({paths})});
    const lines=(pv.items||[]).slice(0,10).map(x=>{
      const delta=x.gain_delta===null || x.gain_delta===undefined ? '-' : (x.gain_delta>0 ? '+'+x.gain_delta : String(x.gain_delta));
      const status=x.can_normalize ? `${x.current_lufs} → ${x.target_lufs} LUFS (${delta} dB)` : `gesperrt: ${x.reason||'nicht möglich'}`;
      return `- ${x.title}: ${status}`;
    });
    if((pv.items||[]).length>10) lines.push(`... und ${(pv.items||[]).length-10} weitere`);
    if(!pv.can_normalize){
      alert('Nicht alle ausgewählten Titel können normalisiert werden:\n\n'+lines.join('\n'));
      return;
    }
    const backupText = backupMode.value==='off' ? 'kein Backup' : (backupMode.value==='sidecar' ? '.bak neben der Datei' : 'Backup unter /data/backups');
    const msg=`${pv.count_tracks} Titel normalisieren?\nZiel: ${pv.target_lufs} LUFS · TP ${pv.true_peak} · LRA ${pv.lra}\nBackup: ${backupText}\n\n${lines.join('\n')}\n\nDateien werden überschrieben.`;
    if(!confirm(msg)) return;
    lastRunning=true;
    status.textContent='Titel-Normalisierung wird gestartet...';
    await j(API+'/normalize_tracks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({paths, backup:backupMode.value})});
    await poll();
  }catch(e){
    status.textContent='Titel-Normalisierungs-Fehler';
    alert('Titel-Normalisierung konnte nicht gestartet werden:\n'+e.message);
  }
}


async function analyzeSelectedAlbums(){
  const albums=selectedBatchArray();
  if(!albums.length) return;
  if(!confirm(`${albums.length} Album/Alben analysieren?`)) return;
  try{
    lastRunning=true;
    status.textContent='Batch-Analyse wird gestartet...';
    await j(API+'/analyze_batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({albums})});
    await poll();
  }catch(e){
    status.textContent='Batch-Analyse-Fehler';
    alert('Batch-Analyse konnte nicht gestartet werden:\n'+e.message);
  }
}

async function normalizeSelectedAlbums(){
  const albums=selectedBatchArray();
  if(!albums.length) return;
  try{
    const pv=await j(API+'/normalize_preview_batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({albums})});
    const lines=(pv.items||[]).slice(0,12).map(x=>{
      const delta=x.gain_delta===null || x.gain_delta===undefined ? '-' : (x.gain_delta>0 ? '+'+x.gain_delta : String(x.gain_delta));
      const status=x.can_normalize ? `${x.current_lufs} → ${x.target_lufs} LUFS (${delta} dB)` : `gesperrt: ${x.reason||'nicht möglich'}`;
      return `- ${x.label}: ${status}`;
    });
    if((pv.items||[]).length>12) lines.push(`... und ${(pv.items||[]).length-12} weitere`);
    if(!pv.can_normalize){
      alert('Nicht alle ausgewählten Alben können normalisiert werden:\n\n'+lines.join('\n'));
      return;
    }
    const backupText = backupMode.value==='off' ? 'kein Backup' : (backupMode.value==='sidecar' ? '.bak neben der Datei' : 'Backup unter /data/backups');
    const msg=`${pv.count_albums} Album/Alben normalisieren?\n${pv.count_tracks} Titel\nZiel: ${pv.target_lufs} LUFS · TP ${pv.true_peak} · LRA ${pv.lra}\nBackup: ${backupText}\n\n${lines.join('\n')}\n\nDateien werden überschrieben.`;
    if(!confirm(msg)) return;
    lastRunning=true;
    status.textContent='Batch-Normalisierung wird gestartet...';
    await j(API+'/normalize_batch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({albums, backup:backupMode.value})});
    await poll();
  }catch(e){
    status.textContent='Batch-Normalisierungs-Fehler';
    alert('Batch-Normalisierung konnte nicht gestartet werden:\n'+e.message);
  }
}


async function stopJob(){
  try{
    btnStop.disabled=true;
    status.textContent='Abbruch wird angefordert...';
    await j(API+'/stop',{method:'POST'});
    await poll();
  }catch(e){
    status.textContent='Stop-Fehler';
    alert('Job konnte nicht gestoppt werden:\n'+e.message);
  }
}

function exportLog(errorsOnly=false){
  const url = API + '/log/export' + (errorsOnly ? '?errors_only=true' : '');
  const a = document.createElement('a');
  a.href = url;
  a.download = errorsOnly ? 'musiclab_errors.log' : 'musiclab.log';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function clearLog(){
  if(!confirm('Log wirklich löschen?')) return;
  try{
    await j(API + '/log/clear', {method:'POST'});
    await loadLog();
  }catch(e){
    alert('Log konnte nicht gelöscht werden:\n' + e.message);
  }
}

async function loadLog(){
  try{
    let l=await j(API+'/log');
    let lines=[...(l.errors||[]), ...(l.lines||[]).slice(-25)];
    logBox.textContent=lines.length ? lines.join('\n') : 'Noch kein Log.';
    logBox.scrollTop=logBox.scrollHeight;
  }catch(e){}
}



let currentView='audio';
function setAppView(view){
  currentView=view;
  document.querySelectorAll('.appView').forEach(el=>el.classList.toggle('active', el.id===view+'View'));
  [['tabAudio','audio'],['tabTags','tags'],['tabSettings','settings']].forEach(([id,v])=>{const b=document.getElementById(id); if(b)b.classList.toggle('active', view===v)});
  document.body.classList.toggle('settingsMode', view==='settings');
  if(view==='tags') loadTagsPage();
  if(view==='settings'){ syncSettingsPageFromMain(); checkMusicRootPage(); }
}
function openSettings(){setAppView('settings')}
function closeSettings(){setAppView('audio')}
function syncSettingsPageFromMain(){
  const pairs=[['targetLufs','targetLufsPage'],['truePeak','truePeakPage'],['lra','lraPage'],['backupMode','backupModePage'],['parallelAnalysis','parallelAnalysisPage'],['musicRoot','musicRootPage'],['watchMode','watchModePage']];
  for(const [a,b] of pairs){const x=document.getElementById(a), y=document.getElementById(b); if(x&&y)y.value=x.value;}
}
function syncSettingsMainFromPage(){
  const pairs=[['targetLufs','targetLufsPage'],['truePeak','truePeakPage'],['lra','lraPage'],['backupMode','backupModePage'],['parallelAnalysis','parallelAnalysisPage'],['musicRoot','musicRootPage'],['watchMode','watchModePage']];
  for(const [a,b] of pairs){const x=document.getElementById(a), y=document.getElementById(b); if(x&&y)x.value=y.value;}
}
async function saveSettingsAndStay(){
  syncSettingsMainFromPage();
  await saveSettings();
  await checkMusicRootPage();
  await loadSettings();
  alert('Einstellungen gespeichert.');
}
async function checkMusicRootPage(){
  const src=document.getElementById('musicRootPage');
  const dst=document.getElementById('musicRootStatusPage');
  if(!src||!dst)return;
  try{
    const res=await j(API+'/settings/check_music_root?path='+encodeURIComponent((src.value||'/music').trim()));
    if(res.ok){dst.textContent='✓ Pfad erreichbar'+(res.sample_audio_files>0?' · Audiodateien gefunden':'');dst.className='small okText'}
    else{dst.textContent='⚠ Pfad nicht nutzbar: '+(res.exists?'kein lesbarer Ordner':'nicht gefunden');dst.className='small warnText'}
  }catch(e){dst.textContent='⚠ Prüfung fehlgeschlagen: '+e.message;dst.className='small warnText'}
}
async function loadGenreOptions(){
  const list=document.getElementById('genreOptions');
  if(!list)return;
  try{
    const genres=await j(API+'/genres');
    list.innerHTML=(genres||[]).map(g=>`<option value="${escAttr(g)}"></option>`).join('');
  }catch(e){/* Genre-Liste optional */}
}

async function getTagTrackUrl(){
  if(selectedTagFolder!==null && selectedTagFolder!==undefined){
    return {url:API+'/tracks_by_folder?folder='+encodeURIComponent(selectedTagFolder), useArtist:null, byFolder:true};
  }
  let useArtist = selectedArtist;
  try{
    const meta = await j(API+'/library_album?album='+encodeURIComponent(selectedAlbum));
    if(Number(meta.artist_count||0)>1) useArtist = null;
  }catch(e){/* fallback */}
  let url=API+'/tracks?album='+encodeURIComponent(selectedAlbum);
  if(useArtist) url+='&artist='+encodeURIComponent(useArtist);
  return {url, useArtist, byFolder:false};
}

async function loadTagsPage(){
  const body=document.getElementById('tagTracks'); const hint=document.getElementById('tagHint');
  if(!body||!hint)return;
  if(!selectedAlbum && selectedTagFolder===null){
    hint.textContent = selectedArtist ? 'Bitte links ein Album von '+selectedArtist+' auswählen.' : 'Noch kein Album ausgewählt.';
    body.innerHTML='';
    const tt=document.getElementById('tagTrackTotal'); if(tt)tt.value=''; const dt=document.getElementById('tagDiscTotal'); if(dt)dt.value='';
    return;
  }
  try{
    const {url, useArtist, byFolder}=await getTagTrackUrl();
    const rows=await j(url);
    hint.textContent=`${byFolder?'Ordner · ':''}${useArtist?useArtist+' · ':''}${selectedAlbum} · ${rows.length} Titel`;
    if(rows.length){
      const first=rows[0];
      const aa=document.getElementById('tagAlbumArtist'), al=document.getElementById('tagAlbumName'), tt=document.getElementById('tagTrackTotal'), dt=document.getElementById('tagDiscTotal'), yr=document.getElementById('tagYear'), ge=document.getElementById('tagGenre');
      const artists=[...new Set(rows.map(r=>r.artist||'').filter(Boolean))];
      const albums=[...new Set(rows.map(r=>r.album||'').filter(Boolean))];
      if(aa)aa.value=artists.length===1 ? artists[0] : '';
      if(al)al.value=byFolder ? (selectedAlbum||first.album||'') : (albums.length===1 ? albums[0] : (selectedAlbum||''));
      if(tt)tt.value=rows.length;
      const discTotals=rows.map(r=>Number(r.disc_total||0)).filter(n=>n>0);
      if(dt)dt.value=discTotals.length ? Math.max(...discTotals) : '';
      if(yr)yr.value=first.year||'';
      if(ge)ge.value=first.genre||'';
    }
    await loadGenreOptions();
    const totalValue = document.getElementById('tagTrackTotal')?.value || (rows.length?String(rows.length):'');
    const discTotalValue = document.getElementById('tagDiscTotal')?.value || '';
    body.innerHTML=rows.map((x,i)=>{
      const trackNumber = x.track_number || parseInt(String(x.track_raw||'').split('/')[0],10) || (i+1);
      const discNumber = x.disc_number || parseInt(String(x.disc_raw||'').split('/')[0],10) || '';
      return `<tr data-path="${escAttr(relPath(x.path))}"><td>${i+1}</td><td><input class="tagTitle" value="${escAttr(x.title||'')}"></td><td><input class="tagArtist" value="${escAttr(x.artist||'')}"></td><td><input class="tagTrack" value="${escAttr(trackNumber)}"></td><td class="tagTotalShow">${escHtml(totalValue)}</td><td><input class="tagDisc" value="${escAttr(discNumber)}" placeholder="1"></td><td class="tagDiscTotalShow">${escHtml(discTotalValue||'-')}</td><td class="small" title="${escAttr(relPath(x.path))}">${escHtml(relPath(x.path))}</td></tr>`;
    }).join('');
  }catch(e){hint.textContent='Tags konnten nicht geladen werden: '+e.message; body.innerHTML='';}
}
function escAttr(s){return String(s ?? '').replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;')}
function syncTrackTotalPreview(){
  const total=(document.getElementById('tagTrackTotal')?.value||'').trim();
  document.querySelectorAll('.tagTotalShow').forEach(el=>el.textContent=total||'-');
}
function syncDiscTotalPreview(){
  const total=(document.getElementById('tagDiscTotal')?.value||'').trim();
  document.querySelectorAll('.tagDiscTotalShow').forEach(el=>el.textContent=total||'-');
}
async function saveAlbumTags(){
  const rows=[...document.querySelectorAll('#tagTracks tr[data-path]')];
  if(!rows.length){alert('Kein Album ausgewählt.');return;}
  const artist=document.getElementById('tagAlbumArtist')?.value||'';
  const album=document.getElementById('tagAlbumName')?.value||'';
  const year=document.getElementById('tagYear')?.value||'';
  const genre=document.getElementById('tagGenre')?.value||'';
  const updates=rows.map(r=>({path:r.dataset.path, artist, album, year, genre}));
  await saveTagUpdates(updates, 'Album-Tags gespeichert. Danach ist ein Scan sinnvoll.');
}
async function saveTrackTags(){
  const rows=[...document.querySelectorAll('#tagTracks tr[data-path]')];
  if(!rows.length){alert('Keine Titel geladen.');return;}
  const total=(document.getElementById('tagTrackTotal')?.value||'').trim();
  const discTotal=(document.getElementById('tagDiscTotal')?.value||'').trim();
  const updates=rows.map(r=>{
    const raw=(r.querySelector('.tagTrack')?.value||'').trim();
    const num=raw.split('/')[0].trim();
    const tracknumber = num ? (total ? `${num}/${total}` : num) : '';
    const discRaw=(r.querySelector('.tagDisc')?.value||'').trim();
    const discNum=discRaw.split('/')[0].trim();
    const discnumber = discNum ? (discTotal ? `${discNum}/${discTotal}` : discNum) : '';
    return {path:r.dataset.path,title:r.querySelector('.tagTitle')?.value||'',artist:r.querySelector('.tagArtist')?.value||'',tracknumber,discnumber};
  });
  await saveTagUpdates(updates, 'Titel-Tags gespeichert.');
}
async function saveTagUpdates(updates, okMsg){
  try{
    const res=await j(API+'/tags/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({updates})});
    alert(`${okMsg}\nGespeichert: ${res.updated}/${res.total}`+(res.errors?.length?'\nFehler:\n'+res.errors.join('\n'):''));
    await loadStats(); await loadBrowser(); await loadAlbums(); await loadGenreOptions(); if(selectedAlbum) await selectAlbum(selectedAlbum);
  }catch(e){alert('Tags konnten nicht gespeichert werden:\n'+e.message)}
}

async function loadHistory(){
  try{
    const h=await j(API+'/history?limit=40');
    if(!h.length){historyList.textContent='Noch keine Historie.';return;}
    historyList.innerHTML=h.map(x=>{
      const d=new Date((x.created_at||0)*1000).toLocaleString('de-DE');
      const artist=x.artist?escHtml(x.artist)+' – ':'';
      const before=x.before_lufs??'-'; const after=x.after_lufs??'-';
      const restored=x.restored_at?' · wiederhergestellt':'';
      const can=x.backups>0 && !x.restored_at;
      return `<div class="historyItem"><div><b>${artist}${escHtml(x.album)}</b><br>${d} · ${x.tracks} Titel · ${before} → ${after} LUFS · Backups ${x.backups}${restored}</div><button class="secondary" ${can?'':'disabled'} data-job="${escHtml(x.job_id)}" data-artist="${encodeURIComponent(x.artist||'')}" data-album="${encodeURIComponent(x.album)}">Wiederherstellen</button></div>`;
    }).join('');
    historyList.querySelectorAll('button[data-job]').forEach(btn=>{
      btn.onclick=()=>restoreHistory(btn.dataset.job, decodeURIComponent(btn.dataset.artist||''), decodeURIComponent(btn.dataset.album||''));
    });
  }catch(e){historyList.textContent='Historie konnte nicht geladen werden: '+e.message;}
}

async function restoreHistory(job_id, artist, album){
  if(!confirm(`Backup wiederherstellen?\n\n${artist?artist+' – ':''}${album}\n\nDie aktuellen Dateien werden durch das Backup ersetzt.`)) return;
  try{
    const res=await j(API+'/history/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id,artist,album})});
    alert(`Wiederhergestellt: ${res.restored}/${res.total}` + (res.errors?.length?`\nFehler: ${res.errors.join('\n')}`:''));
    await loadHistory(); await loadStats(); await loadAlbums(); if(selectedAlbum) await selectAlbum(selectedAlbum);
  }catch(e){alert('Wiederherstellung fehlgeschlagen:\n'+e.message)}
}

async function poll(){
  let s=await j(API+'/status');
  let p=s.total?Math.round(s.done/s.total*100):0;

  progress.style.width=p+'%';
  progressText.textContent=`${s.mode} · ${s.done}/${s.total} · Fehler ${s.errors} · ${s.current||s.message}`;
  status.textContent=s.message;
  const running=!!s.running;
  if(btnStop) btnStop.disabled=!running;
  if(running){
    btnAnalyze.disabled=true; btnNorm.disabled=true; btnRef.disabled=true; if(btnTrackNorm)btnTrackNorm.disabled=true; if(typeof btnAlbumAction !== 'undefined' && btnAlbumAction) btnAlbumAction.disabled=true;
  }else if(selectedAlbum){
    btnAnalyze.disabled=false; btnRef.disabled=false; updateNormalizeGuard(); updateTrackSelectionUI();
  }

  // Nur nach Abschluss eines Jobs neu laden. Kein permanentes Re-Rendering im Idle-Zustand,
  // damit die Albumauswahl nicht wieder zuklappt.
  await loadLog();

  if(lastRunning && !s.running){
    await loadStats();
    await loadReference();
    await loadHistory();
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
loadSettings().then(syncSettingsPageFromMain);
loadStats();
loadReference();
loadBrowser();
loadAlbums();
loadLog();
loadHistory();
renderBatchBar();
if(typeof albumAction !== 'undefined' && albumAction) albumAction.onchange = renderBatchBar;
poll();
