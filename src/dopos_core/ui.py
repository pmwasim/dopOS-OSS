"""Code-native local control room UI."""

PAGE = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>dopOS local control room</title>
  <style>
    :root { --bg:#07101f; --panel:#0b1328; --line:#26365a; --muted:#9aa7c7; --text:#f3f6ff; --blue:#4c82ff; --violet:#7a3cff; --ok:#75e6a2; --danger:#ff697f; }
    * { box-sizing:border-box; }
    body { margin:0; min-height:100vh; color:var(--text); font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:radial-gradient(circle at 45% 15%,#172d5d 0,#08111f 37%,#040914 100%); }
    .shell { max-width:1520px; margin:auto; padding:20px 28px; }
    .top { height:52px; display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid #1e2c4c; }
    .brand { font-size:31px; font-weight:650; letter-spacing:-1.7px; }
    .clock { color:#dce4fb; font-size:15px; }
    .tools { display:flex; gap:18px; align-items:center; color:#cad4ec; font-size:14px; }
    .tools span:before { content:'●'; color:var(--ok); font-size:11px; margin-right:7px; }
    .tools .status-off:before { color:#ff9aa8; }
    .tools .status-off { color:#a7adc0; }
    .frame { display:grid; grid-template-columns:minmax(0,2.45fr) minmax(330px,1fr); min-height:calc(100vh - 94px); overflow:hidden; border:1px solid #1e3154; border-radius:17px; background:#07101ee8; box-shadow:0 30px 100px #0008; }
    .conversation { display:flex; flex-direction:column; gap:26px; padding:42px clamp(28px,8vw,140px) 30px; }
    .thread { display:flex; flex-direction:column; gap:25px; min-height:390px; }
    .message { max-width:82%; font-size:17px; line-height:1.56; }
    .message.user { align-self:flex-end; padding:20px 24px; border-radius:16px 16px 4px 16px; background:linear-gradient(135deg,#1d3158,#162442); }
    .agent { display:grid; grid-template-columns:112px 1fr; gap:20px; align-items:start; }
    .orb { width:86px; height:86px; display:grid; place-items:center; border:2px solid #714bff; border-radius:50%; color:#a890ff; font-size:37px; box-shadow:0 0 36px #653cdd6b; }
    .orb:after { content:'⌁'; transform:rotate(-10deg); }
    .label { color:#8e73ff; font-weight:700; }
    .time { margin-left:12px; color:var(--muted); font-size:13px; }
    .explain { margin:7px 0; color:#e7ecfb; }
    .plan { padding:19px 20px; border:1px solid #6947d2; border-radius:15px; background:#0b1428; box-shadow:inset 2px 0 #7c42ff; }
    .plan h3 { margin:0 0 7px; font-size:17px; }
    .plan p { margin:0 0 13px; color:#c3cee7; }
    .actions { display:flex; flex-wrap:wrap; gap:7px; margin-bottom:15px; }
    .actions span { padding:5px 7px; border:1px solid #2d4777; border-radius:6px; color:#a9c2ff; font:12px ui-monospace,SFMono-Regular,monospace; }
    .buttons { display:flex; gap:10px; }
    .button { padding:11px 20px; border:1px solid #52648b; border-radius:9px; background:#17213a; color:white; font:600 15px inherit; cursor:pointer; }
    .button.primary { border-color:#6a68ff; background:linear-gradient(135deg,#3278fa,#7d38e5); }
    .button.danger { border-color:#9f4052; background:#251520; color:#ff9aa8; }
    .composer { display:flex; align-items:center; gap:12px; padding:8px 9px 8px 17px; border:1px solid #386df3; border-radius:15px; background:#071327; box-shadow:0 0 20px #284fc824; }
    .composer textarea { flex:1; min-height:46px; resize:none; border:0; outline:0; background:transparent; color:white; font:16px inherit; padding:12px 0; }
    .send { width:44px; height:44px; border:0; border-radius:12px; background:#25468f; color:white; font-size:24px; cursor:pointer; }
    .hint { padding-left:5px; color:var(--muted); font-size:12px; }
    .rail { padding:31px; border-left:1px solid #1d2c4a; background:#0914269c; }
    .rail h2 { margin:0; font-size:22px; }
    .rail-head { display:flex; align-items:center; justify-content:space-between; padding-bottom:21px; border-bottom:1px solid #1f304e; }
    .pulse { color:#8a5dff; font-size:29px; }
    .side-section { padding-top:25px; }
    .side-section h3 { margin:0 0 17px; font-size:18px; }
    .today-line { display:flex; justify-content:space-between; gap:12px; padding:9px 0; border-bottom:1px solid #1d2c4a; color:#dfe8fd; font-size:14px; }
    .today-line:last-child { border-bottom:0; }
    .today-line strong { font-weight:650; }
    .today-line small { color:#95a4c5; text-align:right; }
    .today-action { padding:0; border:0; background:none; color:#9fb7ff; font:inherit; text-align:left; cursor:pointer; text-decoration:underline; text-underline-offset:3px; }
    .steps { padding:20px 0 24px; border-bottom:1px solid #1f304e; }
    .step { position:relative; padding:0 0 21px 44px; color:#aeb9d1; }
    .step:last-child { padding-bottom:0; }
    .step:before { content:''; position:absolute; left:10px; top:6px; width:15px; height:15px; border:2px solid #8090b1; border-radius:50%; background:#101a2c; }
    .step:after { content:''; position:absolute; left:17px; top:24px; height:30px; border-left:1px solid #4d5d7b; }
    .step:last-child:after { display:none; }
    .step.active { color:white; }
    .step.active:before { border-color:#5790ff; background:#275ed6; box-shadow:0 0 14px #3679ff; }
    .step strong { display:block; font-size:15px; }
    .step small { color:var(--muted); font-size:13px; }
    .history-item { display:block; width:100%; margin:0 0 8px; padding:10px 12px; border:1px solid #263b63; border-radius:9px; background:#0c1830; color:#e8edfc; font:inherit; text-align:left; cursor:pointer; }
    .history-item:hover { border-color:#637ff3; background:#101f3d; }
    .history-item strong { display:block; overflow:hidden; font-size:13px; text-overflow:ellipsis; white-space:nowrap; }
    .history-item small { display:block; margin-top:3px; color:#9eadca; text-transform:capitalize; }
    .workspace-search { display:flex; gap:8px; }
    .workspace-search input { min-width:0; flex:1; border:1px solid #31486f; border-radius:8px; background:#0a162c; color:var(--text); font:14px inherit; padding:9px 10px; }
    .workspace-search button { padding:8px 10px; font-size:13px; }
    .workspace-result { display:block; width:100%; padding:9px 0; border:0; border-bottom:1px solid #1d2c4a; background:transparent; color:#dce6fb; font:14px inherit; text-align:left; cursor:default; }
    .workspace-result:last-child { border-bottom:0; }
    .workspace-result small { display:block; margin-top:3px; color:#8291b2; font-size:12px; }
    .event { position:relative; padding:0 0 16px 23px; color:#bec8e0; font-size:14px; }
    .event:before { content:''; position:absolute; left:3px; top:6px; width:7px; height:7px; border-radius:50%; background:#91a0cc; }
    .event time { display:block; margin-top:3px; color:#7785a9; font-size:12px; }
    .empty { padding:28px 10px; color:var(--muted); font-size:15px; text-align:center; }
    pre { overflow:auto; white-space:pre-wrap; }
    @media (max-width:900px) { .shell { padding:12px; } .top { height:auto; gap:12px; flex-wrap:wrap; padding-bottom:12px; } .tools { order:3; width:100%; justify-content:space-between; gap:5px; } .frame { grid-template-columns:1fr; } .rail { border-top:1px solid #1d2c4a; border-left:0; } .conversation { padding:28px 20px; } .message { max-width:95%; } .agent { grid-template-columns:64px 1fr; } .orb { width:55px; height:55px; font-size:24px; } .clock { font-size:13px; } }
  </style>
</head>
<body>
  <div class="shell">
    <header class="top"><div class="brand">dopOS</div><div class="clock" id="clock"></div><div class="tools" aria-label="Local tool status"><span id="tool-docker">Docker</span><span id="tool-github">GitHub</span><span id="tool-ollama">Local AI</span></div></header>
    <main class="frame">
      <section class="conversation">
        <div class="thread" id="thread"><div class="empty">Ask dopOS about this machine. It will create a safe plan and wait for your decision.</div></div>
        <form class="composer" onsubmit="submitWork(event)"><span aria-hidden="true">＋</span><textarea id="request" aria-label="Ask dopOS anything" placeholder="Ask dopOS anything"></textarea><button class="send" aria-label="Send request">↑</button></form>
        <div class="hint">Plans are frozen before approval. Local Qwen explains plans; it cannot select actions.</div>
      </section>
      <aside class="rail">
        <div class="rail-head"><h2>Live Work</h2><span class="pulse">⌁</span></div>
        <div class="side-section"><h3>Today</h3><div id="today" class="empty">Loading local state…</div></div>
        <div class="side-section"><h3>Workspace</h3><form class="workspace-search" onsubmit="searchWorkspace(event)"><input id="workspace-query" aria-label="Search workspace filenames and folders" maxlength="160" placeholder="Find a file or folder"><button class="button" type="submit">Find</button></form><div id="workspace-results" class="empty">Search stays local and reads names only.</div></div>
        <div class="steps"><div class="step active"><strong>Goal</strong><small>Waiting for your request</small></div><div class="step"><strong>Plan</strong><small>Safe actions only</small></div><div class="step"><strong>Build</strong><small>Approval required</small></div><div class="step"><strong>Test</strong><small>Evidence captured</small></div><div class="step"><strong>Verify</strong><small>Diary updated</small></div></div>
        <div class="side-section"><h3>Recent work</h3><div id="recent" class="empty">No work yet.</div></div>
        <div class="side-section"><h3>Diary</h3><div id="diary" class="empty">No activity yet.</div></div>
      </aside>
    </main>
  </div>
<script>
const api = async (path, body) => { const response = await fetch(path, { method: body !== undefined ? 'POST' : 'GET', headers: {'Content-Type':'application/json'}, body: body !== undefined ? JSON.stringify(body) : undefined }); const value = await response.json(); if (!response.ok) throw Error(value.error); return value; };
let current;
function escape(value) { const element = document.createElement('div'); element.textContent = value; return element.innerHTML; }
function clock() { document.querySelector('#clock').textContent = new Intl.DateTimeFormat(undefined, {dateStyle:'medium', timeStyle:'short'}).format(new Date()); }
function setStep(index) { [...document.querySelectorAll('.step')].forEach((element, position) => element.classList.toggle('active', position <= index)); }
clock(); setInterval(clock, 30000);

async function loadTools() { try { const tools = await api('/tools/status'); for (const [name, value] of Object.entries(tools)) { const element = document.querySelector(`#tool-${name}`); if (!element) continue; const available = value.available && value.ok !== false; element.classList.toggle('status-off', !available); element.title = available ? 'Available locally' : (value.error || value.reason || 'Unavailable locally'); } } catch { document.querySelectorAll('.tools span').forEach(element => element.classList.add('status-off')); } }
async function loadControls() { try { const state = await api('/controls/kill-switch'); let control = document.querySelector('#control-status'); if (!control) { control = document.createElement('button'); control.id = 'control-status'; control.className = 'button'; control.style.padding = '5px 9px'; control.style.fontSize = '12px'; document.querySelector('.tools').append(control); } const paused = state.kill_switch === 'on'; control.textContent = paused ? 'Execution paused — Resume' : 'Safety ready'; control.classList.toggle('danger', paused); control.title = paused ? 'Execution is blocked. Click to resume explicitly.' : 'Safe actions require your approval.'; control.onclick = paused ? async () => { await api('/controls/kill-switch', {enabled:false}); loadControls(); } : null; } catch {} }
async function loadToday() { try { const [state, loop, queue] = await Promise.all([api('/today'), api('/autonomous-loop'), api('/autonomous-loop/queue')]); const lines = []; if (state.needs_decision.length) lines.push(`<div class="today-line"><button class="today-action" onclick="openWork(${state.needs_decision[0].work_item_id})">${state.needs_decision.length} decision${state.needs_decision.length === 1 ? '' : 's'} waiting</button><small>approval</small></div>`); if (state.in_motion.length) lines.push(`<div class="today-line"><button class="today-action" onclick="openWork(${state.in_motion[0].work_item_id})">${state.in_motion.length} approved plan${state.in_motion.length === 1 ? '' : 's'}</button><small>ready to run</small></div>`); if (!lines.length) lines.push('<div class="today-line"><strong>Nothing waiting</strong><small>new work can be planned</small></div>'); lines.push(`<div class="today-line"><strong>Recovery</strong><small>${state.recovery.audit_chain_valid ? 'audit verified' : 'needs review'} · ${state.recovery.backup_count} backup${state.recovery.backup_count === 1 ? '' : 's'}</small></div>`); const latest = loop.cycles[0]; lines.push(`<div class="today-line"><strong>Automation</strong><small>${latest ? `${escape(latest.result)} · ${escape(latest.title)}` : 'no cycle recorded'}</small></div>`); const next = queue.items[0]; lines.push(`<div class="today-line"><strong>Queue</strong><small>${next ? `next · ${escape(next.title)}` : 'no queued work'}</small></div>`); today.innerHTML = lines.join(''); } catch { today.innerHTML = '<div class="empty">Today is unavailable.</div>'; } }
function controls() { return '<div class="buttons"><button class="button primary" onclick="approve()">Approve</button><button class="button" onclick="reject()">Reject</button><button class="button danger" onclick="stop()">Stop</button></div>'; }
function renderPlan(plan, title = 'Ready to execute plan') { current = plan; thread.innerHTML = `<div class="agent"><div class="orb"></div><div><div><span class="label">dopOS</span><span class="time">just now</span></div><p class="explain">${escape(plan.explanation)}</p><div class="plan"><h3>${title}</h3><p>This plan is frozen. It contains only local, read-only checks.</p><div class="actions">${plan.actions.map(action => `<span>${escape(action)}</span>`).join('')}</div>${controls()}</div></div></div>`; setStep(1); loadDiary(); loadRecent(); loadToday(); }
function formatResults(results) { return results.map(entry => { const result = entry.result; if (entry.action === 'status.summary') return `<div><strong>Host records</strong><p>${result.work_items} work items · ${result.plans} plans · ${result.audit_events} audit events</p></div>`; if (entry.action === 'docker.status') return `<div><strong>Docker status</strong><pre>${escape(result.containers || result.error || result.reason || 'No Docker details returned.')}</pre></div>`; if (entry.action === 'quality.status') return `<div><strong>Local quality checks</strong><p>${result.ok ? 'All fixed checks passed.' : 'One or more checks need attention.'}</p><div class="actions">${(result.checks || []).map(check => `<span>${escape(check.name)} · ${check.passed ? 'passed' : 'failed'}</span>`).join('')}</div></div>`; if (entry.action === 'workspace.status') return `<div><strong>Workspace inventory</strong><p>${result.count} local document${result.count === 1 ? '' : 's'} found. Names and paths only.</p>${(result.documents || []).map(document => `<div class="workspace-result">${escape(document.path)}<small>${escape(document.extension)} · ${document.size} bytes</small></div>`).join('')}</div>`; if (entry.action === 'backup.create') return `<div><strong>Local backup created</strong><p>${escape(result.path)} · audit chain ${result.audit_chain_valid ? 'verified' : 'needs review'}</p></div>`; if (entry.action === 'backup.verify') return `<div><strong>Recovery backups</strong><p>${escape(result.message)}</p><div class="actions">${(result.backups || []).map(check => `<span>${escape(check.name)} · ${check.ok ? 'verified' : 'needs review'}</span>`).join('')}</div></div>`; if (entry.action === 'diary.preview') return '<div><strong>Diary updated</strong><p>The approved run and its evidence have been recorded.</p></div>'; return `<div><strong>${escape(entry.action)}</strong><p>${escape(JSON.stringify(result))}</p></div>`; }).join(''); }
async function submitWork(event) { event.preventDefault(); const text = request.value.trim(); if (!text) return; thread.innerHTML = `<div class="message user">${escape(text)}</div><div class="agent"><div class="orb"></div><div><span class="label">dopOS</span><p class="explain">Preparing the smallest safe plan…</p></div></div>`; setStep(0); try { const item = await api('/work-items', {title:text.slice(0,80), request:text}); renderPlan(await api('/plans/from-request', {work_item_id:item.id})); request.value = ''; } catch (error) { thread.innerHTML += `<div class="plan">${escape(error.message)}</div>`; } }
async function executeApproved() { try { const done = await api(`/plans/${current.id}/execute`, {}); thread.innerHTML += `<div class="plan"><h3>Completed</h3><p>The approved local checks finished successfully.</p><div class="results">${formatResults(done.results)}</div></div>`; setStep(4); loadDiary(); loadRecent(); loadToday(); } catch (error) { thread.innerHTML += `<div class="plan">${escape(error.message)}</div>`; } }
async function approve() { try { await api(`/plans/${current.id}/approve`, {}); setStep(2); await executeApproved(); } catch (error) { thread.innerHTML += `<div class="plan">${escape(error.message)}</div>`; } }
async function reject() { await api(`/plans/${current.id}/reject`, {}); thread.innerHTML += '<div class="plan"><h3>Plan rejected</h3><p>No action was run.</p></div>'; loadDiary(); loadRecent(); loadToday(); }
async function stop() { await api('/controls/kill-switch', {enabled:true}); thread.innerHTML += '<div class="plan"><h3>Stop control enabled</h3><p>Execution is blocked until it is explicitly resumed.</p></div>'; loadDiary(); loadControls(); }
async function loadRecent() { try { const items = await api('/work-items'); recent.innerHTML = items.slice(0,5).map(item => `<button class="history-item" onclick="openWork(${item.id})"><strong>${escape(item.title)}</strong><small>${escape(item.plan?.state || 'draft')}</small></button>`).join('') || '<div class="empty">No work yet.</div>'; } catch {} }
async function searchWorkspace(event) { event.preventDefault(); const query = document.querySelector('#workspace-query').value.trim(); const results = document.querySelector('#workspace-results'); results.innerHTML = '<div class="empty">Searching local names…</div>'; try { const state = await api(`/workspace?query=${encodeURIComponent(query)}`); const prefix = state.count ? '' : '<div class="empty">No matching local documents.</div>'; results.innerHTML = prefix + state.documents.map(document => `<div class="workspace-result">${escape(document.path)}<small>${escape(document.extension)} · ${document.size} bytes</small></div>`).join(''); } catch (error) { results.innerHTML = `<div class="empty">${escape(error.message)}</div>`; } }
async function openWork(id) { try { const item = await api(`/work-items/${id}`); const plan = item.plan; if (!plan) { thread.innerHTML = `<div class="plan"><h3>${escape(item.title)}</h3><p>${escape(item.request)}</p><p>No plan has been created yet.</p></div>`; return; } if (plan.state === 'awaiting_approval') { renderPlan(plan, 'Saved plan'); return; } current = plan; const outcome = plan.state === 'completed' ? `<h3>Completed</h3><p>Recorded result from the approved run.</p><div class="results">${formatResults(plan.results || [])}</div>` : plan.state === 'approved' ? `<p>This plan is approved and can be run now.</p><div class="buttons"><button class="button primary" onclick="executeApproved()">Execute approved plan</button><button class="button danger" onclick="stop()">Stop</button></div>` : `<p>This plan is ${escape(plan.state)}.</p>`; thread.innerHTML = `<div class="message user">${escape(item.request)}</div><div class="agent"><div class="orb"></div><div><span class="label">dopOS</span><p class="explain">${escape(plan.explanation)}</p><div class="plan"><h3>Saved plan</h3><div class="actions">${plan.actions.map(action => `<span>${escape(action)}</span>`).join('')}</div>${outcome}</div></div></div>`; setStep(plan.state === 'completed' ? 4 : plan.state === 'approved' ? 2 : 1); } catch (error) { thread.innerHTML = `<div class="plan">${escape(error.message)}</div>`; } }
async function loadDiary() { try { const events = await api('/journal'); diary.innerHTML = events.slice(-6).reverse().map(event => `<div class="event">${escape(event.summary)}<time>${new Date(event.created_at).toLocaleString()}${event.detail ? ` · ${escape(event.detail)}` : ''}</time></div>`).join('') || '<div class="empty">No activity yet.</div>'; } catch {} }
loadTools(); loadControls(); loadToday(); loadRecent();
</script>
</body>
</html>'''
