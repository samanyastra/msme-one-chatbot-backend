(function(){
  const socket = io(); // default namespace
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

  socket.on('connect', () => {
    appendMessage('Connected to server', 'bot');
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
