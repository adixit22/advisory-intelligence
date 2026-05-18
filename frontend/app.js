// ── State ──────────────────────────────────────────────────────
let allClients = [];
let currentClient = null;
let currentBrief = null;
let currentMarket = null;
let videoPollingInterval = null;

// ── Boot ───────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadClients();
  loadMarketTicker();
});

// ── View Router ────────────────────────────────────────────────
function showView(name) {
  document.querySelectorAll('video').forEach(v => { v.pause(); v.currentTime = 0; });
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`view-${name}`).classList.add('active');
  const titles = { clients: 'Client Book', market: 'Market Pulse', profile: 'Client Profile', brief: 'Client Brief' };
  document.getElementById('topbar-title').textContent = titles[name] || name;
  const navMap = { clients: 0, market: 1 };
  if (navMap[name] !== undefined) document.querySelectorAll('.nav-item')[navMap[name]].classList.add('active');
  if (name === 'market') loadMarketData();
}

// ── Risk Badge ─────────────────────────────────────────────────
function riskBadgeStyle(risk) {
  const map = {
    'Aggressive': { bg: 'rgba(239,68,68,0.15)', color: '#ef4444' },
    'Moderate-Aggressive': { bg: 'rgba(245,158,11,0.15)', color: '#f59e0b' },
    'Moderate': { bg: 'rgba(99,102,241,0.15)', color: '#818cf8' },
    'Conservative': { bg: 'rgba(16,185,129,0.15)', color: '#10b981' },
  };
  const s = map[risk] || { bg: 'rgba(99,102,241,0.15)', color: '#818cf8' };
  return `background:${s.bg};color:${s.color};`;
}

function returnColor(val, bench) {
  if (val >= bench) return '#10b981';
  if (val >= bench - 2) return '#f59e0b';
  return '#ef4444';
}

function formatAUM(val) {
  if (val >= 1000000) return `$${(val / 1000000).toFixed(1)}M`;
  if (val >= 1000) return `$${(val / 1000).toFixed(0)}K`;
  return `$${val}`;
}

// ── Client Roster ──────────────────────────────────────────────
async function loadClients() {
  try {
    const res = await fetch('/api/clients');
    allClients = await res.json();
    renderClientGrid(allClients);
  } catch (e) {
    document.getElementById('client-grid').innerHTML = '<div class="loading-state">Failed to load clients. Is the server running?</div>';
  }
}

function renderClientGrid(clients) {
  const grid = document.getElementById('client-grid');
  if (!clients.length) {
    grid.innerHTML = '<div class="loading-state">No clients match your search.</div>';
    return;
  }
  grid.innerHTML = clients.map(c => {
    const ytdColor = returnColor(c.ytd_return, c.benchmark_return);
    const ytdSign = c.ytd_return >= 0 ? '+' : '';
    return `
      <div class="client-card" style="--card-accent:${c.avatar_color}" onclick="openClientProfile('${c.id}')">
        <div class="client-card-header">
          <div class="client-avatar" style="background:${c.avatar_color}">${c.avatar_initials}</div>
          <div>
            <div class="client-card-name">${c.name}</div>
            <div class="client-card-occ">${c.occupation}</div>
            <div class="client-card-loc">📍 ${c.location}</div>
          </div>
        </div>
        <div class="client-card-stats">
          <div class="stat-item">
            <div class="stat-val" style="color:#10b981">${formatAUM(c.aum)}</div>
            <div class="stat-label">AUM</div>
          </div>
          <div class="stat-item">
            <div class="stat-val" style="color:${ytdColor}">${ytdSign}${c.ytd_return}%</div>
            <div class="stat-label">YTD Return</div>
          </div>
          <div class="stat-item">
            <div class="stat-val">${c.age}</div>
            <div class="stat-label">Age</div>
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span class="risk-badge" style="${riskBadgeStyle(c.risk_profile)}">${c.risk_profile}</span>
          <span style="font-size:12px;color:var(--text-muted)">Last met: ${c.last_meeting || 'N/A'}</span>
        </div>
      </div>`;
  }).join('');
}

