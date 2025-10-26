(function(){
  // explicitly connect to backend - update URL as needed for production
  const socket = io('http://localhost:5000', {
    transports: ['websocket', 'polling'],
    reconnectionAttempts: 5,
    reconnectionDelay: 1000
  });
  
  const messagesEl = document.getElementById('messages');
  const inputEl = document.getElementById('input');
  const sendBtn = document.getElementById('send');
  const hiBtn = document.getElementById('btn-hi');
  const helloBtn = document.getElementById('btn-hello');

  function appendMessage(text, cls){
    const d = document.createElement('div');
    d.className = 'msg ' + cls;
    d.textContent = text;
    messagesEl.appendChild(d);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // Debug connection events
  socket.on('connect_error', (error) => {
    console.error('Connection error:', error);
    appendMessage('Connection error: ' + error, 'bot error');
  });

  socket.on('connect', () => {
    console.log('Connected! Socket ID:', socket.id);
    appendMessage('Connected to server (ID: ' + socket.id + ')', 'bot');
  });

  socket.on('disconnect', (reason) => {
    console.log('Disconnected:', reason);
    appendMessage('Disconnected: ' + reason, 'bot');
  });

  socket.on('system', (payload) => {
    appendMessage(payload.msg || 'system', 'bot');
  });

  socket.on('chat_response', (payload) => {
    if(payload && payload.error){
      appendMessage('Error: '+payload.error, 'bot');
      return;
    }
    const txt = payload && payload.answer ? payload.answer : JSON.stringify(payload);
    appendMessage(txt, 'bot');
  });

  sendBtn.addEventListener('click', () => {
    const v = (inputEl.value || '').trim();
    if(!v) return;
    appendMessage(v, 'user');
    socket.emit('chat_message', { query: v });
    inputEl.value = '';
  });

  inputEl.addEventListener('keydown', (e) => {
    if(e.key === 'Enter'){ sendBtn.click(); }
  });

  hiBtn.addEventListener('click', () => {
    const msg = 'Hi';
    appendMessage(msg, 'user');
    socket.emit('chat_message', { query: msg });
  });

  helloBtn.addEventListener('click', () => {
    const msg = 'Hello';
    appendMessage(msg, 'user');
    socket.emit('chat_message', { query: msg });
  });

})();
