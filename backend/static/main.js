// Immediately define the function on window to ensure it's available
(function() {
  'use strict';
  
  console.log('[main.js] Script loading...');
  // Utility for loading overlay
  function showLoading(msg){
    const m=document.getElementById('loadingModal');
    if(!m) return; m.style.display='block';
    const s=document.getElementById('loadingStatusMsg'); if(s&&msg) s.textContent=msg;
  }
  function hideLoading(){ const m=document.getElementById('loadingModal'); if(m) m.style.display='none'; }
  

  // --- CLEAN YOUTUBE PLAYER INITIALIZATION ---
  if (typeof window.ytPlayer === "undefined") window.ytPlayer = null;
  if (typeof window.ytPlayerReady === "undefined") window.ytPlayerReady = false;
  if (typeof window.queuedVideoId === "undefined") window.queuedVideoId = null;

  // Define fetchTranscript function first
  async function fetchTranscript() {
    console.log('[fetchTranscript] ENTRY');
    const url = document.getElementById('videoIdInput').value;
    const videoId = extractVideoId(url);
    const transcriptPre = document.getElementById('transcript');
    const topicSegmentsOutput = document.getElementById('topicSegmentsOutput');
    transcriptPre.textContent = 'Loading...';
    if (topicSegmentsOutput) topicSegmentsOutput.value = '';

  if (!videoId) {
    console.error('[fetchTranscript] Invalid or missing videoId.');
    alert('Error: Could not extract a valid YouTube video ID from your input.');
    transcriptPre.textContent = 'Error: Could not extract a valid YouTube video ID from your input.';
    return;
  }

  // We will load the player later unless we are using cached segments
  let deferPlayerLoad = false;

  // Check if segment JSON already exists
  let segmentExists = false;
  try {
    const segCheck = await fetch(`/api/segments/${videoId}`, {
      method: 'GET',
      headers: { 'Cache-Control': 'no-cache' }
    });
    if (segCheck.ok) segmentExists = true;
    // Immediately cancel reading body to avoid unnecessary work
    if (segCheck.body && typeof segCheck.body.cancel === 'function') {
      try { segCheck.body.cancel(); } catch (_) {}
    }
  } catch (e) {
    segmentExists = false;
  }

  // Check for 'regenerate' checkbox
  const regenerateCheckbox = document.getElementById('regenerateCheckbox');
  const forceRegenerate = regenerateCheckbox && regenerateCheckbox.checked;

  if (segmentExists && !forceRegenerate) {
    // Cached path -> load player immediately
    updateYouTubePlayer(videoId);
    // Fetch existing segment JSON
    try {
      const response = await fetch(`/api/segments/${videoId}`);
      if (!response.ok) throw new Error(`Failed to fetch segment JSON: ${response.status} ${response.statusText}`);
      const data = await response.json();
      loadedSegments = data;
      // Normalize start timestamps to seconds numbers
      loadedSegments.forEach(seg => {
        if (typeof seg.start === 'string' && seg.start.includes(':')) {
          const [mm, ss] = seg.start.split(':').map(x => parseInt(x, 10));
          if (!isNaN(mm) && !isNaN(ss)) seg.start = mm * 60 + ss;
        }
      });
      // Fetch full transcript lines for display
      try {
        const tRes = await fetch(`/api/transcript/?video_id=${encodeURIComponent(videoId)}`);
        if (tRes.ok) {
          const tData = await tRes.json();
          if (Array.isArray(tData) && transcriptPre) {
            transcriptPre.textContent = tData.map(seg => {
              const min = String(Math.floor(seg.start/60)).padStart(2,'0');
              const sec = String(Math.floor(seg.start%60)).padStart(2,'0');
              return `[${min}:${sec}] ${seg.text}`;
            }).join('\n');
          }
        }
      } catch(_) {}


      // Populate the keywords/side panel
      const topicSegmentsOutput = document.getElementById('topicSegmentsOutput');
      if (topicSegmentsOutput) {
        topicSegmentsOutput.value = loadedSegments.map(seg => `[${seg.start}] ${seg.keyword}`).join('\n');
      }
      // Immediately update side panel for playhead 0
      updateKeywordsAndImages(0);
    } catch (e) {
      console.error('[fetchTranscript] Error fetching segment JSON:', e);
    }
    return;
  }

  // Show overlay while we prepare visuals
  showLoading('Preparing visuals. Please wait while we analyze the transcript and generate topic images...');
  deferPlayerLoad = true;
  // Start polling DB until images ready
  if(imagesReadyPoll) clearInterval(imagesReadyPoll);
  imagesReadyPoll = setInterval(async ()=>{
    try{
      const r = await fetch(`/api/segments/${videoId}`, {headers:{'Cache-Control':'no-cache'}});
      if(!r.ok) return;
      const js = await r.json();
      if(Array.isArray(js) && js.length>0 && js.every(s=>s.image)){
        loadedSegments = js;
        clearInterval(imagesReadyPoll);
        imagesReadyPoll = null;
        hideLoading();
        updateYouTubePlayer(videoId);
        // refresh gallery preview
        const segmentImagesPreview = document.getElementById('segmentImagesPreview');
        if(segmentImagesPreview){
          segmentImagesPreview.innerHTML='';
          js.forEach(s=>{
            if(s.image){
              const img=document.createElement('img');
              img.src=`/images/${s.image}`;
              img.alt=s.keyword||'';
              img.title=`[${s.start}] ${s.keyword}`;
              img.style.maxWidth='220px';
              img.style.maxHeight='160px';
              img.style.borderRadius='8px';
              img.style.margin='0.5em';
              segmentImagesPreview.appendChild(img);
            }
          });
          document.getElementById('mainContent').style.display='block';
        }
      }
    }catch(_){}
  }, 4000);
  // Fetch transcript from backend
  try {
    const response = await fetch(`/api/transcript/?video_id=${encodeURIComponent(videoId)}`);
    if (!response.ok) throw new Error(`Failed to fetch transcript: ${response.status} ${response.statusText}`);
    const data = await response.json();
    let transcript = null;
    if (Array.isArray(data)) {
      transcript = data;
    } else if (data.transcript && Array.isArray(data.transcript)) {
      transcript = data.transcript;
    }
    if (!transcript || transcript.length === 0) {
      transcriptPre.textContent = 'No transcript found for this video.';
      return;
    }
    // Display transcript with timestamps
    transcriptPre.textContent = transcript.map(seg => {
      const min = String(Math.floor(seg.start/60)).padStart(2,'0');
      const sec = String(Math.floor(seg.start%60)).padStart(2,'0');
      return `[${min}:${sec}] ${seg.text}`;
    }).join('\n');
    // Optionally, fetch topic segments (keywords)dddd
    if (topicSegmentsOutput) {
      topicSegmentsOutput.value = 'Loading...';
      try {
        const res = await fetch('/api/topic-keywords', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ videoId, transcript: transcript.map(seg => seg.text).join(' ') })
        });
        const topicData = await res.json();
        if (topicData.segments && Array.isArray(topicData.segments)) {
          topicSegmentsOutput.value = topicData.segments.map(seg => `[${seg.start}] ${seg.keyword}`).join('\n');
        } else if (topicData.error) {
          topicSegmentsOutput.value = 'Error: ' + topicData.error;
        } else {
          topicSegmentsOutput.value = 'No segments found.';
        }
      } catch (e) {
        topicSegmentsOutput.value = 'Error: ' + e.message;
      }
    }
    // Fetch and display segment images if available
    try {
      const segRes = await fetch(`/api/segments/${videoId}`);
      if (segRes.ok) {
        loadedSegments = await segRes.json();
        // Normalize start timestamps to seconds numbers
        loadedSegments.forEach(seg => {
          if (typeof seg.start === 'string' && seg.start.includes(':')) {
            const [mm, ss] = seg.start.split(':').map(x => parseInt(x, 10));
            if (!isNaN(mm) && !isNaN(ss)) seg.start = mm * 60 + ss;
          }
        });
        
        const segmentImagesPreview = document.getElementById('segmentImagesPreview');
        if (segmentImagesPreview) {
          segmentImagesPreview.innerHTML = '';
          loadedSegments.forEach(seg => {
            if (seg.image) {
              const img = document.createElement('img');
              img.src = `/images/${seg.image}`;
              img.alt = seg.keyword || '';
              img.title = `[${seg.start}] ${seg.keyword}`;
              img.style.maxWidth = '220px';
              img.style.maxHeight = '160px';
              img.style.borderRadius = '8px';
              img.style.margin = '0.5em';
              segmentImagesPreview.appendChild(img);
            }
          });
          // Show the section if images exist
          const allHaveImages = loadedSegments.length>0 && loadedSegments.every(s=>s.image);
          if(allHaveImages){ hideLoading(); if(deferPlayerLoad) updateYouTubePlayer(videoId); }
          if (loadedSegments.some(seg => seg.image)) {
            document.getElementById('mainContent').style.display = 'block';
          } else {
            document.getElementById('mainContent').style.display = 'none';
          }
        }
      }
    } catch (e) {
      console.warn('No segment images found or error loading:', e);
      document.getElementById('mainContent').style.display = 'none';
    }
    // Immediately update side panel for playhead 0
    updateKeywordsAndImages(0);
  } catch (e) {
    console.error('[fetchTranscript] Error processing transcript or segments:', e);
    transcriptPre.textContent = 'Error processing transcript or segments.';
  }
  } // End of fetchTranscript

  // IMMEDIATELY expose to window
  window.fetchTranscript = fetchTranscript;

  function extractVideoId(url) {
    // Robust extraction: handles various YouTube URL formats and plain IDs
    const patterns = [
      /(?:v=|youtu\.be\/|embed\/|shorts\/)([\w-]{11})/, // common patterns
      /youtube\.com\/watch\?.*?v=([\w-]{11})/,           // explicit v= param
    ];
    for (const pattern of patterns) {
      const match = url.match(pattern);
      if (match) return match[1];
    }
    // fallback: if input is just the ID
    if (/^[\w-]{11}$/.test(url)) return url;
    return null;
  }

