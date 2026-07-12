const API='http://'+location.hostname+':8091/api';
const APP_VERSION='2.0.0';
let coverCacheBust=Date.now();
let selectedArtist=null, selectedAlbum=null, selectedTagFolder=null;
let selectedUiKey=null; // v1.9.39: eindeutige visuelle Einzelauswahl für Listen und Album-Kacheln
let selectedTagGenre=null, selectedTagYear=null;
let browserMode='artist';
let lastRunning=false;
let uiBusy=false;
let reference=null;
let selectedAlbumAnalysis=null;
let selectedBatch=new Map();
let selectedTracks=new Map();
let selectedMediaArtist=null, selectedMediaFolder=null, selectedMediaAlbum=null;
let mediaArtistsCache=[];
let mediaAlbumsCache=[];
const mediaArtistAlbumsCache=new Map();
let mediaTracksRequestToken=0;
let mediaPageLoaded=false;
let tagDiscTotals={};
let tagsDirty=false;
let selectionSerial=0;

/* v1.9.39 Tag-Performance */
let tagRefreshTimer=null;
let lightRefreshTimer=null;
function scheduleLightRefresh(delay=700){
  clearTimeout(lightRefreshTimer);
  lightRefreshTimer=setTimeout(()=>{
    try{ loadStats(); }catch(e){ console.warn(e); }
    try{ loadGenreOptions(); }catch(e){ console.warn(e); }
  }, delay);
}
function scheduleTagsPageRefresh(delay=250){
  clearTimeout(tagRefreshTimer);
  tagRefreshTimer=setTimeout(()=>{
    try{ loadTagsPage(); }catch(e){ console.warn(e); }
  }, delay);
}
function setTagActionBusy(flag, text=''){
  document.body.classList.toggle('tagBusy', !!flag);
  if(text && typeof status!=='undefined' && status) status.textContent=text;
}


function updateViewportMetrics(){
  const header=document.querySelector('header');
  const h=header ? Math.ceil(header.getBoundingClientRect().height) : 76;
  document.documentElement.style.setProperty('--musiclab-header-h', h+'px');
  document.documentElement.style.setProperty('--musiclab-vh', window.innerHeight+'px');
}
window.addEventListener('resize', updateViewportMetrics, {passive:true});
window.addEventListener('orientationchange', updateViewportMetrics, {passive:true});