function filterClients() {
  const q = document.getElementById('client-search').value.toLowerCase();
  const filtered = allClients.filter(c =>
    c.name.toLowerCase().includes(q) ||
    c.occupation.toLowerCase().includes(q) ||
    c.location.toLowerCase().includes(q) ||
    c.risk_profile.toLowerCase().includes(q)
  );
  renderClientGrid(filtered);
}

// ── Client Profile ─────────────────────────────────────────────
async function openClientProfile(id) {
  try {
    const [clientRes, cacheRes] = await Promise.all([
      fetch(`/api/clients/${id}`),
      fetch(`/api/brief/${id}/cached`)
    ]);
    currentClient = await clientRes.json();
    const cacheData = await cacheRes.json();
    // If a valid cached brief exists, store it so the user can view it instantly
    currentBrief = cacheData.cached ? cacheData : null;
    renderProfile(currentClient, cacheData);
    showView('profile');
  } catch (e) {
    showToast('Failed to load client profile');
  }
}

function formatAge(seconds) {
  if (seconds < 3600)  return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)} hours ago`;
  return 'over a day ago';
}

function renderProfile(c, cache) {
  const holdingColors = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#0ea5e9', '#a855f7'];
  const holdingsRows = c.holdings.map((h, i) => {
    const color = holdingColors[i % holdingColors.length];
    return `
      <tr>
        <td>${h.asset}</td>
        <td style="font-weight:700;color:#10b981">$${h.value.toLocaleString()}</td>
        <td>
          <div class="alloc-bar-container">
            <div class="alloc-bar-bg">
              <div class="alloc-bar-fill" style="width:${h.allocation}%;background:${color}"></div>
            </div>
            <span style="font-weight:700;color:${color};font-size:13px;width:36px;text-align:right">${h.allocation}%</span>
          </div>
        </td>
      </tr>`;
  }).join('');

  const ytdColor = returnColor(c.ytd_return, c.benchmark_return);

  document.getElementById('profile-content').innerHTML = `
    <div style="margin-bottom:20px">
      <h2>${c.name} <span style="font-size:16px;color:var(--text-muted);font-weight:400">— Full Profile</span></h2>
    </div>

    <div class="profile-grid">
      <!-- Left column -->
      <div>
        <div class="profile-card" style="margin-bottom:16px">
          <div class="profile-hero">
            <div class="profile-avatar-lg" style="background:${c.avatar_color}">${c.avatar_initials}</div>
            <div class="profile-name">${c.name}</div>
            <div class="profile-occ">${c.occupation}</div>
            <div class="profile-loc">📍 ${c.location}</div>
            <div class="profile-aum">
              <div class="aum-value">$${c.aum.toLocaleString()}</div>
              <div class="aum-label">Assets Under Management</div>
            </div>
          </div>
          <div class="profile-details">
            <div class="detail-row"><span class="detail-key">Age</span><span class="detail-val">${c.age} years</span></div>
            <div class="detail-row"><span class="detail-key">Marital Status</span><span class="detail-val">${c.marital_status}</span></div>
            <div class="detail-row"><span class="detail-key">Dependents</span><span class="detail-val">${c.dependents}</span></div>
            <div class="detail-row"><span class="detail-key">Annual Income</span><span class="detail-val">$${c.annual_income.toLocaleString()}</span></div>
            <div class="detail-row"><span class="detail-key">Risk Profile</span><span class="detail-val"><span class="risk-badge" style="${riskBadgeStyle(c.risk_profile)}">${c.risk_profile}</span></span></div>
            <div class="detail-row"><span class="detail-key">Risk Score</span><span class="detail-val">${c.risk_score}/10</span></div>
            <div class="detail-row"><span class="detail-key">Horizon</span><span class="detail-val">${c.investment_horizon}</span></div>
          </div>
        </div>

        <!-- Performance -->
        <div class="profile-card">
          <div class="section-title">Performance</div>
          <div class="perf-row">
            <span class="perf-label">YTD Return</span>
            <div class="perf-bar-bg"><div class="perf-bar-fill" style="width:${Math.min(c.ytd_return * 4, 100)}%;background:${ytdColor}"></div></div>
            <span class="perf-val" style="color:${ytdColor}">${c.ytd_return > 0 ? '+' : ''}${c.ytd_return}%</span>
          </div>
          <div class="perf-row">
            <span class="perf-label">Benchmark</span>
            <div class="perf-bar-bg"><div class="perf-bar-fill" style="width:${Math.min(c.benchmark_return * 4, 100)}%;background:var(--text-muted)"></div></div>
            <span class="perf-val" style="color:var(--text-muted)">${c.benchmark_return}%</span>
          </div>
        </div>
      </div>

      <!-- Right column -->
      <div>
        <!-- Goals -->
        <div class="profile-card" style="margin-bottom:16px">
          <div class="section-title">Investment Goals</div>
          <ul class="goals-list">
            ${c.goals.map(g => `<li class="goal-item"><div class="goal-dot"></div><span>${g}</span></li>`).join('')}
          </ul>
        </div>

        <!-- Life Events -->
        <div class="profile-card" style="margin-bottom:16px">
          <div class="section-title">Key Life Events</div>
          <ul class="events-list">
            ${c.life_events.map(e => `<li class="event-item"><div class="event-dot"></div><span>${e}</span></li>`).join('')}
          </ul>
        </div>

        <!-- Holdings -->
        <div class="profile-card" style="margin-bottom:16px">
          <div class="section-title">Portfolio Holdings</div>
          <table class="holdings-table">
            <thead><tr><th>Asset</th><th>Value</th><th>Allocation</th></tr></thead>
            <tbody>${holdingsRows}</tbody>
          </table>
        </div>

        <!-- Advisor Notes -->
        <div class="profile-card">
          <div class="section-title">Advisor Notes</div>
          <p style="font-size:14px;line-height:1.7;color:var(--text-secondary)">${c.advisor_notes}</p>
        </div>
      </div>
    </div>

    <div class="profile-actions">
      ${cache && cache.cached ? `
        <div style="display:flex;flex-direction:column;gap:6px;align-items:flex-start">
          <div style="display:flex;gap:10px;align-items:center">
            <button class="btn btn-primary" onclick="viewCachedBrief()">
              📋 View Last Brief
            </button>
            <button class="btn btn-ghost" onclick="generateBrief('${c.id}')">
              ↺ Regenerate Brief
            </button>
            <button class="btn btn-ghost" onclick="showView('clients')">
              ← Back to Client Book
            </button>
          </div>
          <span style="font-size:12px;color:var(--text-muted);padding-left:4px">
            Last generated ${formatAge(cache.age_seconds)} &nbsp;·&nbsp; ${new Date(cache.generated_at).toLocaleString('en-US',{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}
          </span>
        </div>
      ` : `
        <div style="display:flex;gap:10px;align-items:center">
          <button class="btn btn-primary" onclick="generateBrief('${c.id}')">
            ✨ Generate Client Brief
          </button>
          <button class="btn btn-ghost" onclick="showView('clients')">
            ← Back to Client Book
          </button>
        </div>
      `}
    </div>
  `;
}

// ── Brief Generation ───────────────────────────────────────────

// Show cached brief instantly — no API call needed
function viewCachedBrief() {
  if (!currentBrief) return;
  renderBrief(currentBrief);
  showView('brief');
}

// Back to profile — re-opens with fresh cache check so buttons are always correct
function backToProfile() {
  if (currentClient) openClientProfile(currentClient.id);
  else showView('profile');
}

async function generateBrief(clientId) {
  showView('brief');
  document.getElementById('brief-content').innerHTML = `
    <div class="generating-state">
      <div class="pulse-icon">✨</div>
      <div style="font-size:18px;font-weight:700;margin-bottom:8px">Generating Personalized Brief</div>
      <div style="color:var(--text-secondary);font-size:14px">Pulling live market data and crafting ${currentClient.name}'s brief with AI...</div>
    </div>`;

  try {
    const res = await fetch(`/api/brief/${clientId}`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Brief generation failed');
    }
    const data = await res.json();
    currentBrief = data;
    renderBrief(data);
  } catch (e) {
    document.getElementById('brief-content').innerHTML = `
      <div class="generating-state">
        <div style="font-size:32px">⚠️</div>
        <div style="font-size:16px;margin:12px 0">${e.message}</div>
        <button class="btn btn-ghost" onclick="backToProfile()">← Back to Profile</button>
      </div>`;
  }
}

async function renderBrief(data) {
  const c = currentClient;
  const brief = data.brief;

  // Check if a video already exists on disk before rendering
  let existingVideo = null;
  try {
    const vr = await fetch(`/api/video/${c.id}/exists`);
    const vd = await vr.json();
    if (vd.exists) existingVideo = vd.url;
  } catch (e) { /* ignore */ }
  const summaryParas = brief.client_summary.split('\n\n').filter(Boolean);
  const talkingPoints = brief.advisor_talking_points || [];

  document.getElementById('brief-content').innerHTML = `
    <div style="margin-bottom:20px;display:flex;justify-content:space-between;align-items:center">
      <div>
        <h2>${c.name} — Client Brief</h2>
        <p style="color:var(--text-secondary);font-size:14px;margin-top:4px">
          ${data.cached ? `📋 Cached brief · Generated ${formatAge(data.age_seconds)}` : `✨ Generated with live market data`}
          &nbsp;·&nbsp; ${data.market_data?.fetched_at || 'Today'}
          ${data.feedback_used ? `&nbsp;·&nbsp; <span style="color:#10b981;font-weight:600">💬 Feedback incorporated</span>` : ''}
        </p>
      </div>
      <div style="display:flex;gap:10px;align-items:center">
        <button class="btn btn-ghost" onclick="openFeedbackModal()" title="Log post-meeting notes for AI to use next time">📝 Post-Meeting Notes</button>
        <button class="btn btn-ghost" onclick="backToProfile()">← Back to Profile</button>
      </div>
    </div>

    <div class="brief-layout">
      <!-- Left: Summary + Video -->
      <div>
        <!-- Market Impact -->
        <div class="market-impact-box">
          <strong style="color:#f59e0b">📊 Market Impact:</strong> ${brief.market_impact_summary || ''}
        </div>

        <!-- Client Summary -->
        <div class="brief-card">
          <div class="brief-card-title">Client Summary <span class="badge">For Client</span></div>
          <div class="client-summary-text">
            ${summaryParas.map(p => `<p>${p}</p>`).join('')}
          </div>
        </div>

        <!-- Video Section -->
        <div class="video-section" id="video-section">
          <div class="brief-card-title" style="border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:16px">
            🎬 Personalized Video Brief
          </div>
          <div class="video-player-wrapper" id="video-wrapper">
            ${existingVideo ? `
              <video controls style="width:100%;height:100%">
                <source src="${existingVideo}" type="video/mp4">
              </video>` : `
              <div class="video-placeholder">
                <div class="icon">▶️</div>
                <p>Click below to generate your personalized video brief</p>
              </div>`}
          </div>
          <div class="video-actions">
            <button class="btn btn-green" id="btn-generate-video"
              style="${existingVideo ? 'display:none' : ''}"
              onclick="startVideoGeneration('${c.id}')">
              🎬 Generate Video
            </button>
            <button class="btn btn-secondary" id="btn-regenerate-video"
              style="${existingVideo ? '' : 'display:none'}"
              onclick="startVideoGeneration('${c.id}')">
              ↺ Regenerate Video
            </button>
            <button class="btn btn-secondary" id="btn-download-video"
              style="${existingVideo ? '' : 'display:none'}"
              onclick="downloadVideo('${c.id}')">
              ⬇ Download Video
            </button>
            <button class="btn btn-secondary" id="btn-send-video"
              style="${existingVideo ? '' : 'display:none'}"
              onclick="openEmailModal('video')">
              ✉️ Send Video to Client
            </button>
          </div>
        </div>
      </div>

      <!-- Right: Talking Points + Actions -->
      <div>
        <!-- Advisor Talking Points -->
        <div class="brief-card">
          <div class="brief-card-title">Advisor Talking Points <span class="badge" style="background:#10b981">For You</span></div>
          <div class="talking-points">
            ${talkingPoints.map((tp, i) => `
              <div class="talking-point" style="border-left-color:${['#6366f1','#10b981','#f59e0b','#ec4899'][i%4]}">
                ${tp}
              </div>`).join('')}
          </div>
        </div>

        <!-- Next Action -->
        <div class="brief-card">
          <div class="brief-card-title">Recommended Next Action</div>
          <div class="next-action-box">
            <strong style="color:#10b981">→</strong> ${brief.next_action || ''}
          </div>
        </div>

        <!-- Share Talking Points -->
        <div class="brief-card">
          <div class="brief-card-title">Share With Client</div>
          <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px">
            Send this summary and talking points to prepare ${c.name} for your upcoming meeting.
          </p>
          <button class="btn btn-primary" style="width:100%" onclick="openEmailModal('summary')">
            ✉️ Send Summary to Client
          </button>
        </div>

        <!-- Live Market Factors -->
        <div class="brief-card">
          <div class="brief-card-title">Live Market Factors</div>
          ${renderMiniMarket(data.market_data)}
        </div>
      </div>
    </div>

    <!-- Feedback Modal -->
    <div class="modal-overlay" id="feedback-modal">
      <div class="modal" style="max-width:560px">
        <div class="modal-title">📝 Post-Meeting Notes</div>
        <p style="font-size:13px;color:var(--text-secondary);margin-bottom:16px">
          These notes are saved and incorporated by AI the next time you generate a brief for ${c.name}.
        </p>

        <div class="modal-field">
          <label>Meeting Date</label>
          <input type="date" id="fb-date" value="${new Date().toISOString().split('T')[0]}" />
        </div>

        <div class="modal-field">
          <label>Overall Meeting Rating</label>
          <div id="fb-stars" style="display:flex;gap:8px;margin-top:6px">
            ${[1,2,3,4,5].map(n => `<button class="star-btn" data-val="${n}" onclick="setRating(${n})" style="font-size:24px;background:none;border:none;cursor:pointer;color:#4a5568">★</button>`).join('')}
          </div>
          <input type="hidden" id="fb-rating" value="0" />
        </div>

        <div class="modal-field">
          <label>Topics that resonated most with ${c.name.split(' ')[0]}</label>
          <input type="text" id="fb-resonated" placeholder="e.g. Portfolio performance, bond allocation, retirement timeline" />
        </div>

        <div class="modal-field">
          <label>Concerns ${c.name.split(' ')[0]} raised</label>
          <textarea id="fb-concerns" placeholder="e.g. Worried about tech concentration, asked about inflation impact on bonds..." style="height:70px"></textarea>
        </div>

        <div class="modal-field">
          <label>What to focus on more next time</label>
          <textarea id="fb-focus" placeholder="e.g. Deeper dive on crypto allocation, tax efficiency strategies..." style="height:70px"></textarea>
        </div>

        <div class="modal-field">
          <label>Actions agreed in this meeting</label>
          <textarea id="fb-actions" placeholder="e.g. Rebalance tech to 20%, review beneficiary designations, send ESG fund options..." style="height:70px"></textarea>
        </div>

        <div class="modal-field">
          <label>Your private advisor notes</label>
          <textarea id="fb-notes" placeholder="Anything else AI should know for next time — client mood, life updates, etc." style="height:60px"></textarea>
        </div>

        <div class="modal-actions">
          <button class="btn btn-ghost" onclick="closeFeedbackModal()">Cancel</button>
          <button class="btn btn-primary" onclick="saveFeedback('${c.id}')">Save Notes ✓</button>
        </div>
      </div>
    </div>

    <!-- Email Modal -->
    <div class="modal-overlay" id="email-modal">
      <div class="modal">
        <div class="modal-title" id="modal-title">Send to Client</div>
        <div class="modal-field">
          <label>To</label>
          <input type="email" id="modal-to" placeholder="client@email.com" />
        </div>
        <div class="modal-field">
          <label>Subject</label>
          <input type="text" id="modal-subject" />
        </div>
        <div class="modal-field">
          <label>Message</label>
          <textarea id="modal-body"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
          <button class="btn btn-primary" onclick="sendEmail()">Send ✉️</button>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div class="toast" id="toast"></div>
  `;
}

function renderMiniMarket(market) {
  if (!market) return '<p style="color:var(--text-muted);font-size:13px">No market data</p>';
  const factors = Object.entries(market).filter(([k]) => k !== 'fetched_at' && k !== 'is_live');
  return factors.map(([k, f]) => {
    const chg = f.change_pct || 0;
    const color = f.impact === 'positive' ? '#10b981' : f.impact === 'negative' ? '#ef4444' : '#94a3b8';
    const arrow = chg >= 0 ? '▲' : '▼';
    const valStr = typeof f.value === 'number' && f.value > 1000 ? `$${f.value.toLocaleString()}` : `${f.value}${f.unit || ''}`;
    return `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">
        <span style="font-size:13px;color:var(--text-secondary)">${f.label}</span>
        <span style="font-size:13px;font-weight:700;color:${color}">${valStr} <span style="font-size:11px">${arrow}${Math.abs(chg).toFixed(2)}%</span></span>
      </div>`;
  }).join('');
}

// ── Video Generation ───────────────────────────────────────────
async function startVideoGeneration(clientId) {
  if (!currentBrief) return;
  document.getElementById('btn-generate-video').disabled = true;
  const regenBtn = document.getElementById('btn-regenerate-video');
  if (regenBtn) regenBtn.style.display = 'none';
  document.getElementById('video-wrapper').innerHTML = `
    <div class="video-progress">
      <div class="spinner"></div>
      <div class="progress-text" id="progress-text">Starting video generation...</div>
      <div style="font-size:12px;color:var(--text-muted);margin-top:8px">This takes 1-2 minutes. Please wait.</div>
    </div>`;

  try {
    const res = await fetch(`/api/video/${clientId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        brief: currentBrief.brief,
        market_data: currentBrief.market_data
      })
    });
    if (!res.ok) throw new Error('Failed to start video generation');

    pollVideoStatus(clientId);
  } catch (e) {
    document.getElementById('video-wrapper').innerHTML = `<div class="video-placeholder"><div class="icon">⚠️</div><p>${e.message}</p></div>`;
    document.getElementById('btn-generate-video').disabled = false;
  }
}