function updateYouTubePlayer(videoId) {
  try {
    console.log('[updateYouTubePlayer] ENTRY:', videoId);
    const playerTime = document.getElementById('playerTime');
    
    if (!videoId || typeof videoId !== 'string' || videoId.length !== 11) {
      console.error('[YT] updateYouTubePlayer called with invalid videoId:', videoId);
      if (playerTime) playerTime.textContent = 'Invalid YouTube video ID.';
      return;
    }
    
    if (!window.ytPlayerReady) {
      console.log('[YT] Player not ready, queueing videoId:', videoId);
      window.queuedVideoId = videoId;
      return;
    }
    
    if (window.ytPlayer && typeof window.ytPlayer.loadVideoById === 'function') {
      window.ytPlayer.loadVideoById(videoId);
      window.ytPlayer.seekTo(0);
      window.ytPlayer.playVideo();
      if (playerTime) playerTime.textContent = '';
      console.log('[YT] Player updated with new videoId:', videoId);
    } else {
      console.warn('[YT] Player object not available after ready.');
    }
  } catch (outerErr) {
    console.error('[updateYouTubePlayer] Outer error:', outerErr);
  }
}

// YouTube API callback - this will be called when the API is ready
window.onYouTubeIframeAPIReady = function() {
  console.log('[YT] onYouTubeIframeAPIReady called');
  window.ytPlayer = new YT.Player('youtubePlayer', {
    height: '225',
    width: '400',
    videoId: window.queuedVideoId || '',
    events: {
      'onReady': function(e) {
        window.ytPlayerReady = true;
        console.log('[YT] Player ready');
        if (window.queuedVideoId) {
          updateYouTubePlayer(window.queuedVideoId);
          window.queuedVideoId = null;
        }
      },
      'onError': function(e) {
        document.getElementById('playerTime').textContent = 'YouTube player error.';
        console.log('[YT] Player error:', e);
      },
      'onStateChange': function(e) {
        if (e.data === 1) { // Playing
          console.log('[YT] Video playing. Start polling.');
          startPlayerTimePolling();
        } else {
          console.log('[YT] Video paused or stopped. Stop polling.');
          stopPlayerTimePolling();
        }
      }
    }
  });
  console.log('[YT] Player created by onYouTubeIframeAPIReady');
};

