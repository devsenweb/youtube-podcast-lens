// Immediately define the function on window to ensure it's available
(function() {
  'use strict';
  
  console.log('[main.js] Script loading...');

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

  // Update the YouTube player
  updateYouTubePlayer(videoId);

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
    // Optionally, fetch topic segments (keywords)
    if (topicSegmentsOutput) {
      topicSegmentsOutput.value = 'Loading...';
      try {
        const res = await fetch('/api/topic-keywords', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ transcript: transcript.map(seg => seg.text).join(' ') })
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
      const segRes = await fetch(`/segments/${videoId}.json`);
      if (segRes.ok) {
        loadedSegments = await segRes.json();
        // Populate the bottom gallery
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
    transcriptPre.textContent = 'Error: ' + e.message;
  }
}


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
    if (!seg.start) continue;
    const [mm, ss] = seg.start.split(':').map(Number);
    const segTime = mm * 60 + ss;
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
    keywordsDiv.textContent = `[${seg.start}] ${seg.keyword}`;
    imagesDiv.innerHTML = '';
    if (seg.image) {
      const img = document.createElement('img');
      img.src = `/images/${seg.image}`;
      img.alt = seg.keyword || '';
      img.title = `[${seg.start}] ${seg.keyword}`;
      img.style.maxWidth = '100%';
      img.style.maxHeight = '120px';
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