function pollVideoStatus(clientId) {
  if (videoPollingInterval) clearInterval(videoPollingInterval);
  videoPollingInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/video/${clientId}/status`);
      const status = await res.json();

      if (status.status === 'generating') {
        const el = document.getElementById('progress-text');
        if (el) el.textContent = status.progress || 'Generating slides and narration...';
      } else if (status.status === 'ready') {
        clearInterval(videoPollingInterval);
        document.getElementById('video-wrapper').innerHTML = `
          <video controls style="width:100%;height:100%">
            <source src="${status.url}?t=${Date.now()}" type="video/mp4">
          </video>`;
        document.getElementById('btn-generate-video').style.display = 'none';
        const regen = document.getElementById('btn-regenerate-video');
        if (regen) regen.style.display = 'inline-flex';
        document.getElementById('btn-download-video').style.display = 'inline-flex';
        document.getElementById('btn-send-video').style.display = 'inline-flex';
        showToast('Video ready!');
      } else if (status.status === 'error') {
        clearInterval(videoPollingInterval);
        document.getElementById('video-wrapper').innerHTML = `<div class="video-placeholder"><div class="icon">⚠️</div><p>Video generation failed: ${status.detail}</p></div>`;
        document.getElementById('btn-generate-video').disabled = false;
      }
    } catch (e) { /* silent */ }
  }, 3000);
}

function downloadVideo(clientId) {
  window.open(`/api/video/${clientId}/file`, '_blank');
}

// ── Email Modal ────────────────────────────────────────────────
function openEmailModal(type) {
  const c = currentClient;
  const brief = currentBrief?.brief;
  const modal = document.getElementById('email-modal');

  if (type === 'video') {
    document.getElementById('modal-title').textContent = '✉️ Send Video Brief to Client';
    document.getElementById('modal-subject').value = `Your Personalized Portfolio Brief — ${new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}`;
    document.getElementById('modal-body').value =
      `Dear ${c.name.split(' ')[0]},\n\nI've prepared a short personalized video summarizing your portfolio performance and key insights for our upcoming meeting.\n\nPlease review it at your convenience — I look forward to discussing this with you in person.\n\nBest regards,\nYour Advisor`;
  } else {
    document.getElementById('modal-title').textContent = '✉️ Send Summary to Client';
    document.getElementById('modal-subject').value = `Portfolio Update — ${new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}`;
    const firstName = c.name.split(' ')[0];
    let summary = brief?.client_summary?.split('\n\n')[0] || '';
    // Strip leading "Robert, " or "Robert " that Claude adds — greeting already has the name
    summary = summary.replace(new RegExp(`^${firstName}[,.]?\\s*`, 'i'), '');
    summary = summary.charAt(0).toUpperCase() + summary.slice(1);
    document.getElementById('modal-body').value =
      `Dear ${firstName},\n\n${summary}\n\nI look forward to speaking with you soon.\n\nBest regards,\nYour Advisor`;
  }

  modal.classList.add('open');
}