// Fallback loader for API script (if not already loaded)
if (!document.querySelector('script[src*="youtube.com/iframe_api"]')) {
  var tag = document.createElement('script');
  tag.src = "https://www.youtube.com/iframe_api";
  document.head.prepend(tag);
  console.log('[main.js] Injected YouTube Iframe API script manually');
}

let playerTimeInterval = null;

// Store loaded segments globally
let loadedSegments = null;
let lastSegmentsRefresh = 0; // timestamp ms of last refresh attempt
let imagesReadyPoll = null; // interval id

function startPlayerTimePolling() {
  console.log('[startPlayerTimePolling] ENTRY');
  stopPlayerTimePolling(); // Ensure only one interval

  if (window.ytPlayer && window.ytPlayerReady) {
    playerTimeInterval = setInterval(() => {
      const time = window.ytPlayer.getCurrentTime();
      document.getElementById('playerTime').textContent = `Current Time: ${time.toFixed(2)}s`;
      console.log('[getCurrentPlayerTime] Current player time (YT API):', time);
      updateKeywordsAndImages(time);
    }, 1000);
    console.log('[Polling] Started.');
  }
}

// Helper: Find current segment by playhead time
function getCurrentSegment(time) {
  if (!loadedSegments || !Array.isArray(loadedSegments)) return null;
  // Convert time (seconds) to MM:SS
  const pad = n => String(n).padStart(2, '0');
  const curMM = pad(Math.floor(time / 60));
  const curSS = pad(Math.floor(time % 60));
  let lastSeg = null;
  for (const seg of loadedSegments) {
    if (seg.start == null) continue;
    let segTime;
    if (typeof seg.start === 'number') {
      segTime = seg.start;
    } else if (typeof seg.start === 'string' && seg.start.includes(':')) {
      const [mm, ss] = seg.start.split(':').map(Number);
      segTime = mm * 60 + ss;
    } else {
      continue;
    }
    if (time >= segTime) lastSeg = seg;
    else break;
  }
  return lastSeg;
}

