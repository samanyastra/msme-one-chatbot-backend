(function(){
  // Reuse a single socket instance across hot-reloads / multiple script runs
  // to avoid creating multiple connections (which cause multiple SIDs).
  if (!window.__chat_socket) {
    // create and attach to global so subsequent script executions reuse it
    // Use relative connection so client connects to the same origin the page was served from.
    window.__chat_socket = io({
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 5,
      reconnectionDelay: 1000
    });
  }
  const socket = window.__chat_socket;

  // guard so handlers attach only once
  if (!window.__chat_handlers_attached) {
    window.__chat_handlers_attached = true;

    socket.on('connect_error', (error) => {
      console.error('Connection error:', error);
      appendMessage && appendMessage('Connection error: ' + error, 'bot error');
      // ensure UI not stuck
      window.__chat_busy = false;
      setBusy && setBusy(false);
    });

    socket.on('connect', () => {
      console.log('Connected! Socket ID:', socket.id);
      appendMessage && appendMessage('Connected to server (ID: ' + socket.id + ')', 'bot');
    });

    socket.on('disconnect', (reason) => {
      console.log('Disconnected:', reason);
      appendMessage && appendMessage('Disconnected: ' + reason, 'bot');
      // on disconnect, clear busy so UI becomes usable
      window.__chat_busy = false;
      setBusy && setBusy(false);
    });

    socket.on('system', (payload) => {
      appendMessage && appendMessage(payload && payload.msg ? payload.msg : 'system', 'bot');
    });

    // updated handler: place returned audio_url as a user-side audio preview
    socket.on('chat_response', (payload) => {
      // response arrived -> clear busy and re-enable UI
      window.__chat_busy = false;
      setBusy && setBusy(false);

      if (payload && payload.error) {
        appendMessage('Error: ' + payload.error, 'bot');
        return;
      }

      // if server returned a transcript, show it as a user-like note
      if (payload.transcript) {
        appendMessage('Transcript: ' + payload.transcript, 'user');
      }

      // If there's an audio URL, prefer to show it on the user side.
      if (payload.audio_url) {
        const messagesEl = document.getElementById('messages');
        let replaced = false;
        if (messagesEl) {
          // find the most recent user audio element with a data: URL and replace its src
          const userAudios = messagesEl.querySelectorAll('div.msg.user audio');
          for (let i = userAudios.length - 1; i >= 0; i--) {
            const a = userAudios[i];
            try {
              if (a && a.src && a.src.startsWith('data:')) {
                a.src = payload.audio_url;
                replaced = true;
                break;
              }
            } catch (e) {
              // ignore access exceptions
            }
          }

          // if nothing to replace, append a new user audio element
          if (!replaced) {
            const wrapper = document.createElement('div');
            wrapper.className = 'msg user';
            const audio = document.createElement('audio');
            audio.controls = true;
            audio.src = payload.audio_url;
            audio.style.maxWidth = '320px';
            wrapper.appendChild(audio);
            messagesEl.appendChild(wrapper);
            messagesEl.scrollTop = messagesEl.scrollHeight;
          }
        }
      }

      // show server answer as bot (if any)
      if (payload.answer) {
        appendMessage(payload.answer, 'bot');
      }
    });
  }

  const messagesEl = document.getElementById('messages');
  const inputEl = document.getElementById('input');
  const sendBtn = document.getElementById('send');
  const hiBtn = document.getElementById('btn-hi');
  const helloBtn = document.getElementById('btn-hello');
//   const rocketBtn = document.getElementById('btn-rocket');
  const micBtn = document.getElementById('mic-btn');
  const recStatus = document.getElementById('rec-status');

  // --- NEW: busy helpers ---
  // global busy flag
  window.__chat_busy = window.__chat_busy || false;

  function setBusy(state) {
    window.__chat_busy = !!state;
    const controls = [sendBtn, micBtn, hiBtn, helloBtn];
    controls.forEach((el) => { if(el) el.disabled = !!state; });
    if(inputEl) inputEl.disabled = !!state;
    // optionally add visual cue
    if(state) {
      // e.g., lower opacity for disabled controls via inline style fallback
      controls.forEach((el) => { if(el) el && (el.style.opacity = '0.6'); });
      if(inputEl) inputEl.style.opacity = '0.9';
    } else {
      controls.forEach((el) => { if(el) el && (el.style.opacity = '1'); });
      if(inputEl) inputEl.style.opacity = '1';
    }
  }
  // ensure setBusy exists globally for handlers above
  window.__setChatBusy = setBusy;

  let mediaRecorder = null;
  let recordedChunks = [];

  function appendMessage(text, cls){
    if(!messagesEl) return;
    const d = document.createElement('div');
    d.className = 'msg ' + (cls || '');
    d.textContent = text;
    messagesEl.appendChild(d);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // helper to attach listener only once
  function attachOnce(el, event, handler){
    if(!el) return;
    if(el.dataset.listenerAttached === 'true') return;
    el.addEventListener(event, handler);
    el.dataset.listenerAttached = 'true';
  }

  // text send
  attachOnce(sendBtn, 'click', () => {
    if(window.__chat_busy) return;            // ignore while busy
    const v = (inputEl && inputEl.value || '').trim();
    if(!v) return;
    appendMessage(v, 'user');
    // mark busy before sending
    window.__chat_busy = true;
    setBusy(true);
    socket.emit('chat_message', { query: v });
    if(inputEl) inputEl.value = '';
  });

  // Enter key
  if(inputEl){
    attachOnce(inputEl, 'keydown', (e) => {
      if(e.key === 'Enter'){
        e.preventDefault();
        sendBtn && sendBtn.click();
      }
    });
  }

  attachOnce(hiBtn, 'click', () => {
    if(window.__chat_busy) return;
    const msg = 'Hi';
    appendMessage(msg, 'user');
    window.__chat_busy = true;
    setBusy(true);
    socket.emit('chat_message', { query: msg });
  });

  attachOnce(helloBtn, 'click', () => {
    if(window.__chat_busy) return;
    const msg = 'Hello';
    appendMessage(msg, 'user');
    window.__chat_busy = true;
    setBusy(true);
    socket.emit('chat_message', { query: msg });
  });

//   attachOnce(rocketBtn, 'click', () => {
//     if(window.__chat_busy) return;
//     const msg = (inputEl && (inputEl.value || '').trim()) || '';
//     if(!msg) return;
//     if(inputEl) inputEl.value = '';
//     appendMessage(msg, 'user');
//     window.__chat_busy = true;
//     setBusy(true);
//     socket.emit('chat_message', { query: msg, meta: { type: 'rocket' } });
//   });

  // Audio recording / mic button
  async function startRecording(){
    if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
      alert('Media recording not supported in this browser.');
      return;
    }
    try{
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordedChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => { if(e.data && e.data.size) recordedChunks.push(e.data); };
      mediaRecorder.onstop = async () => {
        const blob = new Blob(recordedChunks, { type: 'audio/webm' });

        // show local UI feedback
        appendMessage('[Audio recorded]', 'user');

        // convert to dataURL and send over socket instead of HTTP
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64data = reader.result; // data:...;base64,...

          // mark busy before sending and disable UI
          window.__chat_busy = true;
          setBusy(true);

          try {
            // emit audio over socket for server-side processing
            socket.emit('audio_message', {
              audio: base64data,
              audio_type: blob.type,
              audio_len: blob.size
            });
            // server will emit chat_response when processing completes
          } catch (err) {
            console.error('socket audio emit failed', err);
            appendMessage('Audio send failed', 'bot');
            // clear busy on failure
            window.__chat_busy = false;
            setBusy(false);
          } finally {
            // hide overlay (server response will re-enable UI)
            const overlay = document.getElementById('record-overlay');
            if(overlay) overlay.classList.remove('show');
          }
        };
        reader.readAsDataURL(blob);

        // stop all tracks (stream variable available in closure in original code)
        try { stream && stream.getTracks && stream.getTracks().forEach(t=>t.stop()); } catch(e){}
      };
      mediaRecorder.start();
      if(micBtn) micBtn.classList.add('recording');
      if(micBtn) micBtn.setAttribute('aria-pressed','true');
      if(recStatus) recStatus.innerHTML = '<span class="rec-indicator"></span> Recording...';
      // show overlay if present
      const overlay = document.getElementById('record-overlay');
      if(overlay) overlay.classList.add('show');
    }catch(err){
      console.error('record start failed', err);
      alert('Could not start recording: ' + err);
    }
  }

  function stopRecording(){
    if(mediaRecorder && mediaRecorder.state !== 'inactive'){
      mediaRecorder.stop();
    }
    if(micBtn) micBtn.classList.remove('recording');
    if(micBtn) micBtn.setAttribute('aria-pressed','false');
    if(recStatus) recStatus.innerHTML = '';
    mediaRecorder = null;
    recordedChunks = [];
    // hide overlay if present
    const overlay = document.getElementById('record-overlay');
    if(overlay) overlay.classList.remove('show');
  }

  attachOnce(micBtn, 'click', async () => {
    if(window.__chat_busy && !(mediaRecorder && mediaRecorder.state === 'recording')) return;
    if(mediaRecorder && mediaRecorder.state === 'recording'){
      stopRecording();
    }else{
      startRecording();
    }
  });

})();