function fmt(n,d=1){return n===null||n===undefined?'':Number(n).toFixed(d)}
function dur(s){s=Number(s||0);let h=Math.floor(s/3600),m=Math.floor((s%3600)/60);return h?`${h}h ${m}m`:`${m}m`}
function trackNo(t){if(!t.track_number)return'';return (!t.track_total || Number(t.track_total)===0) ? String(t.track_number) : `${t.track_number}/${t.track_total}`}
function relPath(p){return String(p||'').replace(/^\/music\//,'')}
function parentFolderFromPath(p){const s=relPath(p); const i=s.lastIndexOf('/'); return i>0?s.slice(0,i):''}
function coverBox(src, large=false, opts={}){
  const id=opts.id ? ` id="${escAttr(opts.id)}"` : '';
  const extra=opts.extraClass ? ' '+opts.extraClass : '';
  const cls=(large?'mediaCoverBox large':'mediaCoverBox')+extra;
  const loading=opts.eager ? 'eager' : 'lazy';
  // v1.9.39: Cover-Boxen müssen beim Albumwechsel immer eine neue, eindeutige
  // DOM-Box bekommen. Besonders wichtig bei #tagCoverPreview: Wenn die ID beim
  // ersten Cover verloren geht, kann die Vorschau bei Albumwechseln nicht mehr
  // ersetzt werden und Safari zeigt das zuletzt sichtbare Cover weiter an.
  const safeSrc=escAttr(src||'');
  return `<div${id} class="${cls} loading" data-cover-src="${safeSrc}"><div class="coverFallback">♪</div><img src="${safeSrc}" loading="${loading}" onload="this.parentElement.classList.add('hasCover');this.parentElement.classList.remove('loading','noCover')" onerror="this.removeAttribute('src');this.style.display='none';this.parentElement.classList.add('noCover');this.parentElement.classList.remove('loading','hasCover')" alt=""></div>`;
}
function tagCoverPlaceholder(text='Cover wird geladen…'){
  const box=document.getElementById('tagCoverPreview');
  if(box){ box.outerHTML=`<div id="tagCoverPreview" class="mediaCoverBox large tagCoverBox loading noCover"><div class="coverFallback">♪</div></div>`; }
  const ci=document.getElementById('tagCoverInfo');
  if(ci) ci.textContent=text;
}
function tagCoverBox(src){
  return coverBox(src, true, {id:'tagCoverPreview', extraClass:'tagCoverBox', eager:true});
}
function coverUrl(folder, artist=''){return API+'/media/cover?folder='+encodeURIComponent(folder||'')+(artist?'&artist='+encodeURIComponent(artist):'')+'&v='+encodeURIComponent(APP_VERSION)+'&cb='+encodeURIComponent(coverCacheBust);}
function coverUrlPath(path){return API+'/media/cover_by_path?path='+encodeURIComponent(path||'')+'&v='+encodeURIComponent(APP_VERSION)+'&cb='+encodeURIComponent(coverCacheBust);}
function escHtml(v){return String(v ?? '').replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function resetTagFilters(){
  selectedArtist=null;
  selectedTagGenre=null;
  selectedTagYear=null;
}
function clearSearch(){
  if(!search) return;
  search.value='';
  // X bedeutet: Suche komplett leeren und die Standardliste des gewählten Suchtyps zeigen.
  if(currentView==='tags'){
    resetTagFilters();
    selectedAlbum=null;
    selectedTagFolder=null;
    selectedUiKey=null;
  }else if(browserMode==='album'){
    selectedArtist=null;
    selectedTagGenre=null;
    selectedTagYear=null;
  }
  loadBrowser();
  syncSingleSelectionUI();
  if(currentView==='tags') loadTagsPage();
}
function handleSearchInput(){
  // In der Tags-Seite ist die Suche immer global nach dem gewählten Suchtyp.
  if(currentView==='tags'){
    resetTagFilters();
  }else if(browserMode==='album' && (search.value||'').trim()){
    selectedArtist=null;
    selectedTagGenre=null;
    selectedTagYear=null;
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


function selectionKey(type, primary='', secondary=''){
  return [type || '', String(primary || ''), String(secondary || '')].join('\u0001');
}
function setSingleSelectionKey(key){
  selectedUiKey=key || null;
  clearVisibleSelectionUI();
  syncSingleSelectionUI();
}

function rowAlbumMatches(el, album, artist){
  if(!el || !album) return false;
  const elAlbum=decodeURIComponent(el.dataset.album||'');
  const elArtist=el.dataset.artist ? decodeURIComponent(el.dataset.artist) : null;
  if(elAlbum!==album) return false;
  if(artist===undefined) artist=selectedArtist || null;
  if(artist) return elArtist===artist;
  return true;
}
function syncSingleSelectionUI(){
  // v1.9.39: Die UI-Markierung ist an einen eindeutigen Schlüssel gebunden.
  // Dadurch können beim Wechsel nicht mehr mehrere Interpreten/Alben markiert bleiben,
  // auch wenn Albumtitel mehrfach vorkommen oder alte async-Ladevorgänge zurückkommen.
  document.querySelectorAll('#browserList .row.sel').forEach(el=>el.classList.remove('sel'));
  document.querySelectorAll('#albums .album.sel').forEach(el=>el.classList.remove('sel'));
  if(selectedUiKey){
    document.querySelectorAll(`[data-ui-key="${CSS.escape(selectedUiKey)}"]`).forEach(el=>el.classList.add('sel'));
    renderSelectionHint();
    return;
  }

  if(currentView==='tags' && selectedTagFolder){
    const key=selectionKey('folder', selectedTagFolder);
    document.querySelectorAll(`[data-ui-key="${CSS.escape(key)}"]`).forEach(el=>el.classList.add('sel'));
    return;
  }

  if(browserMode==='artist' && selectedArtist){
    const key=selectionKey('artist', selectedArtist);
    document.querySelectorAll(`[data-ui-key="${CSS.escape(key)}"]`).forEach(el=>el.classList.add('sel'));
  }else if((browserMode==='album' || browserMode==='new') && selectedAlbum){
    const key=selectionKey('album', selectedAlbum, selectedArtist || '');
    document.querySelectorAll(`[data-ui-key="${CSS.escape(key)}"]`).forEach(el=>el.classList.add('sel'));
  }
  renderSelectionHint();
}
function clearVisibleSelectionUI(){
  document.querySelectorAll('#browserList .row.sel, #albums .album.sel').forEach(el=>el.classList.remove('sel'));
}

function activeSelectionLabel(){
  if(currentView==='tags'){
    if(selectedTagFolder || selectedAlbum){
      const art = selectedArtist ? selectedArtist+' · ' : '';
      return art + (selectedAlbum || selectedTagFolder || 'Albumordner');
    }
    if(selectedArtist) return 'Interpret: '+selectedArtist;
    if(selectedTagGenre) return 'Genre: '+selectedTagGenre;
    if(selectedTagYear) return 'Jahr: '+selectedTagYear;
    return '';
  }
  if(selectedAlbum){
    return (selectedArtist ? selectedArtist+' · ' : '') + selectedAlbum;
  }
  if(selectedArtist) return 'Interpret: '+selectedArtist;
  return '';
}
function renderSelectionHint(){
  const box=document.getElementById('selectionHint');
  if(!box) return;
  const active=activeSelectionLabel();
  const batch=selectedBatch.size;
  const parts=[];
  if(active) parts.push(`<span class="selHintLine"><b>Aktiv:</b> ${escHtml(active)}</span>`);
  if(batch) parts.push(`<span class="selHintLine"><b>Markiert:</b> ${batch} ${batch===1?'Album':'Alben'}</span>`);
  box.classList.toggle('hidden', parts.length===0);
  box.innerHTML=parts.join('');
}
function browserRowBadges(kind, album='', artist='', folder=''){
  const badges=[];
  if(kind==='artist'){
    if(selectedArtist && artist && selectedArtist===artist) badges.push('<span class="sideBadge active">Aktiv</span>');
  }else{
    let active=false;
    if(folder){ active = !!selectedTagFolder && selectedTagFolder===folder; }
    else if(album){ active = !!selectedAlbum && selectedAlbum===album && (!artist || !selectedArtist || selectedArtist===artist); }
    if(active) badges.push('<span class="sideBadge active">Aktiv</span>');
    if(album){
      const key=batchKey(artist || null, album);
      if(selectedBatch.has(key)) badges.push('<span class="sideBadge marked">Markiert</span>');
    }
  }
  return badges.length ? '<span class="sideBadges">'+badges.join('')+'</span>' : '';
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
  const key=batchKey(itemArtist,x.album);
  const uiKey=selectionKey('album', x.album, itemArtist || '');
  const ref=isReferenceAlbum(itemArtist,x.album);
  const selected=selectedUiKey===uiKey;
  const checked=selectedBatch.has(key);
  const cls=`album ${selected?'sel':''} ${ref?'ref':''}`;
  const title=`${itemArtist?itemArtist+' – ':''}${x.album}`;
  const label=ref?' <span class="reflabel">Referenz</span>':'';
  return `<div class="${cls}" title="${escHtml(title)}" data-ui-key="${escAttr(uiKey)}" data-album="${encodeURIComponent(x.album)}" data-artist="${itemArtist?encodeURIComponent(itemArtist):''}"><input class="pick" type="checkbox" ${checked?'checked':''} title="Album auswählen"><b>${ref?'⭐ ':''}${escHtml(x.album)}${label}</b><br><span class="small">${x.tracks} Titel · ${x.analyzed}/${x.tracks} analysiert</span><br><span class="small">Ø ${x.avg_lufs??'-'} LUFS · TP ${x.max_true_peak??'-'} · LRA ${x.avg_lra??'-'}</span></div>`;
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
  updateAlbumActionButton();
  renderSelectionHint();
}

function updateAlbumActionButton(){
  if(typeof btnAlbumAction === 'undefined' || !btnAlbumAction) return;
  const hasSelection = selectedBatch && selectedBatch.size > 0;
  const action = albumAction ? albumAction.value : '';
  const isJobRunning = false; // Job-Zustand wird in poll() separat behandelt.
  btnAlbumAction.disabled = uiBusy || isJobRunning || !hasSelection || !action;
}

async function runAlbumAction(){
  if(!albumAction || !albumAction.value || selectedBatch.size===0) return;
  const action=albumAction.value;
  if(btnAlbumAction) btnAlbumAction.disabled=true;
  try{
    if(action==='selectVisible'){ selectVisibleAlbums(); albumAction.value=''; renderBatchBar(); return; }
    if(action==='clear'){ clearBatchSelection(); albumAction.value=''; renderBatchBar(); return; }
    if(action==='reference'){ await setSelectedBatchReference(); albumAction.value=''; renderBatchBar(); return; }
    if(action==='analyze'){ await analyzeSelectedAlbums(); albumAction.value=''; renderBatchBar(); return; }
    if(action==='normalize'){ await normalizeSelectedAlbums(); albumAction.value=''; renderBatchBar(); return; }
  }finally{
    updateAlbumActionButton();
  }
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
    await loadSettings(); checkApiVersion();
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
  let s={};
  try{ s=await j(API+'/settings'); }catch(e){ console.warn('Settings konnten nicht geladen werden:', e); }
  targetLufs.value=s.target_lufs || '-16';
  truePeak.value=s.true_peak || '-1.5';
  lra.value=s.lra || '11';
  backupMode.value=s.backup_mode || 'on';
  parallelAnalysis.value=s.parallel_analysis || '2';
  if(typeof parallelNormalize!=='undefined') parallelNormalize.value=s.parallel_normalize || '2';
  if(typeof musicRoot!=='undefined') musicRoot.value=s.music_root || '/music';
  if(typeof watchMode!=='undefined') watchMode.value=s.watch_mode || 'off';
  if(typeof sortAfterTags!=='undefined') sortAfterTags.value=s.sort_after_tags || 'off';
  if(typeof sortAfterTagsPage!=='undefined') sortAfterTagsPage.value=s.sort_after_tags || 'off';
  if(typeof smbBaseUrl!=='undefined') smbBaseUrl.value=s.smb_base_url || 'smb://DS923/Musik';
  if(typeof smbBaseUrlPage!=='undefined') smbBaseUrlPage.value=s.smb_base_url || 'smb://DS923/Musik';
  updateTargetInfo();
}


function updateTargetInfo(){
  const bm={on:'/data/backups',sidecar:'.bak',off:'kein Backup'}[backupMode.value]||backupMode.value;
  const bmShort={on:'ein',sidecar:'.bak',off:'aus'}[backupMode.value]||backupMode.value;
  const pn=(typeof parallelNormalize!=='undefined' && parallelNormalize.value) ? parallelNormalize.value : '2';
  targetInfo.textContent=`Ziel ${targetLufs.value} LUFS · TP ${truePeak.value} · LRA ${lra.value} · Backup ${bm} · Analyse ${parallelAnalysis.value}× · Norm ${pn}×`;
  const mr=(typeof musicRoot!=='undefined' && musicRoot.value) ? musicRoot.value : '/music';
  const wm=(typeof watchMode!=='undefined' && watchMode.value && watchMode.value!=='off') ? ` · Watch: ${watchMode.options[watchMode.selectedIndex].text}` : '';
  if(typeof settingsLine!=='undefined') settingsLine.textContent=`Backup: ${bmShort} · Analyse: ${parallelAnalysis.value}× · Norm: ${pn}× · Musik: ${mr}${wm}`;
}

async function saveSettings(){
  await j(API+'/settings',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({target_lufs:targetLufs.value,true_peak:truePeak.value,lra:lra.value,backup_mode:backupMode.value,parallel_analysis:parallelAnalysis.value,parallel_normalize:(typeof parallelNormalize!=='undefined'?parallelNormalize.value:'2'),music_root:musicRoot.value,watch_mode:watchMode.value,sort_after_tags:(typeof sortAfterTags!=='undefined'?sortAfterTags.value:(typeof sortAfterTagsPage!=='undefined'?sortAfterTagsPage.value:'off')),smb_base_url:(typeof smbBaseUrl!=='undefined'?smbBaseUrl.value:(typeof smbBaseUrlPage!=='undefined'?smbBaseUrlPage.value:'smb://DS923/Musik'))})
  });
  updateTargetInfo();
}


async function checkMusicRoot(){
  const path=(musicRoot.value||'/music').trim() || '/music';
  const endpoints=[
    API+'/settings/check_music_root?path='+encodeURIComponent(path),
    API+'/settings/check_music_root/?path='+encodeURIComponent(path),
    API+'/check_music_root?path='+encodeURIComponent(path),
    API+'/music_root/check?path='+encodeURIComponent(path)
  ];
  let lastErr=null;
  for(const url of endpoints){
    try{
      const res=await j(url);
      if(musicRootStatus){
        if(res.ok){
          const suffix=res.sample_audio_files>0 ? ` · ${res.sample_audio_files}+ Audiodatei(en) gefunden` : ' · erreichbar, aber im Stichprobentest keine Audiodateien';
          musicRootStatus.textContent=`✓ Pfad erreichbar: ${res.path || path}${suffix}`;
          musicRootStatus.className='small okText';
        }else{
          const why=res.exists ? (res.is_dir ? 'nicht lesbar' : 'kein Ordner') : 'nicht gefunden';
          musicRootStatus.textContent=`⚠ Pfad nicht nutzbar: ${res.path || path} · ${why}`;
          musicRootStatus.className='small warnText';
        }
      }
      return;
    }catch(e){
      lastErr=e;
      // 404 heißt fast immer: Backend ist noch alt oder wurde nicht neu gebaut.
      if(!String(e.message||'').includes('404')) break;
    }
  }
  if(musicRootStatus){
    musicRootStatus.textContent='⚠ Prüfung fehlgeschlagen: Backend-Endpunkt fehlt oder Backend ist nicht aktuell. Backend neu bauen. Details: '+(lastErr?.message||'unbekannt');
    musicRootStatus.className='small warnText';
  }
}

async function checkApiVersion(){
  try{
    const v=await j(API+'/version');
    if(v && v.version && v.version!==APP_VERSION){
      console.warn('Frontend/Backend-Version unterschiedlich:', APP_VERSION, v.version);
      if(typeof settingsLine!=='undefined'){
        settingsLine.textContent += ` · Backend ${v.version}`;
      }
    }
  }catch(e){
    console.warn('Backend-Version konnte nicht geprüft werden:', e);
  }
}

async function loadReference(){
  try{
    reference=await j(API+'/reference');
    if(reference && reference.is_set){
      referenceBox.className='small refWithClear';
      referenceBox.innerHTML=`<span class="refpill">${escHtml(reference.artist_label || reference.artist || 'Verschiedene Interpreten')} – ${escHtml(reference.album)} · Ø ${reference.avg_lufs ?? '-'} LUFS · TP ${reference.max_true_peak ?? '-'} · LRA ${reference.avg_lra ?? '-'}</span><button class="refClearBtn" onclick="clearReferenceAlbum()" title="Referenzalbum entfernen" aria-label="Referenzalbum entfernen">×</button>`;
      btnUseRef.disabled = reference.avg_lufs === null || reference.avg_lufs === undefined;
      const dref=document.getElementById('dashboardReference');
      if(dref){ dref.className='small'; dref.innerHTML=`${escHtml(reference.artist_label || reference.artist || 'Verschiedene Interpreten')} – ${escHtml(reference.album)}<br>LUFS ${reference.avg_lufs ?? '-'} · TP ${reference.max_true_peak ?? '-'} · LRA ${reference.avg_lra ?? '-'}`; }
    }else{
      referenceBox.className='small refempty';
      referenceBox.textContent='Noch kein Referenzalbum festgelegt.';
      const dref=document.getElementById('dashboardReference'); if(dref){dref.className='small refempty'; dref.textContent='Noch kein Referenzalbum festgelegt.';}
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

async function clearReferenceAlbum(){
  try{
    if(!confirm('Referenzalbum entfernen?\n\nDeine Ziel-LUFS in den Einstellungen bleiben unverändert.')) return;
    await j(API+'/reference',{method:'DELETE'});
    reference={is_set:false};
    await loadReference();
    if(selectedArtist) await selectArtist(selectedArtist,true);
    status.textContent='Referenzalbum entfernt';
  }catch(e){
    alert('Referenzalbum konnte nicht entfernt werden:\n'+e.message);
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
  const set=(id,val)=>{const el=document.getElementById(id); if(el) el.textContent=val};
  set('dArtists', s.artists);
  set('dAlbums', s.albums);
  set('dTracks', s.tracks);
  set('dDuration', dur(s.duration));
  set('dAnalyzed', s.analyzed);
  set('dMissingAnalysis', Math.max(0, Number(s.tracks||0)-Number(s.analyzed||0)));
}

async function loadDashboard(){
  await loadStats();
  await loadReference();
  const par=document.getElementById('parallelAnalysisPage')?.value || document.getElementById('parallelAnalysis')?.value || '-';
  const norm=document.getElementById('parallelNormalizePage')?.value || document.getElementById('parallelNormalize')?.value || '-';
  const dp=document.getElementById('dParallel'); if(dp) dp.textContent=par==='-'?'-':`Analyse ${par}x · Norm ${norm}x`;
}

function updateBrowserTabsForView(){
  const audioSwitch=document.getElementById('audioModeSwitch');
  const tagControls=document.getElementById('tagSearchControls');
  const tagSelect=document.getElementById('tagSearchType');
  if(audioSwitch) audioSwitch.style.display = currentView==='tags' ? 'none' : '';
  if(tagControls) tagControls.style.display = currentView==='tags' ? '' : 'none';
  if(currentView==='tags' && tagSelect) tagSelect.value = browserMode;
}
function setTagSearchType(type){
  setBrowserMode(type || 'album');
}
function setBrowserMode(mode){
  if(currentView==='audio' && (mode==='genre' || mode==='year')) mode='artist';
  if(currentView==='audio' && mode==='new'){};
  if(currentView==='tags' && mode==='new') mode='album';
  browserMode=mode;
  search.value='';
  if(currentView==='tags'){
    resetTagFilters();
    selectedAlbum=null;
    selectedTagFolder=null;
    selectedUiKey=null;
  }else if(mode==='album'){
    selectedArtist=null;
    selectedTagGenre=null;
    selectedTagYear=null;
  }
  if(typeof modeArtist !== 'undefined' && modeArtist) modeArtist.classList.toggle('active', mode==='artist');
  if(typeof modeAlbum !== 'undefined' && modeAlbum) modeAlbum.classList.toggle('active', mode==='album');
  if(typeof modeGenre !== 'undefined' && modeGenre) modeGenre.classList.toggle('active', mode==='new');
  if(typeof modeYear !== 'undefined' && modeYear) modeYear.style.display = 'none';
  const titleMap={artist:'Interpreten', album:'Alben', new:'Neu gefunden', genre:'Genres', year:'Jahre', issues:'Tag-Probleme'};
  const phMap={artist:'Interpreten suchen...', album:'Alben suchen...', new:'Neue Alben suchen...', genre:'Genre suchen...', year:'Jahr suchen...', issues:'Fehlerhafte Tags suchen...'};
  browserTitle.textContent = titleMap[mode] || 'Interpreten';
  search.placeholder = phMap[mode] || 'Suchen...';
  updateBrowserTabsForView();
  loadBrowser();
}

async function loadBrowser(){
  if(browserMode==='album') return loadAlbumBrowser();
  if(browserMode==='new') return loadNewBrowser();
  if(browserMode==='genre') return loadGenreBrowser();
  if(browserMode==='year') return loadYearBrowser();
  if(browserMode==='issues') return loadTagIssuesBrowser();
  return loadArtists();
}

function bindArtistRows(){
  document.querySelectorAll('#browserList .row[data-artist]').forEach(el=>{
    el.onclick=()=>{
      const artist=decodeURIComponent(el.dataset.artist);
      setSingleSelectionKey(el.dataset.uiKey || selectionKey('artist', artist));
      selectArtist(artist);
    };
  });
  syncSingleSelectionUI();
}

function bindAlbumRows(){
  document.querySelectorAll('#browserList .row[data-album], #browserList .row[data-folder]').forEach(el=>{
    el.onclick=()=>{
      setSingleSelectionKey(el.dataset.uiKey || null);
      if(el.dataset.folder && currentView==='tags'){
        return selectTagFolder(
          decodeURIComponent(el.dataset.folder),
          decodeURIComponent(el.dataset.album || ''),
          el.dataset.artist ? decodeURIComponent(el.dataset.artist) : null,
          el.dataset.uiKey || null
        );
      }
      return selectAlbumFromBrowser(
        decodeURIComponent(el.dataset.album),
        el.dataset.artist ? decodeURIComponent(el.dataset.artist) : null,
        el.dataset.uiKey || null
      );
    };
  });
  syncSingleSelectionUI();
}
function bindFilterRows(){
  document.querySelectorAll('#browserList .row[data-genre], #browserList .row[data-year]').forEach(el=>{
    el.onclick=()=>{
      if(el.dataset.genre) return selectTagFilter('genre', decodeURIComponent(el.dataset.genre));
      if(el.dataset.year) return selectTagFilter('year', decodeURIComponent(el.dataset.year));
    };
  });
}
async function selectTagFilter(kind, value){
  resetTagFilters();
  selectedTagGenre = kind==='genre' ? value : null;
  selectedTagYear = kind==='year' ? value : null;
  selectedAlbum=null;
  selectedTagFolder=null;
  selectedUiKey=null;
  browserMode='album';
  search.value='';
  const tagSelect=document.getElementById('tagSearchType');
  if(tagSelect) tagSelect.value='album';
  await loadBrowser();
  await loadTagsPage();
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
      setSingleSelectionKey(el.dataset.uiKey || selectionKey('album', album, artist || selectedArtist || ''));
      if(artist && artist!==selectedArtist){
        selectedArtist=artist;
        selectArtist(artist,true).then(()=>selectAlbum(album, selectedUiKey));
      }else{
        selectAlbum(album, selectedUiKey);
      }
    };
  });
  renderBatchBar();
  syncSingleSelectionUI();
}

async function loadArtists(){
  let q=encodeURIComponent(search.value||'');
  let a=await j(API+'/artists?q='+q);
  browserList.innerHTML=a.map(x=>{ const uiKey=selectionKey('artist', x.artist); return `<div class="row ${selectedUiKey===uiKey?'sel':''}" data-ui-key="${escAttr(uiKey)}" data-artist="${encodeURIComponent(x.artist)}"><b>${escHtml(x.artist)}</b>${browserRowBadges('artist','',x.artist)}<br><span class="small">${x.albums} Alben · ${x.tracks} Titel</span></div>`; }).join('') || '<div class="empty">Keine Interpreten gefunden.</div>';
  bindArtistRows();
  syncSingleSelectionUI();
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
    let url = API+'/tag_albums?q='+q;
    if(selectedArtist && !rawQ) url += '&artist='+encodeURIComponent(selectedArtist);
    if(selectedTagGenre && !rawQ) url += '&genre='+encodeURIComponent(selectedTagGenre);
    if(selectedTagYear && !rawQ) url += '&year='+encodeURIComponent(selectedTagYear);
    a=await j(url);
    let filterTitle = 'Albumordner';
    if(selectedArtist && !rawQ) filterTitle='Albumordner von '+selectedArtist;
    if(selectedTagGenre && !rawQ) filterTitle='Albumordner mit Genre '+selectedTagGenre;
    if(selectedTagYear && !rawQ) filterTitle='Albumordner aus '+selectedTagYear;
    browserTitle.textContent = rawQ ? 'Albumordner suchen' : filterTitle;
    browserList.innerHTML=a.map(x=>{
      const artistData = x.artist && Number(x.artist_count||0)===1 ? ` data-artist="${encodeURIComponent(x.artist)}"` : '';
      const isVirtual = String(x.folder||'').startsWith('__album__:') || x.virtual;
      const cleanTagAlbum = x.tag_album && x.tag_album !== 'Mehrere Album-Tags' ? x.tag_album : '';
      const shownAlbum = cleanTagAlbum || x.album;
      const folderHint = isVirtual ? ` · ${Number(x.folder_count||0)||'mehrere'} Ordner` : (cleanTagAlbum && cleanTagAlbum !== x.album ? ` · Ordner: ${escHtml(x.album)}` : '');
      const tagHint = x.tag_album === 'Mehrere Album-Tags' ? ' · Tag: Mehrere Album-Tags' : folderHint;
      const uiKey=selectionKey('folder', x.folder||'');
      const active = selectedUiKey===uiKey;
      return `<div class="row ${active?'sel':''}" data-ui-key="${escAttr(uiKey)}" data-folder="${encodeURIComponent(x.folder||'')}" data-album="${encodeURIComponent(shownAlbum)}"${artistData}><b>${escHtml(shownAlbum)}</b>${browserRowBadges('album', shownAlbum, Number(x.artist_count||0)===1 ? x.artist : '', x.folder||'')}<br><span class="small">${escHtml(x.artist)} · ${x.tracks} Titel · ${x.analyzed}/${x.tracks} analysiert${tagHint}</span></div>`;
    }).join('') || '<div class="empty">Keine Albumordner gefunden.</div>';
    bindAlbumRows();
    syncSingleSelectionUI();
    return;
  }
  a=await j(API+'/library_albums?q='+q);
  browserTitle.textContent= rawQ ? 'Alben suchen' : 'Alben';
  browserList.innerHTML=a.map(x=>{
    const oneArtist = Number(x.artist_count||0)===1;
    const artistData = oneArtist ? ` data-artist="${encodeURIComponent(x.artist)}"` : '';
    const uiArtist = oneArtist ? x.artist : '';
    const uiKey=selectionKey('album', x.album, uiArtist);
    const active = selectedUiKey===uiKey;
    return `<div class="row ${active?'sel':''}" data-ui-key="${escAttr(uiKey)}" data-album="${encodeURIComponent(x.album)}"${artistData}><b>${escHtml(x.album)}</b>${browserRowBadges('album', x.album, uiArtist)}<br><span class="small">${escHtml(x.artist)} · ${x.tracks} Titel · ${x.analyzed}/${x.tracks} analysiert</span></div>`;
  }).join('') || '<div class="empty">Keine Alben gefunden.</div>';
  bindAlbumRows();
  syncSingleSelectionUI();
}

async function loadGenreBrowser(){
  const rawQ=(search.value||'').trim().toLowerCase();
  const genres=await j(API+'/genres');
  const vals=(genres||[]).filter(g=>!rawQ || String(g).toLowerCase().includes(rawQ));
  browserTitle.textContent='Genres';
  browserList.innerHTML=vals.map(g=>`<div class="row" data-genre="${encodeURIComponent(g)}"><b>${escHtml(g)}</b></div>`).join('') || '<div class="empty">Keine Genres gefunden.</div>';
  bindFilterRows();
}
async function loadYearBrowser(){
  const rawQ=(search.value||'').trim().toLowerCase();
  const years=await j(API+'/years');
  const vals=(years||[]).filter(y=>!rawQ || String(y).toLowerCase().includes(rawQ));
  browserTitle.textContent='Jahre';
  browserList.innerHTML=vals.map(y=>`<div class="row" data-year="${encodeURIComponent(y)}"><b>${escHtml(y)}</b></div>`).join('') || '<div class="empty">Keine Jahre gefunden.</div>';
  bindFilterRows();
}


async function loadTagIssuesBrowser(){
  const rawQ=(search.value||'').trim();
  const issues=await j(API+'/tag_issues?q='+encodeURIComponent(rawQ));
  browserTitle.textContent = rawQ ? 'Tag-Probleme suchen' : 'Tag-Probleme';
  browserList.innerHTML=(issues||[]).map(x=>{
    const uiKey=selectionKey('folder', x.folder||'');
    const active = selectedUiKey===uiKey;
    const issueText=(x.issues||[]).slice(0,3).join(' · ')+((x.issues||[]).length>3?' · …':'');
    const artistData = x.artist && x.artist !== 'Verschiedene Interpreten' ? ` data-artist="${encodeURIComponent(x.artist)}"` : '';
    const album = x.album || x.folder || 'Unbekanntes Album';
    return `<div class="row ${active?'sel':''}" data-ui-key="${escAttr(uiKey)}" data-folder="${encodeURIComponent(x.folder||'')}" data-album="${encodeURIComponent(album)}"${artistData}><b>${escHtml(album)}</b>${browserRowBadges('album', album, x.artist && x.artist !== 'Verschiedene Interpreten' ? x.artist : '', x.folder||'')}<br><span class="small">${escHtml(x.artist||'')} · ${x.tracks} Titel · ${x.issue_count} Problem(e)</span><br><span class="small issueLine">${escHtml(issueText)}</span></div>`;
  }).join('') || '<div class="empty">Keine fehlenden oder fehlerhaften Tags gefunden.</div>';
  bindAlbumRows();
  syncSingleSelectionUI();
}

async function loadNewBrowser(){
  let q=encodeURIComponent(search.value||'');
  let a=await j(API+'/new_albums?q='+q);
  browserList.innerHTML=a.map(x=>{
    const oneArtist = Number(x.artist_count||0)===1;
    const artistData = oneArtist ? ` data-artist="${encodeURIComponent(x.artist)}"` : '';
    const uiArtist = oneArtist ? x.artist : '';
    const uiKey=selectionKey('album', x.album, uiArtist);
    const active = selectedUiKey===uiKey;
    const missing = Math.max(0, Number(x.tracks||0)-Number(x.analyzed||0));
    return `<div class="row ${active?'sel':''}" data-ui-key="${escAttr(uiKey)}" data-album="${encodeURIComponent(x.album)}"${artistData}><b>${escHtml(x.album)}</b><br><span class="small">${escHtml(x.artist)} · ${x.tracks} Titel · ${missing} offen</span></div>`;
  }).join('') || '<div class="empty">Keine neuen/offenen Alben.</div>';
  bindAlbumRows();
  syncSingleSelectionUI();
}

async function selectAlbumFromBrowser(album, artist=null, uiKey=null){
  const token=++selectionSerial;
  selectedTagFolder=null;
  selectedArtist=artist;
  selectedAlbum=album;
  selectedUiKey=uiKey || selectionKey('album', album, artist || '');
  syncSingleSelectionUI();
  await loadBrowser();
  if(token!==selectionSerial) return;
  await loadAlbums();
  if(token!==selectionSerial) return;
  await selectAlbum(album, selectedUiKey);
}

async function selectTagFolder(folder, displayAlbum, artist=null, uiKey=null){
  const token=++selectionSerial;
  selectedTagFolder=folder || '';
  selectedAlbum=displayAlbum || folder || '';
  selectedArtist=artist || null;
  selectedUiKey=uiKey || selectionKey('folder', selectedTagFolder);
  syncSingleSelectionUI();
  closeTagScraper();
  if(token!==selectionSerial) return;
  await loadTagsPage();
}


async function selectArtist(a, keepAlbum=false){
  const token=++selectionSerial;
  selectedArtist=a;
  if(!keepAlbum) selectedUiKey=selectionKey('artist', a);
  syncSingleSelectionUI();
  if(currentView==='tags'){selectedTagGenre=null;selectedTagYear=null;}
  if(!keepAlbum){
    selectedAlbum=null;
    selectedTagFolder=null;
    selectedUiKey=selectionKey('artist', a);
    syncSingleSelectionUI();
  }

  // Tags-Ansicht: ein Klick auf einen Interpreten zeigt sofort dessen Alben in der linken Liste.
  if(currentView==='tags' && !keepAlbum){
    browserMode='album';
    const tagSelect=document.getElementById('tagSearchType');
    if(tagSelect) tagSelect.value='album';
    modeArtist.classList.remove('active');
    modeAlbum.classList.add('active');
    if(typeof modeGenre !== 'undefined' && modeGenre) modeGenre.classList.remove('active');
    if(typeof modeYear !== 'undefined' && modeYear) modeYear.classList.remove('active');
    search.value='';
    search.placeholder='Alben suchen...';
  }

  await loadBrowser();
  if(token!==selectionSerial) return;
  await loadAlbums();
  if(token!==selectionSerial) return;
  syncSingleSelectionUI();

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
    syncSingleSelectionUI();
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
  syncSingleSelectionUI();

  if(selectedAlbum && !list.some(x=>x.album===selectedAlbum)){
    selectedAlbum=null;
    selectedUiKey=null;
    tracks.innerHTML='';
    clearTrackSelection();
    albumSummary.textContent='';
    selectedAlbumAnalysis=null;
    normalizePreview.textContent='';
    btnRef.disabled=true;
    btnAnalyze.disabled=true;
    btnNorm.disabled=true;
    syncSingleSelectionUI();
  }
}


async function selectAlbum(a, uiKey=null){
  const token=++selectionSerial;
  selectedAlbum=a;
  if(uiKey) selectedUiKey=uiKey;
  else if(!selectedUiKey || !selectedUiKey.startsWith('album')) selectedUiKey=selectionKey('album', a, selectedArtist || '');
  syncSingleSelectionUI();

  let url=API+'/tracks?album='+encodeURIComponent(a);
  if(selectedArtist) url+='&artist='+encodeURIComponent(selectedArtist);
  let t=await j(url);
  if(token!==selectionSerial) return;
  selectedTracks.clear();
  tracks.innerHTML=t.map(x=>`<tr><td><input type="checkbox" class="trackPick" data-path="${escHtml(relPath(x.path))}" data-title="${escHtml(x.title)}"></td><td>${trackNo(x)}</td><td>${escHtml(x.title)}<br><span class="small">${escHtml(relPath(x.path))}</span></td><td class="right">${fmt(x.input_i,1)}</td><td class="right">${fmt(x.input_tp,1)}</td><td class="right">${fmt(x.input_lra,1)}</td><td class="right">${x.bitrate?Math.round(x.bitrate/1000):''}</td><td>${escHtml(x.codec)}</td></tr>`).join('');
  document.querySelectorAll('.trackPick').forEach(cb=>{cb.onchange=()=>toggleTrack(cb.dataset.path, cb.dataset.title || cb.dataset.path, cb.checked)});
  updateTrackSelectionUI();

  let anUrl=API+'/album_analysis?album='+encodeURIComponent(a);
  if(selectedArtist) anUrl+='&artist='+encodeURIComponent(selectedArtist);
  let an=await j(anUrl);
  if(token!==selectionSerial) return;
  selectedAlbumAnalysis=an;
  albumSummary.textContent=`${an.tracks} Titel · ${an.analyzed} analysiert · Ø ${an.avg_lufs??'-'} LUFS · TP ${an.max_true_peak??'-'} · LRA ${an.avg_lra??'-'}`;

  btnRef.disabled=false;
  btnAnalyze.disabled=false;
  updateNormalizeGuard();
  syncSingleSelectionUI();
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

async function chooseNormalizeTargetSource(){
  // v1.9.39: Kein Browser-Prompt mehr.
  // „Alles normalisieren“ verwendet immer die Werte aus den Einstellungen.
  // Soll ein Referenzalbum als Ziel dienen, vorher bewusst „Ziel-LUFS übernehmen“ klicken.
  return 'settings';
}

async function normalizeAll(){
  try{
    const targetSource='settings';
    lastRunning=true;
    status.textContent='Alles-Normalisierung: Vorschau wird erstellt...';
    if(progressText) progressText.textContent='Normalisierung vorbereiten...';

    const pv=await j(API+'/normalize_preview_all?target_source=settings');
    if(!pv.can_normalize){
      status.textContent='Alles-Normalisierung nicht möglich';
      alert('Alles normalisieren ist aktuell nicht möglich:\n\nEs gibt keine vollständig analysierten Alben, die normalisiert werden können.');
      await poll();
      return;
    }

    const backupText = backupMode.value==='off' ? 'kein Backup' : (backupMode.value==='sidecar' ? '.bak neben der Datei' : 'Backup unter /data/backups');
    const sourceText = 'Werte aus Einstellungen';
    const examples=(pv.normalizable||[]).slice(0,8).map(x=>`- ${x.label}: ${x.current_lufs} → ${x.target_lufs} LUFS`).join('\n');
    const more=(pv.count_albums||0)>8 ? `\n... und ${(pv.count_albums||0)-8} weitere` : '';
    const skipped=[];
    if(pv.count_blocked) skipped.push(`${pv.count_blocked} Album/Alben werden übersprungen, weil sie noch nicht vollständig analysiert sind`);
    if(pv.count_skipped_reference) skipped.push(`${pv.count_skipped_reference} Referenzalbum/Alben werden übersprungen`);
    const msg=`Alles normalisieren starten?\n\n${pv.count_albums} Album/Alben · ${pv.count_tracks} Titel\nQuelle: ${sourceText}\nZiel: ${pv.target_lufs} LUFS · TP ${pv.true_peak} · LRA ${pv.lra}\nBackup: ${backupText}\n\n${examples}${more}${skipped.length?'\n\n'+skipped.join('\n'):''}\n\nDateien werden überschrieben.`;
    if(!confirm(msg)){
      status.textContent='Alles-Normalisierung abgebrochen';
      await poll();
      return;
    }

    status.textContent='Alles-Normalisierung wird gestartet...';
    if(progressText) progressText.textContent='Normalisierung wird gestartet...';
    await j(API+'/normalize_all',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({backup:backupMode.value,target_source:'settings'})});
    setTimeout(poll, 250);
    setTimeout(poll, 1000);
    setTimeout(poll, 3000);
  }catch(e){
    lastRunning=false;
    status.textContent='Alles-Normalisierung-Fehler';
    alert('Alles normalisieren konnte nicht gestartet werden:\n'+e.message);
    try{ await poll(); }catch(_){}
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
      const status=x.skip_reference ? `übersprungen: ${x.reason||'Referenzalbum'}` : (x.can_normalize ? `${x.current_lufs} → ${x.target_lufs} LUFS (${delta} dB)` : `gesperrt: ${x.reason||'nicht möglich'}`);
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

let lastLibraryCheck=null;
function renderIssueGroup(title, items){
  if(!items || !items.length) return '';
  const rows=items.slice(0,6).map(x=>`<div class="checkPath">${escHtml(x.path||x.title||'')}</div>`).join('');
  const more=items.length>6?`<div class="small muted">… ${items.length-6} weitere</div>`:'';
  return `<div class="checkItem"><b>${escHtml(title)}</b>${rows}${more}</div>`;
}
function jsArg(v){return JSON.stringify(String(v??''));}
function renderPathRow(x){
  const path=String(x?.path||'');
  if(!path) return '';
  // v1.9.39: Auf der Duplikatseite keine Pfad-Buttons mehr.
  // Direktes Öffnen/Kopieren war im Browser/NAS-Setup nicht zuverlässig genug
  // und hat die Seite unnötig überladen. Der Pfad bleibt nur als Hinweis sichtbar.
  return `<div class="checkPathRow"><div class="checkPath">${escHtml(path)}</div></div>`;
}


function itemPaths(item){
  if(!item) return [];
  if(Array.isArray(item.items)) return item.items.map(x=>String(x?.path||x||'')).filter(Boolean);
  if(item.path) return [String(item.path)];
  return [];
}
function renderCheckList(el, items, emptyText, opts={}){
  if(!el) return;
  if(!Array.isArray(items) || !items.length){
    el.innerHTML=`<div class="muted">${escHtml(emptyText||'Keine Einträge gefunden.')}</div>`;
    return;
  }
  el.innerHTML=items.slice(0,80).map((item,idx)=>{
    const title=item.title || item.name || item.album || item.artist || ('Treffer '+(idx+1));
    const artist=item.artist ? `<span>${escHtml(item.artist)}</span>` : '';
    const album=item.album ? `<span>${escHtml(item.album)}</span>` : '';
    const score=(item.score!==undefined && item.score!==null) ? `<span>${Math.round(Number(item.score)*100)}%</span>` : '';
    const paths=itemPaths(item);
    const rows=paths.length ? paths.map(p=>renderPathRow({path:p})).join('') : renderPathRow(item);
    const confirmBtn=(opts.confirmFalseDuplicate && paths.length>=2)
      ? `<button class="miniBtn danger" onclick='confirmNonDuplicate(${JSON.stringify(paths).replace(/'/g,"&#39;")}, ${JSON.stringify(title).replace(/'/g,"&#39;")});event.stopPropagation();'>Kein Duplikat bestätigen</button>`
      : '';
    return `<div class="checkItem"><div class="checkItemHead"><b>${escHtml(title)}</b><div class="checkMeta">${artist}${album}${score}</div></div>${rows}<div class="checkPathActions footerActions">${confirmBtn}</div></div>`;
  }).join('') + (items.length>80 ? `<div class="small muted">… ${items.length-80} weitere Einträge</div>` : '');
}

async function copyText(text, label='Text'){
  try{
    await navigator.clipboard.writeText(text);
    const statusEl=document.getElementById('checkStatus');
    if(statusEl) statusEl.textContent=label+' kopiert: '+text;
    return true;
  }catch(e){
    prompt(label+' manuell kopieren:', text);
    return false;
  }
}

async function copyMusicPath(path){
  try{
    const info=await j(API+'/path_info?path='+encodeURIComponent(path));
    const text=info.container_path || path;
    await copyText(text, 'Container-Pfad');
  }catch(e){
    await copyText(path, 'Pfad');
  }
}

async function copySmbPath(path){
  try{
    const info=await j(API+'/path_info?path='+encodeURIComponent(path));
    await copyText(info.folder_smb_url || info.file_smb_url || path, 'SMB-Link');
  }catch(e){
    alert('SMB-Link konnte nicht erzeugt werden:\n'+e.message);
  }
}

async function copyFinderOpenCommand(path){
  try{
    const info=await j(API+'/path_info?path='+encodeURIComponent(path));
    await copyText(info.finder_open_folder_command || ('open "'+(info.folder_smb_url||path)+'"'), 'Finder-Befehl');
  }catch(e){
    alert('Finder-Befehl konnte nicht erzeugt werden:\n'+e.message);
  }
}

async function openMusicPath(path){
  try{
    const info=await j(API+'/path_info?path='+encodeURIComponent(path));
    const url=info.folder_smb_url || info.file_smb_url;
    const statusEl=document.getElementById('checkStatus');
    if(statusEl) statusEl.textContent='Versuche zu öffnen: '+url+' · Falls nichts passiert: „Finder-Befehl kopieren“ nutzen.';
    try{ await navigator.clipboard.writeText(info.finder_open_folder_command || ('open "'+url+'"')); }catch(_e){}
    const a=document.createElement('a');
    a.href=url;
    a.target='_self';
    a.rel='noreferrer';
    document.body.appendChild(a);
    a.click();
    setTimeout(()=>a.remove(),500);
  }catch(e){
    alert('Pfad konnte nicht geöffnet werden:\n'+path+'\n\n'+e.message);
  }
}

async function showOpenPathHelp(path){
  try{
    const info=await j(API+'/path_info?path='+encodeURIComponent(path));
    const msg=[
      'Direktes Öffnen kann Safari/Chrome blockieren. Sicher funktioniert der Finder-Befehl im Terminal.',
      '',
      'SMB-Ordner:', info.folder_smb_url || '-',
      '',
      'Finder-Befehl:', info.finder_open_folder_command || '-',
      '',
      'Container-Pfad:', info.container_path || path
    ].join('\n');
    const openNow=confirm(msg+'\n\nJetzt trotzdem per Browser öffnen?');
    if(openNow) await openMusicPath(path);
    else await copyText(info.finder_open_folder_command || info.folder_smb_url || path, 'Finder-Befehl');
  }catch(e){
    alert('Pfad-Infos konnten nicht erzeugt werden:\n'+e.message);
  }
}


async function confirmNonDuplicate(paths, title){
  if(!Array.isArray(paths) || paths.length<2) return;
  const msg=`Diese Treffer künftig ausblenden?\n\n${title}\n\n${paths.slice(0,2).join('\n')}`;
  if(!confirm(msg)) return;
  const statusEl=document.getElementById('checkStatus');
  try{
    await j(API+'/duplicates/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({paths:paths.slice(0,2), reason:'Benutzerbestätigung: kein Duplikat'})});
    if(statusEl) statusEl.textContent='Als kein Duplikat bestätigt. Prüfung wird aktualisiert…';
    await runLibraryCheck(true);
  }catch(e){
    alert('Bestätigung konnte nicht gespeichert werden:\n'+e.message);
  }
}
async function runLibraryCheck(force=true){
  const statusEl=document.getElementById('checkStatus');
  const btn=document.getElementById('btnRunCheck');
  try{
    if(btn){btn.disabled=true; btn.textContent='Prüfe…';}
    if(statusEl) statusEl.textContent='Duplikatprüfung läuft…';

    // v1.8.6: zuerst dedizierten Duplikat-Endpunkt nutzen, Fallback bleibt library_check.
    let res;
    try{
      res=await j(API+'/duplicates?threshold=0.90');
    }catch(_e){
      res=await j(API+'/library_check?threshold=0.90');
    }
    lastLibraryCheck=res;
    const real=res.real_duplicates || res.duplicates || [];
    const repeated=res.repeated_titles || [];
    const conflicts=res.file_conflicts || [];

    const realEl=document.getElementById('checkRealDupes'); if(realEl) realEl.textContent=real.length||0;
    const repEl=document.getElementById('checkRepeatedTitles'); if(repEl) repEl.textContent=repeated.length||0;
    const conEl=document.getElementById('checkConflicts'); if(conEl) conEl.textContent=conflicts.length||0;
    const missing=(res.missing_year?.count||0)+(res.missing_genre?.count||0)+(res.missing_cover?.count||0)+(res.broken_files?.length||0);
    const metaEl=document.getElementById('checkMissingMeta'); if(metaEl) metaEl.textContent=missing;

    renderCheckList(document.getElementById('realDuplicates'), real, 'Keine Duplikate gefunden. Regel: gleicher Interpret + gleiches Album + mindestens 90 % ähnlicher Titel.', {confirmFalseDuplicate:true});
    renderCheckList(document.getElementById('repeatedTitles'), repeated, 'Keine mehrfach vorhandenen Titel auf verschiedenen Alben gefunden.');
    renderCheckList(document.getElementById('fileConflicts'), conflicts, 'Keine Dateikonflikte nach Sortierung gefunden.');
    const meta=[];
    if(res.missing_year?.count) meta.push({title:`Fehlendes Jahr: ${res.missing_year.count}`, items:res.missing_year.examples||[]});
    if(res.missing_genre?.count) meta.push({title:`Fehlendes Genre: ${res.missing_genre.count}`, items:res.missing_genre.examples||[]});
    if(res.missing_cover?.count) meta.push({title:`Fehlende Cover: ${res.missing_cover.count}`, items:res.missing_cover.examples||[]});
    if(res.broken_files?.length) meta.push({title:`Beschädigte/nicht lesbare Dateien: ${res.broken_files.length}`, items:res.broken_files});
    const mbox=document.getElementById('metadataIssues');
    if(mbox) mbox.innerHTML=meta.length?meta.map(g=>renderIssueGroup(g.title,g.items)).join(''):'<div class="muted">Keine relevanten Metadatenprobleme gefunden.</div>';
    if(statusEl) statusEl.textContent=`Geprüft: ${res.tracks||0} Titel · Toleranz ${res.threshold_percent||90}% · ${real.length||0} Duplikatgruppe(n) · ${res.confirmed_false_duplicates||0} bestätigt ausgeblendet`;
  }catch(e){
    if(statusEl) statusEl.textContent='Duplikatprüfung fehlgeschlagen: '+e.message;
    alert('Duplikatprüfung fehlgeschlagen:\n'+e.message);
  }finally{
    if(btn){btn.disabled=false; btn.textContent='Duplikate suchen';}
  }
}

function exportLibraryCheck(){
  const a=document.createElement('a');
  a.href=API+'/library_check/export';
  a.download='musiclab_bibliothekspruefung.csv';
  document.body.appendChild(a);a.click();a.remove();
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

function logLineTimeKey(line, idx){
  const m=String(line||'').match(/^(\d{1,2}):(\d{2}):(\d{2})/);
  if(!m) return {t: 999999 + idx/1000000, idx};
  return {t: Number(m[1])*3600 + Number(m[2])*60 + Number(m[3]) + idx/1000000, idx};
}

function filterLogLine(line, filter){
  const s=String(line||'').toLowerCase();
  if(!filter || filter==='all') return true;
  if(filter==='error') return s.includes('fehler') || s.includes('error') || s.includes('fehlgeschlagen') || s.includes('abgebrochen');
  if(filter==='scan') return s.includes('scan');
  if(filter==='tags') return s.includes('tag') || s.includes('cover') || s.includes('verschoben') || s.includes('sortier');
  if(filter==='audio') return s.includes('analyse') || s.includes('normalisierung') || s.includes('normalisiert') || s.includes('referenz');
  if(filter==='sort') return s.includes('sortier') || s.includes('verschoben');
  return true;
}

async function loadLog(){
  try{
    const box=document.getElementById('logBox');
    const auto=document.getElementById('protocolAutoscroll');
    const keepTop=box?box.scrollTop:0;
    const wasNearBottom=box ? (box.scrollTop + box.clientHeight >= box.scrollHeight - 12) : true;
    let l=await j(API+'/log');
    const raw=[...(l.lines||[]), ...(l.errors||[])];
    const seen=new Set();
    let lines=[];
    raw.forEach((line,idx)=>{
      const key=String(line||'');
      if(!key || seen.has(key)) return;
      seen.add(key);
      lines.push({line:key, ...logLineTimeKey(key, idx)});
    });
    lines.sort((a,b)=>a.t-b.t || a.idx-b.idx);
    const filter=(box?.dataset?.filter)||'all';
    const shown=lines.map(x=>x.line).filter(line=>filterLogLine(line, filter)).slice(-200);
    if(box){
      box.textContent=shown.length ? shown.join('\n') : 'Noch kein Log.';
      if(auto?.checked && wasNearBottom){
        box.scrollTop=box.scrollHeight;
      }else{
        box.scrollTop=keepTop;
      }
    }
  }catch(e){}
}


function setProtocolFilter(kind){
  document.querySelectorAll('.filterPills button').forEach(b=>{
    const label=(b.textContent||'').trim().toLowerCase();
    const active=(kind==='all' && label==='alle') ||
      (kind==='error' && label==='fehler') ||
      (kind==='scan' && label==='scan') ||
      (kind==='tags' && label==='tags') ||
      (kind==='audio' && label==='audio') ||
      (kind==='sort' && label==='sortierung');
    b.classList.toggle('active', active);
  });
  const box=document.getElementById('logBox');
  if(!box)return;
  box.dataset.filter=kind;
  loadLog();
}


document.addEventListener('DOMContentLoaded',()=>{document.getElementById('settingsModal')?.classList.add('hidden')});
let currentView='dashboard';
function setAppView(view){
  currentView=view;
  updateViewportMetrics();
  document.querySelectorAll('.appView').forEach(el=>el.classList.toggle('active', el.id===view+'View'));
  [['tabDashboard','dashboard'],['tabAudio','audio'],['tabTags','tags'],['tabMedia','media'],['tabCheck','check'],['tabProtocol','protocol'],['tabSettings','settings']].forEach(([id,v])=>{const b=document.getElementById(id); if(b)b.classList.toggle('active', view===v)});
  document.body.classList.toggle('settingsMode', view==='settings');
  document.body.classList.toggle('audioMode', view==='audio');
  document.body.classList.toggle('mediaMode', view==='media');
  document.body.classList.toggle('dashboardMode', view==='dashboard');
  document.body.classList.toggle('protocolMode', view==='protocol');
  document.body.classList.toggle('checkMode', view==='check');
  if(view==='dashboard'){
    updateBrowserTabsForView();
    loadDashboard();
  }else if(view==='tags'){
    // Tags arbeitet mit einem Suchtyp-Dropdown. Standard ist Album.
    if(!['artist','album','genre','year','issues'].includes(browserMode)) browserMode='album';
    const tagSelect=document.getElementById('tagSearchType');
    if(tagSelect) tagSelect.value=browserMode;
    resetTagFilters();
    selectedAlbum=null;
    selectedTagFolder=null;
    selectedUiKey=null;
    updateBrowserTabsForView();
    loadBrowser();
    loadTagsPage();
  }else if(view==='audio'){
    if(browserMode==='genre' || browserMode==='year') browserMode='artist';
    updateBrowserTabsForView();
    setBrowserMode(browserMode);
  }else if(view==='media'){
    updateBrowserTabsForView();
    loadMediaPage();
  }else if(view==='check'){
    updateBrowserTabsForView();
    runLibraryCheck(false);
  }else if(view==='protocol'){
    updateBrowserTabsForView();
    loadLog();
    loadHistory();
  }else{
    updateBrowserTabsForView();
  }
  if(view==='settings'){ syncSettingsPageFromMain(); checkMusicRootPage(); }
}
function openSettings(){setAppView('settings')}
function closeSettings(){document.getElementById('settingsModal')?.classList.add('hidden');setAppView(currentView==='settings'?'dashboard':currentView)}
function syncSettingsPageFromMain(){
  const pairs=[['targetLufs','targetLufsPage'],['truePeak','truePeakPage'],['lra','lraPage'],['backupMode','backupModePage'],['parallelAnalysis','parallelAnalysisPage'],['parallelNormalize','parallelNormalizePage'],['musicRoot','musicRootPage'],['watchMode','watchModePage'],['sortAfterTags','sortAfterTagsPage'],['smbBaseUrl','smbBaseUrlPage']];
  for(const [a,b] of pairs){const x=document.getElementById(a), y=document.getElementById(b); if(x&&y)y.value=x.value;}
}
function syncSettingsMainFromPage(){
  const pairs=[['targetLufs','targetLufsPage'],['truePeak','truePeakPage'],['lra','lraPage'],['backupMode','backupModePage'],['parallelAnalysis','parallelAnalysisPage'],['parallelNormalize','parallelNormalizePage'],['musicRoot','musicRootPage'],['watchMode','watchModePage'],['sortAfterTags','sortAfterTagsPage'],['smbBaseUrl','smbBaseUrlPage']];
  for(const [a,b] of pairs){const x=document.getElementById(a), y=document.getElementById(b); if(x&&y)x.value=y.value;}
}
function downloadSortPreviewExport(){
  window.open(API+'/library/sort_preview_export','_blank');
}
async function sortLibraryByTags(){
  try{
    const preview=await j(API+'/library/sort_preview');
    if(!preview.move_count){ alert('Die Bibliothek ist bereits nach den aktuellen Tags sortiert.'); return; }
    const groups=(preview.groups||[]).slice(0,8).map(x=>`• ${x.artist||'Unbekannter Interpret'} – ${x.album||'Unbekanntes Album'}\n  ${x.count} Dateien`).join('\n');
    const msg=`Bibliothek neu sortieren?\n\n${preview.move_count} Dateien würden verschoben\n${preview.conflicts||0} Konflikte\n${preview.skipped||0} übersprungen\n\nGrößte Gruppen:\n${groups||'-'}\n\nEine vollständige Detail-Liste kannst du danach/jetzt über „Sortier-Vorschau exportieren“ herunterladen.\n\nJetzt sortieren?`;
    if(!confirm(msg)) return;
    const res=await j(API+'/library/sort',{method:'POST'});
    if(res && res.error){ alert(res.error); return; }
    const spText=document.getElementById('sortProgressText');
    if(spText) spText.textContent='Sortierung wird gestartet…';
    poll();
  }catch(e){alert('Bibliothek konnte nicht sortiert werden:\n'+(e && e.message ? e.message : e));}
}

let folderPickerCurrent='/music';
async function openFolderPicker(){
  const current=(document.getElementById('musicRootPage')?.value||document.getElementById('musicRoot')?.value||'/music').trim()||'/music';
  folderPickerCurrent=current;
  document.getElementById('folderPickerModal')?.classList.remove('hidden');
  await loadFolderPicker(current);
}
function closeFolderPicker(){ document.getElementById('folderPickerModal')?.classList.add('hidden'); }
async function loadFolderPicker(path){
  try{
    const data=await j(API+'/fs/browse?path='+encodeURIComponent(path||'/'));
    folderPickerCurrent=data.path||path||'/';
    const p=document.getElementById('folderPickerPath'); if(p)p.textContent=folderPickerCurrent;
    const list=document.getElementById('folderPickerList'); if(!list)return;
    list.innerHTML=(data.dirs||[]).map(d=>`<button class="folderItem" onclick="loadFolderPicker('${esc(d.path)}')">📁 ${esc(d.name)}</button>`).join('') || '<div class="empty">Keine Unterordner gefunden.</div>';
  }catch(e){
    const list=document.getElementById('folderPickerList'); if(list)list.innerHTML='<div class="empty">Ordner konnte nicht geladen werden: '+esc(e.message)+'</div>';
  }
}
async function browseParentFolder(){
  const parts=folderPickerCurrent.split('/').filter(Boolean);
  const parent='/' + parts.slice(0,-1).join('/');
  await loadFolderPicker(parent==='/'?'/':parent);
}
function usePickedFolder(){
  const a=document.getElementById('musicRootPage'); const b=document.getElementById('musicRoot');
  if(a)a.value=folderPickerCurrent; if(b)b.value=folderPickerCurrent;
  closeFolderPicker();
  checkMusicRootPage?.();
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


function setTagsDirty(dirty=true){
  tagsDirty=!!dirty;
  const btn=document.getElementById('btnApplyTagChanges');
  if(btn){ btn.disabled=!tagsDirty; btn.classList.toggle('primaryPulse', tagsDirty); }
  const info=document.getElementById('tagDirtyInfo');
  if(info){ info.textContent=tagsDirty?'Ungespeicherte Änderungen':'Keine Änderungen'; info.className='small '+(tagsDirty?'warnText':'muted'); }
}
function bindTagDirtyHandlers(){
  ['tagAlbumArtist','tagAlbumName','tagYear','tagGenre','tagTrackTotal','tagDiscTotal'].forEach(id=>{
    const el=document.getElementById(id); if(el) el.oninput=()=>{ if(id==='tagTrackTotal')syncTrackTotalPreview(); if(id==='tagDiscTotal')syncDiscTotalPreview(); setTagsDirty(true); };
  });
  document.querySelectorAll('#tagTracks input, #tagDiscTotalsBox input').forEach(el=>{
    const old=el.getAttribute('oninput')||'';
    el.oninput=()=>{ if(old.includes('syncTrackTotalPreview'))syncTrackTotalPreview(); setTagsDirty(true); };
  });
}
function setupCoverDrop(){
  const drop=document.getElementById('tagCoverDrop');
  const inp=document.getElementById('tagCoverInput');
  if(!drop || !inp) return;
  ['dragenter','dragover'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();drop.classList.add('dragover');}));
  ['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();e.stopPropagation();drop.classList.remove('dragover');}));
  drop.ondrop=(e)=>{
    const f=e.dataTransfer?.files?.[0];
    if(!f) return;
    if(!/^image\//.test(f.type||'')){ alert('Bitte eine Bilddatei verwenden.'); return; }
    const dt=new DataTransfer(); dt.items.add(f); inp.files=dt.files; uploadTagCover();
  };
}
async function applyTagChanges(){
  const rows=[...document.querySelectorAll('#tagTracks tr[data-path]')];
  if(!rows.length){alert('Kein Album ausgewählt.');return;}
  const artist=document.getElementById('tagAlbumArtist')?.value||'';
  const album=document.getElementById('tagAlbumName')?.value||'';
  const year=document.getElementById('tagYear')?.value||'';
  const genre=document.getElementById('tagGenre')?.value||'';
  const total=(document.getElementById('tagTrackTotal')?.value||'').trim();
  const discTotal=(document.getElementById('tagDiscTotal')?.value||'').trim();
  const updates=rows.map(r=>{
    const raw=(r.querySelector('.tagTrack')?.value||'').trim();
    const num=raw.split('/')[0].trim();
    const discRaw=(r.querySelector('.tagDisc')?.value||'').trim();
    const discTotalNum = parseInt(discTotal,10);
    const discNum=discTotalNum>1 ? (discRaw.split('/')[0].trim() || '1') : '';
    const perDiscTotal = discNum ? discTotalFor(discNum, total) : total;
    const tracknumber = num ? (perDiscTotal ? `${num}/${perDiscTotal}` : num) : '';
    const discnumber = (discTotalNum && discTotalNum>1 && discNum) ? `${discNum}/${discTotalNum}` : '';
    const rowArtist=(r.querySelector('.tagArtist')?.value||'').trim();
    const origArtist=(r.dataset.origArtist||'').trim();
    const finalArtist = (rowArtist && rowArtist !== origArtist) ? rowArtist : artist;
    return {
      path:r.dataset.path,
      title:r.querySelector('.tagTitle')?.value||'',
      artist:finalArtist,
      album, year, genre,
      tracknumber, discnumber
    };
  });
  await saveTagUpdates(updates, 'Änderungen übernommen.', {album});
}

async function getTagTrackUrl(){
  if(selectedTagFolder!==null && selectedTagFolder!==undefined){
    let url=API+'/tracks_by_folder?folder='+encodeURIComponent(selectedTagFolder);
    // Preserve the current browser context. This prevents e.g. "Unbekanntes Album"
    // from expanding to every artist when it was opened from "Albumordner von ASP".
    const rawQ=(search.value||'').trim();
    if(selectedArtist) url+='&artist='+encodeURIComponent(selectedArtist);
    if(selectedTagGenre) url+='&genre='+encodeURIComponent(selectedTagGenre);
    if(selectedTagYear) url+='&year='+encodeURIComponent(selectedTagYear);
    if(rawQ) url+='&q='+encodeURIComponent(rawQ);
    return {url, useArtist:selectedArtist||null, byFolder:true};
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

function clearTagForm(){
  ['tagAlbumArtist','tagAlbumName','tagYear','tagGenre','tagTrackTotal','tagDiscTotal'].forEach(id=>{const el=document.getElementById(id); if(el){el.value=''; el.disabled=false;}});
  const box=document.getElementById('tagDiscTotalsBox'); if(box){box.innerHTML=''; box.style.display='none';}
  const b=document.getElementById('btnTagScraper'); if(b)b.disabled=true;
}

async function loadTagsPage(){
  const body=document.getElementById('tagTracks'); const hint=document.getElementById('tagHint');
  if(!body||!hint)return;
  // v1.9.39: Beim Albumwechsel sofort die alte Vorschau entfernen.
  // Sonst bleibt bei langsamer/fehlender Cover-Antwort das zuletzt gesehene Cover stehen.
  tagCoverPlaceholder('Cover wird geladen…');
  if(!selectedAlbum && selectedTagFolder===null){
    hint.textContent = selectedArtist ? 'Bitte links ein Album von '+selectedArtist+' auswählen.' : 'Noch kein Album ausgewählt.';
    body.innerHTML='';
    clearTagForm();
    tagCoverPlaceholder('Noch kein Album ausgewählt.');
    setTagsDirty(false);
    setupCoverDrop();
    return;
  }
  try{
    const {url, useArtist, byFolder}=await getTagTrackUrl();
    const rows=await j(url);
    hint.textContent=`${byFolder?'Ordner · ':''}${useArtist?useArtist+' · ':''}${selectedAlbum} · ${rows.length} Titel`;
    tagDiscTotals={};
    if(rows.length){
      const bs=document.getElementById('btnTagScraper'); if(bs) bs.disabled=false;
      const first=rows[0];
      const cp=document.getElementById('tagCoverPreview'); const ci=document.getElementById('tagCoverInfo');
      if(cp){ cp.outerHTML = tagCoverBox(coverUrlPath(first.path||'')); }
      if(ci) ci.textContent = 'Cover wird in die sichtbaren Audiodateien dieses Albums eingebettet.';
      const aa=document.getElementById('tagAlbumArtist'), al=document.getElementById('tagAlbumName'), tt=document.getElementById('tagTrackTotal'), dt=document.getElementById('tagDiscTotal'), yr=document.getElementById('tagYear'), ge=document.getElementById('tagGenre');
      const artists=[...new Set(rows.map(r=>r.artist||'').filter(Boolean))];
      const albums=[...new Set(rows.map(r=>r.album||'').filter(Boolean))];
      if(aa)aa.value=artists.length===1 ? artists[0] : '';
      if(al)al.value=byFolder ? (selectedAlbum||first.album||'') : (albums.length===1 ? albums[0] : (selectedAlbum||''));
      const discNums=[...new Set(rows.map(r=>Number(r.disc_number||parseInt(String(r.disc_raw||'').split('/')[0],10)||1)).filter(n=>n>0))].sort((a,b)=>a-b);
      const discTotalsExisting=rows.map(r=>Number(r.disc_total||0)).filter(n=>n>0);
      let discTotalCount=discTotalsExisting.length ? Math.max(...discTotalsExisting) : (discNums.length>1 ? discNums.length : '');
      if(Number(discTotalCount)<=1) discTotalCount='';
      if(dt)dt.value=discTotalCount;
      if(tt){
        if(discNums.length>1){
          tt.value='';
          tt.placeholder='je Disc unten';
          tt.disabled=true;
        }else{
          tt.disabled=false;
          tt.placeholder='z. B. 10';
          tt.value=rows.length;
        }
      }
      for(const d of discNums){
        const rowsForDisc=rows.filter(r=>(Number(r.disc_number||parseInt(String(r.disc_raw||'').split('/')[0],10)||1)===d));
        const tagged=rowsForDisc.map(r=>Number(r.track_total||0)).filter(n=>n>0);
        tagDiscTotals[d]=tagged.length ? Math.max(...tagged) : rowsForDisc.length;
      }
      renderDiscTotalsEditor(discNums);
      if(yr){ const y=String(first.year||'').trim(); yr.value=(y==='0000'||y==='0')?'':y; }
      if(ge)ge.value=first.genre||'';
    } else {
      clearTagForm();
      tagCoverPlaceholder('Keine Titel in dieser Auswahl.');
      renderDiscTotalsEditor([]);
    }
    await loadGenreOptions();
    const singleTotalValue = document.getElementById('tagTrackTotal')?.value || (rows.length?String(rows.length):'');
    const discTotalValue = document.getElementById('tagDiscTotal')?.value || '';
    body.innerHTML=rows.map((x,i)=>{
      const trackNumber = x.track_number || parseInt(String(x.track_raw||'').split('/')[0],10) || (i+1);
      const rawDiscNumber = x.disc_number || parseInt(String(x.disc_raw||'').split('/')[0],10) || 1;
      const isMultiDisc = !!discTotalValue && Number(discTotalValue)>1;
      const discNumber = isMultiDisc ? rawDiscNumber : '';
      const totalValue = (isMultiDisc ? (tagDiscTotals[rawDiscNumber] || '') : (singleTotalValue || rows.length || ''));
      return `<tr data-path="${escAttr(relPath(x.path))}" data-orig-title="${escAttr(x.title||'')}" data-orig-artist="${escAttr(x.artist||'')}" data-orig-track="${escAttr(trackNumber)}" data-orig-disc="${escAttr(discNumber)}"><td>${i+1}</td><td><input class="tagTitle" value="${escAttr(x.title||'')}"></td><td><input class="tagArtist" value="${escAttr(x.artist||'')}"></td><td><input class="tagTrack" value="${escAttr(trackNumber)}"></td><td class="tagTotalShow" data-disc="${escAttr(rawDiscNumber)}">${escHtml(totalValue)}</td><td><input class="tagDisc" value="${escAttr(discNumber)}" placeholder="" oninput="syncTrackTotalPreview()"></td><td class="tagDiscTotalShow">${escHtml(isMultiDisc ? discTotalValue : '-')}</td><td class="small" title="${escAttr(relPath(x.path))}">${escHtml(relPath(x.path))}</td></tr>`;
    }).join('');
    bindTagDirtyHandlers();
    setupCoverDrop();
    setTagsDirty(false);
  }catch(e){hint.textContent='Tags konnten nicht geladen werden: '+e.message; body.innerHTML=''; tagCoverPlaceholder('Cover konnte nicht geladen werden.'); clearTagForm(); setTagsDirty(false);}
}
function escAttr(s){return String(s ?? '').replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;').replaceAll('>','&gt;')}
function renderDiscTotalsEditor(discs){
  const box=document.getElementById('tagDiscTotalsBox');
  if(!box) return;
  if(!discs || discs.length<=1){
    box.innerHTML='';
    box.style.display='none';
    return;
  }
  box.style.display='grid';
  box.innerHTML='<label>Tracks pro Disc</label><div class="discTotalsGrid">'+discs.map(d=>`<span>Disc ${d}</span><input data-disc-total="${d}" value="${escAttr(tagDiscTotals[d]||'')}" oninput="syncTrackTotalPreview()">`).join('')+'</div>';
}
function discTotalFor(d, fallback=''){
  const input=document.querySelector(`[data-disc-total="${CSS.escape(String(d))}"]`);
  return (input?.value||tagDiscTotals[d]||fallback||'').toString().trim();
}
function syncTrackTotalPreview(){
  const single=(document.getElementById('tagTrackTotal')?.value||'').trim();
  document.querySelectorAll('.tagTotalShow').forEach(el=>{
    const d=(el.dataset.disc||'').trim();
    const total=d ? discTotalFor(d, single) : single;
    el.textContent=total||'-';
  });
}
function syncDiscTotalPreview(){
  const total=(document.getElementById('tagDiscTotal')?.value||'').trim();
  document.querySelectorAll('.tagDiscTotalShow').forEach(el=>el.textContent=total||'-');
}

function visibleTagPaths(){
  return [...document.querySelectorAll('#tagTracks tr[data-path]')]
    .map(r=>r.dataset.path||'')
    .filter(Boolean);
}
function setTagCoverPreviewFromFile(file){
  const box=document.getElementById('tagCoverPreview');
  if(!box || !file) return null;
  const url=URL.createObjectURL(file);
  box.outerHTML=`<div id="tagCoverPreview" class="mediaCoverBox large tagCoverBox hasCover"><img src="${url}" alt=""></div>`;
  return url;
}

async function uploadTagCover(){
  const inp=document.getElementById('tagCoverInput');
  const f=inp?.files?.[0];
  if(!f){return;}

  const paths=visibleTagPaths();
  let folder=selectedTagFolder;
  const first=paths[0] || '';
  const firstFolder=parentFolderFromPath(first||'');

  if(firstFolder) folder=firstFolder;
  if((!folder || String(folder).startsWith('__album__:')) && !paths.length){
    alert('Bitte zuerst ein konkretes Album/einen Ordner auswählen.'); return;
  }

  const previewUrl=setTagCoverPreviewFromFile(f);
  try{
    setTagActionBusy(true, 'Cover wird gespeichert…');
    const data=await new Promise((resolve,reject)=>{
      const r=new FileReader();
      r.onload=()=>resolve(String(r.result||''));
      r.onerror=()=>reject(new Error('Datei konnte nicht gelesen werden'));
      r.readAsDataURL(f);
    });
    const payload={folder, paths, filename:f.name, content_type:f.type, data};
    const res=await j(API+'/tags/cover', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    coverCacheBust=Date.now();
    const folderFiles=(res.folder_files||[]).length;
    const verified=Number(res.verified||0);
    const msg=`Cover Apple-kompatibel gespeichert: ${res.updated}/${res.total} eingebettet · geprüft: ${verified}/${res.total}`+(folderFiles?` · Ordnercover: ${folderFiles}`:'')+(res.unsupported?` · nicht unterstützt: ${res.unsupported}`:'')+(res.errors?.length?` · Fehler: ${res.errors.length}`:'');
    progressText.textContent=msg;
    status.textContent=msg;
    const ci=document.getElementById('tagCoverInfo');
    if(ci) ci.textContent=msg;
    if(res.errors?.length || verified < Number(res.updated||0) || res.apple_compatible===false){
      alert(msg+(res.errors?.length?'\n'+res.errors.join('\n'):''));
    }
    try{
      const firstPath=(res.paths && res.paths[0]) || paths[0] || '';
      const cp=document.getElementById('tagCoverPreview');
      if(cp && firstPath){ cp.outerHTML = tagCoverBox(coverUrlPath(firstPath)); }
    }catch(_e){}
    if(currentView==='media') setTimeout(()=>loadMediaPage().catch(()=>{}), 300);
  }catch(e){
    coverCacheBust=Date.now();
    alert('Cover konnte nicht gespeichert werden: '+e.message);
  }
  finally{
    setTagActionBusy(false);
    if(previewUrl) setTimeout(()=>URL.revokeObjectURL(previewUrl), 15000);
    if(inp) inp.value='';
  }
}



function currentTagRows(){
  return [...document.querySelectorAll('#tagTracks tr[data-path]')];
}
function currentTagPaths(){
  return currentTagRows().map(r=>r.dataset.path).filter(Boolean);
}
function closeTagScraper(){
  const p=document.getElementById('tagScraperPanel'); if(p)p.classList.add('hidden');
}
function currentTagTrackData(){
  return currentTagRows().map((r,i)=>({
    index:i+1,
    path:r.dataset.path||'',
    title:r.querySelector('.tagTitle')?.value||r.dataset.origTitle||'',
    artist:r.querySelector('.tagArtist')?.value||r.dataset.origArtist||'',
    track:r.querySelector('.tagTrack')?.value||r.dataset.origTrack||'',
    disc:r.querySelector('.tagDisc')?.value||r.dataset.origDisc||''
  }));
}
function scraperNorm(s){
  return String(s||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
}
function scraperTitleMatch(a,b){
  a=scraperNorm(a); b=scraperNorm(b);
  if(!a&&!b)return 100;
  if(!a||!b)return 0;
  const m=a.length,n=b.length;
  const dp=Array.from({length:m+1},(_,i)=>[i]);
  for(let j=1;j<=n;j++)dp[0][j]=j;
  for(let i=1;i<=m;i++){
    for(let j=1;j<=n;j++){
      dp[i][j]=Math.min(dp[i-1][j]+1,dp[i][j-1]+1,dp[i-1][j-1]+(a[i-1]===b[j-1]?0:1));
    }
  }
  return Math.max(0, Math.round((1-dp[m][n]/Math.max(m,n))*100));
}
function renderTrackComparison(onlineTracks){
  const mine=currentTagTrackData();
  const online=onlineTracks||[];
  const max=Math.max(mine.length, online.length);
  if(!max)return '<div class="empty">Keine Trackdaten für den Vergleich vorhanden.</div>';
  const rows=[];
  for(let i=0;i<max;i++){
    const m=mine[i]||{};
    const o=online[i]||{};
    const oDisc=Number(o.disc_number||1);
    const oPos=o.position||o.number||'';
    const sim=(m.title||o.title)?scraperTitleMatch(m.title||'', o.title||''):0;
    const cls=sim>=90?'good':(sim>=70?'warn':'bad');
    rows.push(`<tr>
      <td class="small">${i+1}</td>
      <td><b>${escHtml(m.title||'—')}</b><br><span class="small muted">${escHtml(m.path||'')}</span></td>
      <td class="small">${escHtml(m.disc||'')} ${m.disc?'·':''} ${escHtml(m.track||'')}</td>
      <td><b>${escHtml(o.title||'—')}</b></td>
      <td class="small">${oDisc>1?'CD '+escHtml(oDisc)+' · ':''}${escHtml(oPos)}</td>
      <td><span class="matchPill ${cls}">${sim}%</span></td>
    </tr>`);
  }
  return `<details class="scraperCompare" open>
    <summary>Track-Vergleich: meine Dateien ↔ MusicBrainz</summary>
    <div class="small muted compareHint">Zum Abgleichen vor der Übernahme. „Titel übernehmen“ schreibt nur die sichtbaren Titel in der aktuellen Reihenfolge; Tracknummern/Reihenfolge bleiben unverändert.</div>
    <div class="scraperCompareTableWrap"><table class="scraperCompareTable">
      <thead><tr><th>#</th><th>Meine Tracks</th><th>Nr.</th><th>Gefundene Tracks</th><th>Nr.</th><th>Match</th></tr></thead>
      <tbody>${rows.join('')}</tbody>
    </table></div>
  </details>`;
}
function scraperTrackPreview(tracks){
  return renderTrackComparison(tracks||[]);
}
function renderTagScraperResults(data){
  const panel=document.getElementById('tagScraperPanel');
  const box=document.getElementById('tagScraperResults');
  const st=document.getElementById('tagScraperStatus');
  if(panel)panel.classList.remove('hidden');
  const proposals=data.proposals||[];
  if(st)st.textContent=`${proposals.length} Treffer für ${data.query?.artist||'-'} — ${data.query?.album||'-'}`;
  if(!box)return;
  if(!proposals.length){
    box.innerHTML='<div class="empty">Keine passenden Online-Tags gefunden.</div>';
    return;
  }
  box.innerHTML=proposals.map((p,i)=>{
    const score=Number(p.score||0);
    const scoreClass=score>=85?'good':(score>=65?'warn':'bad');
    const year=p.year||((p.date||'').slice(0,4));
    return `<div class="scraperCard">
      <div class="scraperCardHead">
        <div><h3>${escHtml(p.artist||'Unbekannt')} — ${escHtml(p.album||'Unbekanntes Album')}</h3>
        <div class="small muted">${escHtml(year||'ohne Jahr')}${p.country?' · '+escHtml(p.country):''}${p.status?' · '+escHtml(p.status):''} · ${p.track_count||0} Titel${p.medium_count>1?' · '+p.medium_count+' Discs':''}</div></div>
        <div class="scraperScore ${scoreClass}">${score}%</div>
      </div>
      <div class="scraperTracks">${scraperTrackPreview(p.tracks||[])}</div>
      <div class="small muted scraperSafetyNote">Sicherheitsmodus: Jahr/Cover ändern keine Titel. „Titel übernehmen“ schreibt nur Titel-Tags anhand dieser Gegenüberstellung; Tracknummern, Discnummern, Interpret, Album und Dateireihenfolge bleiben unverändert.</div>
      <div class="toolbar scraperActions">
        <button onclick="applyTagScraperProposal(${i}, 'year')">Nur Jahr übernehmen</button>
        <button onclick="applyTagScraperProposal(${i}, 'cover')">Nur Cover übernehmen</button>
        <button onclick="applyTagScraperProposal(${i}, 'year_cover')">Jahr + Cover übernehmen</button>
        <button class="secondary" onclick="applyTagScraperProposal(${i}, 'titles')">Titel übernehmen</button>
        ${p.source_url?`<button class="ghost" onclick="window.open('${escAttr(p.source_url)}','_blank')">MusicBrainz öffnen</button>`:''}
      </div>
    </div>`;
  }).join('');
  window.__tagScraperProposals=proposals;
  if(panel) panel.scrollIntoView({behavior:'smooth', block:'center'});
}
async function searchTagScraper(){
  const btn=document.getElementById('btnTagScraper');
  if(btn){btn.disabled=true; btn.textContent='Suche…';}
  const paths=currentTagPaths();
  const panel=document.getElementById('tagScraperPanel');
  const box=document.getElementById('tagScraperResults');
  const st=document.getElementById('tagScraperStatus');
  if(panel){panel.classList.remove('hidden'); panel.scrollIntoView({behavior:'smooth', block:'center'});}
  if(!paths.length){
    if(st)st.textContent='Kein Album ausgewählt';
    if(box)box.innerHTML='<div class="empty">Bitte links zuerst ein Album auswählen. Danach erscheinen hier die Online-Treffer.</div>';
    if(btn){btn.disabled=false; btn.textContent='Tags scrapen…';}
    return;
  }
  if(box)box.innerHTML='<div class="empty">Suche Online-Tags…</div>';
  if(st)st.textContent='Suche läuft…';
  const payload={
    folder:selectedTagFolder,
    paths,
    artist:document.getElementById('tagAlbumArtist')?.value||'',
    album:document.getElementById('tagAlbumName')?.value||''
  };
  try{
    const data=await j(API+'/tag_scraper/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    renderTagScraperResults(data);
  }catch(e){
    if(st)st.textContent='Suche fehlgeschlagen';
    if(box)box.innerHTML=`<div class="empty">Tag-Scraper fehlgeschlagen: ${escHtml(e.message||e)}</div>`;
  } finally {
    if(btn){btn.disabled=false; btn.textContent='Tags scrapen…';}
  }
}
async function applyTagScraperProposal(index, mode='year_cover'){
  const proposals=window.__tagScraperProposals||[];
  const proposal=proposals[index];
  const paths=currentTagPaths();
  if(!proposal || !paths.length)return;
  const year=proposal.year||((proposal.date||'').slice(0,4));
  const modeLabel={year:'Nur Jahr',cover:'Nur Cover',year_cover:'Jahr + Cover',titles:'Titel'}[mode]||'Jahr + Cover';
  const details=[];
  if(mode==='year' || mode==='year_cover') details.push(`Jahr: ${year||'nicht vorhanden'}`);
  if(mode==='cover' || mode==='year_cover') details.push('Cover: aus MusicBrainz/Cover Art Archive');
  if(mode==='titles') details.push(`Titel: ${Math.min(paths.length, (proposal.tracks||[]).length)} Online-Titel in der sichtbaren Reihenfolge`);
  const sortFiles=false;
  const warning = mode==='titles'
    ? 'Es werden NUR Titel-Tags überschrieben. Tracknummern, Discnummern, Interpret, Album, Dateinamen und Reihenfolge bleiben unverändert. Vorher bitte die Gegenüberstellung prüfen.'
    : 'Titel, Tracknummern, Discnummern, Interpret und Album werden NICHT überschrieben. Die angezeigte Trackliste ist nur eine Vorschau.';
  if(!confirm(`${modeLabel} übernehmen?\n\n${proposal.artist||'-'} — ${proposal.album||'-'}\n${details.join('\n')}\n${paths.length} sichtbare Dateien\n\nWichtig:\n${warning}`))return;
  const st=document.getElementById('tagScraperStatus');
  if(st)st.textContent=`Übernehme ${modeLabel}…`;
  try{
    const res=await j(API+'/tag_scraper/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:selectedTagFolder,paths,proposal,mode,sort_files:sortFiles})});
    const yearApplied=res.year_applied||0;
    const titlesApplied=res.titles_applied||0;
    const coverUpdated=res.cover?.updated||0;
    const coverVerified=res.cover?.verified||0;
    const errors=[...(res.result?.errors||[]), ...(res.cover?.errors||[])];
    const msg=`Scraper übernommen: Jahr ${yearApplied} · Titel ${titlesApplied} · Cover ${coverUpdated} · geprüft ${coverVerified}`+(errors.length?` · Fehler: ${errors.length}`:'');
    progressText.textContent=msg; status.textContent=msg;
    if(st)st.textContent=msg;
    if(errors.length) alert(msg+'\n'+errors.slice(0,10).join('\n'));
    scheduleLightRefresh(700);
    await loadTagsPage();
    setTagsDirty(false);
  }catch(e){
    if(st)st.textContent='Übernahme fehlgeschlagen';
    alert('Online-Daten konnten nicht übernommen werden: '+(e.message||e));
  }
}


async function saveAlbumTags(){
  const rows=[...document.querySelectorAll('#tagTracks tr[data-path]')];
  if(!rows.length){alert('Kein Album ausgewählt.');return;}
  const artist=document.getElementById('tagAlbumArtist')?.value||'';
  const album=document.getElementById('tagAlbumName')?.value||'';
  const year=document.getElementById('tagYear')?.value||'';
  const genre=document.getElementById('tagGenre')?.value||'';
  const total=(document.getElementById('tagTrackTotal')?.value||'').trim();
  const discTotal=(document.getElementById('tagDiscTotal')?.value||'').trim();
  const updates=rows.map(r=>{
    const raw=(r.querySelector('.tagTrack')?.value||'').trim();
    const num=raw.split('/')[0].trim();
    const discRaw=(r.querySelector('.tagDisc')?.value||'').trim();
    const discTotalNum = parseInt(discTotal,10);
    const discNum=discTotalNum>1 ? (discRaw.split('/')[0].trim() || '1') : '';
    const perDiscTotal = discNum ? discTotalFor(discNum, total) : total;
    const tracknumber = num ? (perDiscTotal ? `${num}/${perDiscTotal}` : num) : '';
    const discnumber = (discTotalNum && discTotalNum>1 && discNum) ? `${discNum}/${discTotalNum}` : '';
    return {path:r.dataset.path, artist, album, year, genre, tracknumber, discnumber};
  });
  await saveTagUpdates(updates, 'Album-Tags gespeichert.', {album});
}
async function saveTrackTags(){
  const rows=[...document.querySelectorAll('#tagTracks tr[data-path]')];
  if(!rows.length){alert('Keine Titel geladen.');return;}
  const total=(document.getElementById('tagTrackTotal')?.value||'').trim();
  const discTotal=(document.getElementById('tagDiscTotal')?.value||'').trim();
  const updates=rows.map(r=>{
    const raw=(r.querySelector('.tagTrack')?.value||'').trim();
    const num=raw.split('/')[0].trim();
    const discRaw=(r.querySelector('.tagDisc')?.value||'').trim();
    const discTotalNum = parseInt(discTotal,10);
    const discNum=discTotalNum>1 ? (discRaw.split('/')[0].trim() || '1') : '';
    const perDiscTotal = discNum ? discTotalFor(discNum, total) : total;
    const tracknumber = num ? (perDiscTotal ? `${num}/${perDiscTotal}` : num) : '';
    const discnumber = (discTotalNum && discTotalNum>1 && discNum) ? `${discNum}/${discTotalNum}` : '';
    return {path:r.dataset.path,title:r.querySelector('.tagTitle')?.value||'',artist:r.querySelector('.tagArtist')?.value||'',tracknumber,discnumber};
  });
  await saveTagUpdates(updates, 'Titel-Tags gespeichert.');
}
async function saveTagUpdates(updates, okMsg, opts={}){
  const wasTags=currentView==='tags';
  const keepFolder=selectedTagFolder;
  const keepAlbum=opts.album || selectedAlbum;
  const keepArtist=selectedArtist;
  const sortFiles=(document.getElementById('sortAfterTags')?.value==='on'||document.getElementById('sortAfterTagsPage')?.value==='on');
  try{
    setTagActionBusy(true, 'Tags werden gespeichert…');
    const res=await j(API+'/tags/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({updates,sort_files:sortFiles})});
    const msg = `${okMsg} Gespeichert: ${res.updated}/${res.total}` + (res.errors?.length ? ` · Fehler: ${res.errors.length}` : '');
    progressText.textContent = msg;
    status.textContent = msg;
    if(res.errors?.length) alert(`${okMsg}\nGespeichert: ${res.updated}/${res.total}\nFehler:\n${res.errors.join('\n')}`);
    if(opts.album) selectedAlbum=opts.album;
    setTagsDirty(false);

    // v1.9.39: Statistik/Genres werden verzögert aktualisiert, nicht blockierend.
    scheduleLightRefresh(900);

    if(sortFiles){
      // Wenn Dateien wirklich verschoben/umbenannt wurden, müssen Pfade neu geladen werden.
      selectedTagFolder=keepFolder;
      selectedAlbum=keepAlbum || selectedAlbum;
      selectedArtist=keepArtist;
      await loadBrowser();
      await loadTagsPage();
    }else if(wasTags){
      // Formular bleibt offen; kein kompletter Browser-Reload nach jedem Speichern.
      selectedTagFolder=keepFolder;
      selectedAlbum=keepAlbum || selectedAlbum;
      selectedArtist=keepArtist;
      syncSingleSelectionUI();
    }else{
      scheduleLightRefresh(300);
    }
  }catch(e){
    alert('Tags konnten nicht gespeichert werden:\n'+e.message)
  }finally{
    setTagActionBusy(false);
  }
}




async function loadMediaPage(){
  const artistsBox=document.getElementById('mediaArtists');
  const albumsBox=document.getElementById('mediaAlbums');
  const tracksBox=document.getElementById('mediaTracks');
  try{
    if(!mediaPageLoaded){
      [mediaArtistsCache,mediaAlbumsCache]=await Promise.all([
        j(API+'/media/artists?sort=artist'),
        j(API+'/media_albums')
      ]);
      mediaPageLoaded=true;
    }
    if(selectedMediaArtist && !mediaArtistsCache.some(x=>x.artist===selectedMediaArtist)){
      selectedMediaArtist=null; selectedMediaFolder=null; selectedMediaAlbum=null;
    }
    if(!selectedMediaArtist && mediaArtistsCache.length){
      selectedMediaArtist=mediaArtistsCache[0].artist;
    }
    renderMediaBrowser();
    await loadMediaAlbums('artist');
  }catch(e){
    if(artistsBox) artistsBox.innerHTML='<div class="empty">Medien konnten nicht geladen werden: '+escHtml(e.message)+'</div>';
    if(albumsBox) albumsBox.innerHTML='';
    if(tracksBox) tracksBox.innerHTML='';
  }
}

function invalidateMediaCaches(){
  mediaPageLoaded=false;
  mediaArtistAlbumsCache.clear();
}

function mediaBrowseMode(){ return document.getElementById('mediaBrowseMode')?.value || 'artist'; }

function switchMediaBrowseMode(){
  const inp=document.getElementById('mediaArtistSearch');
  if(inp){ inp.value=''; inp.placeholder = 'Suchen...'; }
  renderMediaBrowser();
}

function clearMediaArtistSearch(){
  const inp=document.getElementById('mediaArtistSearch');
  if(inp) inp.value='';
  renderMediaBrowser();
}

function renderMediaBrowser(){
  if(mediaBrowseMode()==='album') renderMediaAlbumBrowser();
  else renderMediaArtists();
}

function renderMediaArtists(){
  const artistsBox=document.getElementById('mediaArtists');
  if(!artistsBox)return;
  const inp=document.getElementById('mediaArtistSearch');
  if(inp) inp.placeholder='Suchen...';
  const q=(inp?.value||'').trim().toLowerCase();
  const list=mediaArtistsCache.filter(x=>!q || String(x.artist||'').toLowerCase().includes(q));
  artistsBox.innerHTML=list.map(x=>`<div class="row ${x.artist===selectedMediaArtist?'sel':''}" data-artist="${escAttr(x.artist)}"><b>${escHtml(x.artist)}</b>${browserRowBadges('artist','',x.artist)}<br><span class="small">${x.albums} Alben · ${x.tracks} Titel</span></div>`).join('') || '<div class="empty">Keine Interpreten gefunden.</div>';
  artistsBox.querySelectorAll('[data-artist]').forEach(el=>{el.onclick=()=>selectMediaArtist(el.dataset.artist);});
}

function renderMediaAlbumBrowser(){
  const box=document.getElementById('mediaArtists');
  if(!box)return;
  const inp=document.getElementById('mediaArtistSearch');
  if(inp) inp.placeholder='Suchen...';
  const q=(inp?.value||'').trim().toLowerCase();
  const list=mediaAlbumsCache.filter(x=>!q || [x.album,x.artist,x.folder].join(' ').toLowerCase().includes(q));
  box.innerHTML=list.map(x=>`<div class="row ${x.folder===selectedMediaFolder?'sel':''}" data-folder="${encodeURIComponent(x.folder||'')}" data-artist="${escAttr(x.artist||'')}" data-album="${encodeURIComponent(x.album||'')}"><b>${escHtml(x.album||'Unbekanntes Album')}</b><br><span class="small">${escHtml(x.artist||'')} · ${x.tracks} Titel</span></div>`).join('') || '<div class="empty">Keine Alben gefunden.</div>';
  box.querySelectorAll('[data-folder]').forEach(el=>{el.onclick=()=>selectMediaAlbumFromBrowser(decodeURIComponent(el.dataset.folder||''), el.dataset.artist||'', decodeURIComponent(el.dataset.album||''));});
}

async function selectMediaAlbumFromBrowser(folder, artist, album){
  selectedMediaArtist=artist;
  selectedMediaFolder=folder;
  selectedMediaAlbum=album;
  renderMediaBrowser();
  if(mediaBrowseMode()==='album') await loadMediaTracks();
  else await loadMediaAlbums('artist');
}

async function selectMediaArtist(artist){
  selectedMediaArtist=artist;
  selectedMediaFolder=null;
  selectedMediaAlbum=null;
  renderMediaBrowser();
  await loadMediaAlbums('artist');
}

async function loadMediaAlbums(sort){
  const albumsBox=document.getElementById('mediaAlbums');
  const tracksBox=document.getElementById('mediaTracks');
  const head=document.getElementById('mediaAlbumHead');
  const dl=document.getElementById('mediaDownload');
  if(!albumsBox || !selectedMediaArtist){
    if(albumsBox) albumsBox.innerHTML='<div class="empty">Bitte Interpret auswählen.</div>';
    return;
  }

  const cacheKey=(selectedMediaArtist||'')+'|'+(sort||'artist');
  let albums=mediaArtistAlbumsCache.get(cacheKey);
  if(!albums){
    albums=await j(API+'/media/artist_albums?artist='+encodeURIComponent(selectedMediaArtist)+'&sort='+encodeURIComponent(sort||'artist'));
    mediaArtistAlbumsCache.set(cacheKey, albums);
  }

  if(selectedMediaFolder && !albums.some(a=>a.folder===selectedMediaFolder)) selectedMediaFolder=null;
  if(!selectedMediaFolder && albums.length){
    selectedMediaFolder=albums[0].folder;
    selectedMediaAlbum=albums[0].album;
  }

  albumsBox.innerHTML=albums.map(x=>{
    const cover=x.first_path ? coverUrlPath(x.first_path) : coverUrl(x.folder||'', selectedMediaArtist||'');
    const sel=x.folder===selectedMediaFolder;
    return `<div class="mediaAlbumRow ${sel?'sel':''}" data-folder="${encodeURIComponent(x.folder||'')}" data-album="${encodeURIComponent(x.album||'')}">${coverBox(cover)}<div class="mediaAlbumText"><b>${escHtml(x.album)}</b><br><span class="small">${x.tracks} Titel · ${x.analyzed}/${x.tracks} analysiert · ${dur(x.duration)}</span><br><span class="small pathLine">${escHtml(x.folder||'')}</span></div></div>`;
  }).join('') || '<div class="empty">Keine Alben gefunden.</div>';

  albumsBox.querySelectorAll('[data-folder]').forEach(el=>{
    el.onclick=()=>selectMediaAlbum(decodeURIComponent(el.dataset.folder), decodeURIComponent(el.dataset.album||''));
  });

  if(selectedMediaFolder) await loadMediaTracks();
  else{
    tracksBox.innerHTML='';
    if(head) head.textContent='Bitte Album auswählen.';
    if(dl){dl.classList.add('disabled'); dl.href='#';}
  }
}

async function selectMediaAlbum(folder, album){
  selectedMediaFolder=folder;
  selectedMediaAlbum=album;

  // Update only the selection marker. Rebuilding every album card reloads all
  // cover images and caused the visible 3–4 second stutter.
  document.querySelectorAll('#mediaAlbums .mediaAlbumRow').forEach(el=>{
    let f='';
    try{ f=decodeURIComponent(el.dataset.folder||''); }catch(_e){ f=el.dataset.folder||''; }
    el.classList.toggle('sel', f===folder);
  });

  const head=document.getElementById('mediaAlbumHead');
  const tracksBox=document.getElementById('mediaTracks');
  if(head) head.innerHTML='<div class="mediaCoverBox large loading noCover"><div class="coverFallback">♪</div></div><div class="mediaAlbumText"><b>'+escHtml(album||'Album')+'</b><br><span>Cover/Titel werden geladen…</span></div>';
  if(tracksBox) tracksBox.innerHTML='<div class="empty">Titel werden geladen…</div>';
  await loadMediaTracks();
}

async function loadMediaTracks(){
  const requestToken=++mediaTracksRequestToken;
  const requestedFolder=selectedMediaFolder;
  const tracksBox=document.getElementById('mediaTracks');
  const head=document.getElementById('mediaAlbumHead');
  const dl=document.getElementById('mediaDownload');
  if(!selectedMediaFolder){return;}
  const tracks=await j(API+'/media/album_tracks?folder='+encodeURIComponent(requestedFolder)+'&artist='+encodeURIComponent(requestedFolder.startsWith('__album__:')?'':(selectedMediaArtist||'')));
  if(requestToken!==mediaTracksRequestToken || requestedFolder!==selectedMediaFolder) return;
  const cover=tracks[0]?.path ? coverUrlPath(tracks[0].path) : coverUrl(selectedMediaFolder, selectedMediaArtist||'');
  const album=selectedMediaAlbum || (tracks[0]?.album) || 'Album';
  const duration=tracks.reduce((a,x)=>a+Number(x.duration||0),0);
  if(head){
    const mediaArtistLabel = selectedMediaFolder.startsWith('__album__:') ? (tracks.some(t=>(t.artist||'')!==(tracks[0]?.artist||'')) ? 'Verschiedene Interpreten' : (tracks[0]?.artist||'')) : (selectedMediaArtist||'');
    head.innerHTML=`${coverBox(cover,true)}<div class="mediaAlbumText"><b>${escHtml(mediaArtistLabel)}</b><br>${escHtml(album)}<br><span>${tracks.length} Titel · ${dur(duration)} · ${escHtml(selectedMediaFolder.startsWith('__album__:') ? album : selectedMediaFolder)}</span></div>`;
  }
  if(dl){
    dl.classList.remove('disabled');
    dl.removeAttribute('aria-disabled');
    dl.href=API+'/media/download_album?folder='+encodeURIComponent(selectedMediaFolder);
  }
  if(tracks.length){
    const discNums=[...new Set(tracks.map(x=>Number(x.disc_number||parseInt(String(x.disc_raw||'').split('/')[0],10)||1)))].sort((a,b)=>a-b);
    const rowsHtml=tracks.map((x,idx)=>{
      const d=Number(x.disc_number||parseInt(String(x.disc_raw||'').split('/')[0],10)||1);
      const prev=idx>0 ? Number(tracks[idx-1].disc_number||parseInt(String(tracks[idx-1].disc_raw||'').split('/')[0],10)||1) : null;
      const discHeader=(discNums.length>1 && d!==prev) ? `<tr class="discHeader"><td colspan="6">Disc ${d}</td></tr>` : '';
      return discHeader+`<tr><td>${escHtml(trackNo(x)||'')}</td><td>${escHtml(x.title||'')}</td><td>${escHtml(x.artist||'')}</td><td>${dur(x.duration)}</td><td>${x.bitrate?Math.round(x.bitrate/1000):''}</td><td class="small">${escHtml(relPath(x.path))}</td></tr>`;
    }).join('');
    tracksBox.innerHTML=`<table><thead><tr><th>#</th><th>Titel</th><th>Interpret</th><th>Dauer</th><th>Bitrate</th><th>Pfad</th></tr></thead><tbody>${rowsHtml}</tbody></table>`;
  }else{
    tracksBox.innerHTML='<div class="empty">Keine Titel gefunden.</div>';
  }
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


async function refreshCurrentViewAfterChange(){
  await loadStats();
  await loadReference();
  await loadHistory();
  await loadBrowser();
  if(currentView==='tags'){
    await loadTagsPage();
    return;
  }
  await loadAlbums();
  if(selectedAlbum) await selectAlbum(selectedAlbum);
}

async function poll(){
  let s=await j(API+'/status');
  let p=s.total?Math.round(s.done/s.total*100):0;

  progress.style.width=p+'%';
  progressText.textContent=`${s.mode} · ${s.done}/${s.total} · Fehler ${s.errors} · ${s.current||s.message}`;
  status.textContent=s.message;
  const spFill=document.getElementById('sortProgressFill');
  const spText=document.getElementById('sortProgressText');
  if(spFill && spText){
    if((s.mode||'').toLowerCase().includes('sort')){
      spFill.style.width=p+'%';
      spText.textContent=`${s.done}/${s.total} Dateien · Fehler ${s.errors} · ${s.current||s.message}`;
    }else if(!s.running){
      spFill.style.width='0%';
      spText.textContent='Bereit zum Sortieren.';
    }
  }
  const running=!!s.running;
  if(btnStop) btnStop.disabled=!running;
  uiBusy = running;
  if(running){
    if(btnAnalyze) btnAnalyze.disabled=true;
    if(btnNorm) btnNorm.disabled=true;
    if(btnRef) btnRef.disabled=true;
    if(btnTrackNorm) btnTrackNorm.disabled=true;
    if(typeof btnAlbumAction !== 'undefined' && btnAlbumAction) btnAlbumAction.disabled=true;
  }else{
    if(btnAnalyze) btnAnalyze.disabled=!selectedAlbum;
    if(btnRef) btnRef.disabled=!selectedAlbum;
    updateNormalizeGuard();
    updateTrackSelectionUI();
    updateAlbumActionButton();
  }

  // Nur nach Abschluss eines Jobs neu laden. Kein permanentes Re-Rendering im Idle-Zustand,
  // damit die Albumauswahl nicht wieder zuklappt.
  await loadLog();

  if(lastRunning && !s.running){
    // Auto-Refresh nach Scan, Analyse, Normalisierung oder Wiederherstellung.
    // Dadurch müssen Audio-/Tag-Werte nicht mehr manuell aktualisiert werden.
    await refreshCurrentViewAfterChange();
  }

  lastRunning=s.running;
}

setInterval(poll,2000);
updateViewportMetrics();
loadSettings().then(()=>{updateViewportMetrics(); syncSettingsPageFromMain(); loadDashboard();});
loadStats();
loadReference();
loadBrowser();
loadAlbums();
loadLog();
loadHistory();
renderBatchBar();
if(typeof albumAction !== 'undefined' && albumAction) albumAction.onchange = renderBatchBar;
poll();

// Protokoll: manuelles Hochscrollen pausiert Autoscroll, damit die Ansicht nicht zurückspringt.
document.addEventListener('DOMContentLoaded',()=>{
  const box=document.getElementById('logBox');
  const auto=document.getElementById('protocolAutoscroll');
  if(box && auto){
    box.addEventListener('scroll',()=>{
      const nearBottom=box.scrollTop + box.clientHeight >= box.scrollHeight - 16;
      if(!nearBottom && auto.checked) auto.checked=false;
    }, {passive:true});
  }
});


/* MusicLab v1.9.39 safe UI helper - never blocks app startup */
(function(){
  function safe(fn){
    try{ fn(); }catch(e){ console.warn('MusicLab safe UI helper skipped:', e); }
  }
  function clean(s){
    return String(s || '').replace(/\b(Aktiv|Ausgewählt|Markiert)\b/g,'').replace(/\s+/g,' ').trim();
  }
  function txt(el){ return clean(el && (el.innerText || el.textContent) || ''); }
  function cardTitle(card){
    var h = card && card.querySelector && card.querySelector('h1,h2,h3,h4,b,.title,.album-title,.artist-title,[data-title]');
    return clean((h && (h.getAttribute('data-title') || h.innerText || h.textContent)) || txt(card).split('·')[0]);
  }
  function isSelectableCard(el){
    if(!el || el.nodeType !== 1) return false;
    var cls = String(el.className || '');
    var t = txt(el);
    if(!t) return false;
    return /album|artist|card|row|item/i.test(cls) || el.querySelector('input[type="checkbox"]');
  }
  function findCards(){
    return Array.prototype.slice.call(document.querySelectorAll(
      '.album-card,.artist-row,.library-card,.side-list-item,.item-card,.albumItem,.artistItem,.album,.artist,.row,.card,[data-album-key],[data-artist-key],[data-key],[data-path]'
    )).filter(isSelectableCard);
  }
  function ensureBadgeRow(card){
    var row = null;
    for(var i=0;i<card.children.length;i++){
      if(card.children[i].classList && card.children[i].classList.contains('ml-badge-row')){
        row = card.children[i];
        break;
      }
    }
    if(!row){
      row = document.createElement('div');
      row.className = 'ml-badge-row';
      card.appendChild(row);
    }
    return row;
  }
  function setBadge(row, cls, label, on){
    var b = row.querySelector('.' + cls);
    if(on){
      if(!b){
        b = document.createElement('span');
        b.className = 'ml-badge ' + cls;
        row.appendChild(b);
      }
      b.textContent = label;
    }else if(b){
      b.parentNode.removeChild(b);
    }
  }
  function hasSelectedState(card){
    var cb = card.querySelector('input[type="checkbox"]');
    if(cb && cb.checked) return true;
    var buttons = Array.prototype.slice.call(card.querySelectorAll('button'));
    for(var i=0;i<buttons.length;i++){
      if(/ausgewählt|abwählen/i.test(buttons[i].textContent || '')) return true;
    }
    return /\bAusgewählt\b|\bMarkiert\b/.test(card.innerText || '');
  }
  function hasActiveState(card){
    return /\bAktiv\b/.test(card.innerText || '') || card.classList.contains('active') || card.classList.contains('is-active') || card.classList.contains('selected');
  }
  function updateCredit(){
    var c = document.querySelector('.musiclab-credit-fixed');
    if(!c){
      c = document.createElement('div');
      c.className = 'musiclab-credit-fixed';
      c.textContent = 'Idea & Umsetzung by Lrd.Tiberius';
      document.body.appendChild(c);
    }
  }
  function ensureSummary(){
    // v2.0.0:
    // Die zusätzliche "Auswahl: ... markiert"-Box wird nicht mehr erzeugt.
    // Sie hat auf der Tags-Seite den Suchfilter zusammengedrückt.
    document.querySelectorAll('.ml-selection-summary').forEach(el=>el.remove());
    return null;
  }
  function updateUI(){
    safe(function(){
      document.querySelectorAll('.ml-selection-summary').forEach(el=>el.remove());
      updateCredit();
      var cards = findCards();
      var selected = 0;
      var activeLabel = '';
      for(var i=0;i<cards.length;i++){
        var card = cards[i];
        var sel = hasSelectedState(card);
        var act = hasActiveState(card);
        if(sel) selected++;
        if(act && !activeLabel) activeLabel = cardTitle(card);
        card.classList.toggle('ml-safe-selected', sel);
        var row = ensureBadgeRow(card);
        setBadge(row, 'ml-badge-active', 'Aktiv', act);
        setBadge(row, 'ml-badge-selected', 'Ausgewählt', sel);
      }
      var summary = ensureSummary();
      if(summary){
        summary.innerHTML = 'Auswahl: ' + selected + ' markiert' + (activeLabel ? ' <span class="muted">· Aktiv: ' + activeLabel.replace(/[<>&]/g,'') + '</span>' : '');
      }
    });
  }
  function start(){
    safe(function(){
      updateUI();
      setInterval(updateUI, 1200);
      document.addEventListener('click', function(){ setTimeout(updateUI, 120); setTimeout(updateUI, 700); }, true);
      document.addEventListener('change', function(){ setTimeout(updateUI, 80); }, true);
      if(window.MutationObserver){
        var mo = new MutationObserver(function(){ setTimeout(updateUI, 60); });
        mo.observe(document.body || document.documentElement, {childList:true, subtree:true});
      }
    });
  }
  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', start);
  }else{
    start();
  }
})();









async function reembedAllCoversApple(){
  let previewText='Die vorhandenen Cover werden Apple-kompatibel neu eingebettet.';
  try{
    const pv=await j(API+'/covers/reembed_preview');
    if(pv && pv.ok!==false){
      const examples=(pv.examples||[]).slice(0,5).map(x=>`- ${x.album} (${x.tracks} Titel)`).join('\n');
      previewText=`MusicLab-Albumgruppen: ${pv.albums}\nmit erkanntem Cover: ${pv.with_cover}\nohne erkanntes Cover: ${pv.without_cover}\nTitel gesamt: ${pv.tracks}\n\n${examples}${pv.with_cover>5?'\n...':''}`;
    }
  }catch(e){
    previewText='Vorschau konnte nicht geladen werden. Der Job kann trotzdem gestartet werden.';
  }

  if(!confirm(`Alle vorhandenen Cover Apple-kompatibel neu einbetten?\n\n${previewText}\n\nDas schreibt eingebettete Cover neu und erstellt cover.jpg/folder.jpg.`)) return;

  try{
    status.textContent='Apple-Cover-Neueinbettung wird gestartet...';
    if(progressText) progressText.textContent='Cover werden vorbereitet...';
    await j(API+'/covers/reembed_all',{method:'POST'});
    setAppView('protocol');
    setTimeout(poll, 300);
    setTimeout(poll, 1200);
  }catch(e){
    alert('Apple-Cover-Neueinbettung konnte nicht gestartet werden:\n'+e.message);
  }
}


async function exportAppleCoverMissingReport(){
  try{
    const rep=await j(API+'/covers/missing_report');
    if(!rep.ok) throw new Error(rep.error||'Report fehlgeschlagen');
    const lines=[];
    lines.push('Alben ohne erkanntes Cover');
    lines.push('Gesamt: '+(rep.without_cover||0)+' von '+(rep.albums||0));
    lines.push('');
    (rep.missing||[]).forEach(x=>{
      lines.push(`${x.album}\t${x.tracks} Titel\t${x.sample||''}`);
    });
    const blob=new Blob([lines.join('\n')],{type:'text/plain;charset=utf-8'});
    const a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download='musiclab_cover_ohne_erkanntes_cover.txt';
    document.body.appendChild(a);
    a.click();
    setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},1000);
  }catch(e){
    alert('Cover-Fehlerliste konnte nicht exportiert werden:\n'+e.message);
  }
}



async function removeAllEmbeddedCovers(){
  let previewText='Entfernt eingebettete Cover aus allen Audiodateien. cover.jpg/folder.jpg bleiben erhalten.';
  try{
    const pv=await j(API+'/covers/remove_embedded_preview');
    if(pv && pv.ok!==false){
      const examples=(pv.examples||[]).slice(0,5).map(x=>`- ${x}`).join('\n');
      previewText=`Audiodateien gesamt: ${pv.total}\nDateien mit erkanntem eingebettetem Cover: ${pv.with_cover}\n\n${examples}${pv.with_cover>5?'\n...':''}\n\nOrdnercover wie cover.jpg/folder.jpg bleiben erhalten.`;
    }
  }catch(e){
    previewText='Vorschau konnte nicht geladen werden. Der Job kann trotzdem gestartet werden.';
  }

  if(!confirm(`Eingebettete Cover wirklich aus allen Tags entfernen?\n\n${previewText}\n\nDas kann später mit "Alle Cover Apple-kompatibel neu einbetten" wiederhergestellt werden, wenn Ordnercover oder andere Quellen vorhanden sind.`)) return;

  try{
    status.textContent='Cover-Entfernung wird gestartet...';
    if(progressText) progressText.textContent='Eingebettete Cover werden entfernt...';
    await j(API+'/covers/remove_embedded_all',{method:'POST'});
    setAppView('protocol');
    setTimeout(poll, 300);
    setTimeout(poll, 1200);
  }catch(e){
    alert('Cover-Entfernung konnte nicht gestartet werden:\n'+e.message);
  }
}



async function removeCurrentTagCover(){
  try{
    const paths = (typeof visibleTagPaths==='function') ? visibleTagPaths() : [];
    let folder = selectedTagFolder || '';
    if((!folder || String(folder).startsWith('__album__:')) && paths.length && typeof parentFolderFromPath==='function'){
      folder = parentFolderFromPath(paths[0] || '') || folder;
    }

    if(!paths.length && !folder){
      alert('Bitte zuerst ein Album oder Titel auf der Tags-Seite auswählen.');
      return;
    }

    const countText = paths.length ? `${paths.length} sichtbare Titel` : `Ordner ${folder}`;
    if(!confirm(`Eingebettetes Cover aus den Tags entfernen?\n\nBetroffen: ${countText}\n\nOrdnercover wie cover.jpg/folder.jpg bleiben erhalten.`)) return;

    setTagActionBusy?.(true, 'Cover wird aus Tags entfernt…');
    const res = await j(API+'/tags/cover/remove', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({paths, folder})
    });

    coverCacheBust = Date.now();
    const msg = `Cover aus Tags entfernt: ${res.changed}/${res.checked} Dateien geändert` + (res.errors?.length ? ` · Fehler: ${res.errors.length}` : '');
    status.textContent = msg;
    if(progressText) progressText.textContent = msg;

    const cp=document.getElementById('tagCoverPreview');
    if(cp){
      cp.classList.add('coverRemoved');
      const hint=cp.querySelector('.tagCoverRemovedHint');
      if(hint) hint.textContent='Eingebettetes Cover entfernt';
    }

    if(res.errors?.length){
      alert(msg+'\n'+res.errors.join('\n'));
    }

    setTimeout(()=>{ try{ loadTagsPage(); }catch(e){} }, 350);
  }catch(e){
    alert('Cover konnte nicht entfernt werden:\n'+e.message);
  }finally{
    try{ setTagActionBusy?.(false); }catch(_e){}
  }
}



function enhanceTagCoverRemoveButton(){
  const box=document.getElementById('tagCoverPreview') || document.querySelector('.tagCoverPreview, .coverDrop, .coverBox');
  if(!box || box.querySelector('.tagCoverRemoveBtn')) return;
  const btn=document.createElement('button');
  btn.type='button';
  btn.className='tagCoverRemoveBtn';
  btn.title='Cover aus Tags entfernen';
  btn.textContent='×';
  btn.addEventListener('click', (ev)=>{ev.stopPropagation(); removeCurrentTagCover();});
  box.style.position='relative';
  box.appendChild(btn);
}
setInterval(()=>{try{ if(currentView==='tags') enhanceTagCoverRemoveButton(); }catch(e){}}, 1000);



/* v1.9.39: robustes Cover-X für virtuelle Alben */
function collectVisibleTagPathsForCoverRemoval(){
  const out=new Set();

  try{
    if(typeof visibleTagPaths==='function'){
      (visibleTagPaths()||[]).forEach(p=>{ if(p) out.add(String(p)); });
    }
  }catch(_e){}

  try{
    const pools=[window.visibleTagTracks, window.currentTagTracks, window.tagTracks, window.currentTracks, window.selectedTracks];
    pools.forEach(arr=>{
      if(Array.isArray(arr)){
        arr.forEach(t=>{
          const p=t && (t.path||t.file||t.filepath||t.relpath);
          if(p) out.add(String(p));
        });
      }
    });
  }catch(_e){}

  try{
    document.querySelectorAll('#tagTracks tr, #tagTracks tbody tr, .tagTrackRow, tr').forEach(row=>{
      const cells = row.cells ? Array.from(row.cells) : [];
      const vals = [
        row.dataset && row.dataset.path,
        row.getAttribute && row.getAttribute('data-path'),
        row.querySelector && row.querySelector('[data-path]') && row.querySelector('[data-path]').getAttribute('data-path'),
        row.querySelector && row.querySelector('.pathCell') && row.querySelector('.pathCell').textContent,
        row.querySelector && row.querySelector('.trackPath') && row.querySelector('.trackPath').textContent,
        cells.length ? cells[cells.length-1].textContent : ''
      ];
      vals.forEach(v=>{
        const s=String(v||'').trim();
        if(/\.(mp3|flac|m4a|mp4|aac|alac|ogg|oga|opus|wav|aiff|aif)$/i.test(s)){
          out.add(s);
        }
      });
    });
  }catch(_e){}

  return Array.from(out);
}

removeCurrentTagCover = async function(){
  try{
    const paths = collectVisibleTagPathsForCoverRemoval();
    let folder = selectedTagFolder || '';
    if((!folder || String(folder).startsWith('__album__:')) && paths.length && typeof parentFolderFromPath==='function'){
      folder = parentFolderFromPath(paths[0] || '') || folder;
    }

    const albumEl = document.querySelector('#tagAlbum, input[name="album"], [data-field="album"]');
    const artistEl = document.querySelector('#tagArtist, input[name="artist"], [data-field="artist"]');
    const album = String((albumEl && albumEl.value) || selectedAlbum || '').trim();
    const artist = String((artistEl && artistEl.value) || selectedArtist || '').trim();

    if(!paths.length && !folder && !album){
      alert('Bitte zuerst ein Album oder Titel auf der Tags-Seite auswählen.');
      return;
    }

    const countText = paths.length ? (paths.length + ' sichtbare Titel') : (album ? ('Album ' + album) : ('Ordner ' + folder));
    if(!confirm('Eingebettetes Cover aus den Tags entfernen?\n\nBetroffen: ' + countText + '\n\nOrdnercover wie cover.jpg/folder.jpg bleiben erhalten.')) return;

    if(typeof setTagActionBusy==='function') setTagActionBusy(true, 'Cover wird aus Tags entfernt…');
    const res = await j(API+'/tags/cover/remove', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({paths:paths, folder:folder, album:album, artist:artist})
    });

    coverCacheBust = Date.now();
    const msg = 'Cover aus Tags entfernt: ' + res.changed + '/' + res.checked + ' Dateien geändert' + ((res.errors && res.errors.length) ? (' · Fehler: ' + res.errors.length) : '');
    status.textContent = msg;
    if(progressText) progressText.textContent = msg;

    const cp=document.getElementById('tagCoverPreview') || document.querySelector('.tagCoverPreview, .coverDrop, .coverBox');
    if(cp){
      cp.classList.add('coverRemoved');
      let hint=cp.querySelector('.tagCoverRemovedHint');
      if(!hint){
        hint=document.createElement('div');
        hint.className='tagCoverRemovedHint';
        cp.appendChild(hint);
      }
      hint.textContent='Eingebettetes Cover entfernt';
    }

    if(res.errors && res.errors.length){
      alert(msg + '\n' + res.errors.join('\n'));
    }

    setTimeout(()=>{ try{ loadTagsPage(); }catch(e){} }, 350);
  }catch(e){
    alert('Cover konnte nicht entfernt werden:\n' + e.message);
  }finally{
    try{ if(typeof setTagActionBusy==='function') setTagActionBusy(false); }catch(_e){}
  }
};