function closeModal() {
  document.getElementById('email-modal').classList.remove('open');
}

function sendEmail() {
  const to = document.getElementById('modal-to').value;
  const subject = document.getElementById('modal-subject').value;
  const body = document.getElementById('modal-body').value;
  const mailtoLink = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  window.open(mailtoLink, '_blank');
  closeModal();
  showToast('Opening email client...');
}

// ── Feedback Modal ────────────────────────────────────────────
function openFeedbackModal() {
  const modal = document.getElementById('feedback-modal');
  if (!modal) return;
  // Pre-fill if existing feedback saved
  fetch(`/api/feedback/${currentClient.id}`)
    .then(r => r.json())
    .then(data => {
      if (data.exists === false) return;
      if (data.meeting_date) document.getElementById('fb-date').value = data.meeting_date;
      if (data.rating)       setRating(data.rating);
      if (data.resonated_topics) document.getElementById('fb-resonated').value = data.resonated_topics;
      if (data.client_concerns)  document.getElementById('fb-concerns').value  = data.client_concerns;
      if (data.focus_next_time)  document.getElementById('fb-focus').value     = data.focus_next_time;
      if (data.agreed_actions)   document.getElementById('fb-actions').value   = data.agreed_actions;
      if (data.advisor_notes)    document.getElementById('fb-notes').value     = data.advisor_notes;
    })
    .catch(() => {});
  modal.classList.add('open');
}

