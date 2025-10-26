(async function(){
  const docsTbody = document.querySelector('#docs-table tbody');
  const usersTbody = document.querySelector('#users-table tbody');
  const btnRefresh = document.getElementById('btn-refresh');
  const btnReindex = document.getElementById('btn-reindex');
  const uploadForm = document.getElementById('upload-form');
  const uploadResult = document.getElementById('upload-result');

  async function fetchJSON(url, opts){
    const resp = await fetch(url, opts);
    const data = await resp.json().catch(()=>({}));
    if(!resp.ok) throw { status: resp.status, body: data };
    return data;
  }

  async function loadDocs(){
    docsTbody.innerHTML = '<tr><td colspan="5">Loading...</td></tr>';
    try{
      const docs = await fetchJSON('/api/docs');
      if(!docs.length){
        docsTbody.innerHTML = '<tr><td colspan="5">No documents</td></tr>';
        return;
      }
      docsTbody.innerHTML = '';
      for(const d of docs){
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${d.id}</td>
          <td>${escapeHtml(d.title)}</td>
          <td>${d.created_at ? new Date(d.created_at).toLocaleString() : ''}</td>
          <td style="max-width:360px">${escapeHtml(d.text || '').slice(0,200)}</td>
          <td>
            <button data-id="${d.id}" class="btn btn-sm btn-danger btn-delete">Delete</button>
          </td>
        `;
        docsTbody.appendChild(tr);
      }
      // attach delete handlers
      document.querySelectorAll('.btn-delete').forEach(b=>{
        b.addEventListener('click', async (e)=>{
          const id = b.dataset.id;
          if(!confirm('Delete doc #' + id + '?')) return;
          try{
            await fetchJSON(`/api/docs/${id}`, { method: 'DELETE' });
            await loadDocs();
          }catch(err){ alert('Delete failed'); }
        });
      });
    }catch(err){
      docsTbody.innerHTML = '<tr><td colspan="5">Failed to load</td></tr>';
    }
  }

  async function loadUsers(){
    usersTbody.innerHTML = '<tr><td colspan="2">Loading...</td></tr>';
    try{
      const users = await fetchJSON('/api/users');
      usersTbody.innerHTML = '';
      for(const u of users){
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${u.id}</td><td>${escapeHtml(u.username)}</td>`;
        usersTbody.appendChild(tr);
      }
    }catch(e){ usersTbody.innerHTML = '<tr><td colspan="2">Failed to load</td></tr>'; }
  }

  btnRefresh && btnRefresh.addEventListener('click', loadDocs);
  btnReindex && btnReindex.addEventListener('click', async ()=>{
    btnReindex.disabled = true;
    try{
      await fetchJSON('/api/docs/reindex', { method: 'POST' });
      alert('Reindex started');
    }catch(err){ alert('Reindex failed'); }
    btnReindex.disabled = false;
  });

  uploadForm && uploadForm.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const fd = new FormData(uploadForm);
    uploadResult.textContent = 'Uploading...';
    try{
      const resp = await fetch('/api/docs', { method: 'POST', body: fd });
      const data = await resp.json().catch(()=>({}));
      if(!resp.ok) throw { status: resp.status, body: data };
      uploadResult.innerHTML = `<div class="alert alert-success">Uploaded id ${data.id}</div>`;
      // trigger reindex automatically (UI call)
      await fetch('/api/docs/reindex', { method: 'POST' });
      await loadDocs();
    }catch(err){
      // prefer server-provided message; fall back to other diagnostics
      let msg = 'Upload failed';
      if (err) {
        if (err.body && err.body.msg) msg = err.body.msg;
        else if (err.msg) msg = err.msg;
        else if (err.status) msg = `Upload failed (status ${err.status})`;
        else if (err.message) msg = err.message;
      }
      uploadResult.innerHTML = `<div class="alert alert-danger">${escapeHtml(msg)}</div>`;
    }
  });

  function escapeHtml(s){ return String(s||'').replace(/[&<>"']/g, (m)=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }

  // initial load
  loadDocs();
  loadUsers();

})();