function updateKeywordsAndImages(time) {
  const keywordsDiv = document.getElementById('keywordsAtPlayhead');
  const imagesDiv = document.getElementById('imagesAtPlayhead');
  if (!keywordsDiv || !imagesDiv) return;
  const seg = getCurrentSegment(time);
  if (seg) {
    // If this segment lacks an image, periodically try to refresh segments (max every 4s)
    const now = Date.now();
    if (!seg.image && now - lastSegmentsRefresh > 4000) {
      lastSegmentsRefresh = now;
      fetch(`/api/segments/${encodeURIComponent(extractVideoId(document.getElementById('videoIdInput').value))}`)
        .then(r => r.ok ? r.json() : null)
        .then(js => {
          if (js && Array.isArray(js)) {
            loadedSegments = js;
            // also refresh gallery preview images; if now all images present hide overlay and load player
            const allImagesNow = js.length>0 && js.every(s=>s.image);
            if(allImagesNow){ hideLoading(); if(deferPlayerLoad) updateYouTubePlayer(extractVideoId(document.getElementById('videoIdInput').value)); }
            // also refresh gallery preview images
            const segmentImagesPreview = document.getElementById('segmentImagesPreview');
            if (segmentImagesPreview) {
              segmentImagesPreview.innerHTML = '';
              loadedSegments.forEach(s => {
                if (s.image) {
                  const img = document.createElement('img');
                  img.src = `/images/${s.image}`;
                  img.alt = s.keyword || '';
                  img.title = `[${s.start}] ${s.keyword}`;
                  img.style.maxWidth = '220px';
                  img.style.maxHeight = '160px';
                  img.style.borderRadius = '8px';
                  img.style.margin = '0.5em';
                  segmentImagesPreview.appendChild(img);
                }
              });
            }
          }
        })
        .catch(()=>{});
    }
    keywordsDiv.textContent = `[${seg.start}] ${seg.keyword}`;
    imagesDiv.innerHTML = '';
    if (seg.image) {
      const img = document.createElement('img');
      img.src = `/images/${seg.image}`;
      img.alt = seg.keyword || '';
      img.title = `[${seg.start}] ${seg.keyword}`;
      img.style.width = '100%';
      img.style.height = '100%';
      img.style.objectFit = 'cover';
      img.style.borderRadius = '8px';
      imagesDiv.appendChild(img);
    }
  } else {
    keywordsDiv.textContent = '(No keywords yet)';
    imagesDiv.innerHTML = '';
  }
}


function stopPlayerTimePolling() {
  console.log('[stopPlayerTimePolling] ENTRY');
  if (playerTimeInterval) {
    clearInterval(playerTimeInterval);
    playerTimeInterval = null;
    console.log('[Polling] Stopped.');
  }
}

function getCurrentPlayerTime() {
  if (window.ytPlayer && window.ytPlayerReady && typeof window.ytPlayer.getCurrentTime === 'function') {
    const time = window.ytPlayer.getCurrentTime();
    console.log('[getCurrentPlayerTime] Current player time (YT API):', time);
    return time;
  }
  console.log('[getCurrentPlayerTime] Player not ready, returning 0');
  return 0;
}

  // Make sure all functions are available globally
  window.updateYouTubePlayer = updateYouTubePlayer;
  window.extractVideoId = extractVideoId;
  window.getCurrentPlayerTime = getCurrentPlayerTime;

  console.log('[main.js] All functions initialized. window.fetchTranscript is', typeof window.fetchTranscript);
})(); // End IIFE