function closeFeedbackModal() {
  const modal = document.getElementById('feedback-modal');
  if (modal) modal.classList.remove('open');
}

function setRating(val) {
  document.getElementById('fb-rating').value = val;
  document.querySelectorAll('.star-btn').forEach(btn => {
    btn.style.color = parseInt(btn.dataset.val) <= val ? '#f59e0b' : '#4a5568';
  });
}

async function saveFeedback(clientId) {
  const payload = {
    meeting_date:     document.getElementById('fb-date').value,
    rating:           parseInt(document.getElementById('fb-rating').value) || 0,
    resonated_topics: document.getElementById('fb-resonated').value.trim(),
    client_concerns:  document.getElementById('fb-concerns').value.trim(),
    focus_next_time:  document.getElementById('fb-focus').value.trim(),
    agreed_actions:   document.getElementById('fb-actions').value.trim(),
    advisor_notes:    document.getElementById('fb-notes').value.trim(),
  };
  try {
    const res = await fetch(`/api/feedback/${clientId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      closeFeedbackModal();
      showToast('Notes saved — AI will incorporate these in the next brief ✓');
    }
  } catch (e) {
    showToast('Failed to save feedback');
  }
}

// ── Market Data ────────────────────────────────────────────────
async function loadMarketTicker() {
  try {
    const res = await fetch('/api/market');
    const data = await res.json();
    const factors = data.factors;
    const sp = factors.sp500;
    const vix = factors.vix;
    if (sp && sp.value !== 'N/A') {
      const sign = sp.change_pct >= 0 ? '+' : '';
      const color = sp.change_pct >= 0 ? '#10b981' : '#ef4444';
      document.getElementById('market-ticker').innerHTML =
        `S&P 500: <span style="color:${color};font-weight:700">${sp.value.toLocaleString()} (${sign}${sp.change_pct}%)</span>&nbsp;&nbsp;VIX: ${vix.value}`;
    }
  } catch (e) { /* silent */ }
}

async function loadMarketData() {
  document.getElementById('market-cards').innerHTML = '<div class="loading-state">Fetching live data...</div>';
  try {
    const res = await fetch('/api/market');
    const data = await res.json();
    renderMarketCards(data.factors);
    document.getElementById('market-narrative-text').textContent = data.narrative;
    document.getElementById('market-narrative-box').style.display = 'block';
    const updatedEl = document.getElementById('market-last-updated');
    if (updatedEl) {
      const ts = data.factors?.fetched_at || new Date().toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
      updatedEl.textContent = `Last updated: ${ts}`;
    }
  } catch (e) {
    document.getElementById('market-cards').innerHTML = '<div class="loading-state">Failed to fetch market data.</div>';
  }
}

function renderMarketCards(factors) {
  const cards = Object.entries(factors).filter(([k]) => k !== 'fetched_at' && k !== 'is_live').map(([k, f]) => {
    const chg = f.change_pct || 0;
    const color = f.impact === 'positive' ? '#10b981' : f.impact === 'negative' ? '#ef4444' : '#94a3b8';
    const arrow = chg >= 0 ? '▲' : '▼';
    const valStr = typeof f.value === 'number' && f.value > 1000 ? `$${f.value.toLocaleString()}` : `${f.value}${f.unit || ''}`;
    return `
      <div class="market-card">
        <div class="market-card-label">${f.label}</div>
        <div class="market-card-value" style="color:${color}">${valStr}</div>
        <div class="market-card-change" style="color:${color}">${arrow} ${Math.abs(chg).toFixed(2)}%</div>
        <div class="market-card-desc">${f.description}</div>
      </div>`;
  });
  document.getElementById('market-cards').innerHTML = cards.join('');
}

// ── Toast ──────────────────────────────────────────────────────
function showToast(msg) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3000);
}
