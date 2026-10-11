/* ============================================================
   DE-CHIMEX PRINT HUB - internal (work) messaging client.
   Reuses the notifications hub (/hubs/notifications): every
   authenticated account joins its own user group, so both the
   admin area and the developer portal receive "internalMessage"
   events. Keeps the sidebar unread badge current, appends live
   messages to an open conversation (and marks them read), and
   toasts new messages on pages that do not already surface them.
   Server counts and persisted read states remain authoritative.
   ============================================================ */
(function () {
  'use strict';

  var script = document.currentScript;
  var base = (script && script.getAttribute('data-base')) || '/admin/team-messages';
  var toasts = (script && script.getAttribute('data-toasts')) === 'true';

  var badge = document.getElementById('teamMsgBadge');
  var page = document.querySelector('[data-team-conversation]');
  var pageConversationId = page ? page.getAttribute('data-team-conversation') : '';
  var myId = page ? (page.getAttribute('data-my-id') || '') : '';

  function csrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content') || '';
    var input = document.querySelector('input[name="__RequestVerificationToken"]');
    return input ? input.value : '';
  }

  /* ---------- unread badge ---------- */
  function fetchCount() {
    fetch(base + '/unread-count', { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!badge || !data || typeof data.count !== 'number') return;
        if (data.count > 0) {
          badge.textContent = data.count > 99 ? '99+' : String(data.count);
          badge.hidden = false;
        } else {
          badge.hidden = true;
        }
      })
      .catch(function () { /* keep last known count */ });
  }

  function postRead(conversationId) {
    return fetch(base + '/' + encodeURIComponent(conversationId) + '/read', {
      method: 'POST', credentials: 'same-origin',
      headers: { RequestVerificationToken: csrf(), Accept: 'application/json' }
    }).catch(function () { /* server state stays authoritative; next load reconciles */ });
  }

  /* ---------- live append (mirrors Conversation.cshtml bubble markup) ---------- */
  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }
  function fmt(iso) {
    var dt = new Date(iso);
    if (isNaN(dt.getTime())) return '';
    var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var pad = function (n) { return (n < 10 ? '0' : '') + n; };
    return pad(dt.getDate()) + ' ' + months[dt.getMonth()] + ' ' + dt.getFullYear() + ' ' + pad(dt.getHours()) + ':' + pad(dt.getMinutes());
  }
  function appendLive(p) {
    var list = document.querySelector('[data-team-messages-list]');
    if (!list) return;
    var empty = list.querySelector('p');
    if (empty) empty.remove();
    var mine = String(p.senderId) === String(myId);
    var div = document.createElement('div');
    div.setAttribute('data-team-msg', p.messageId);
    div.style.cssText = 'padding:10px 12px;border:1px solid rgba(128,128,128,.25);border-radius:10px;margin-bottom:8px;max-width:75%;' + (mine ? 'margin-left:auto' : '');
    div.innerHTML = '<div style="font-size:12px;opacity:.75">' + esc(p.senderName) + ' · ' + esc(fmt(p.sentUtc)) + '</div>' +
      '<div style="white-space:pre-wrap;word-break:break-word">' + esc(p.body) + '</div>';
    list.appendChild(div);
    div.scrollIntoView({ block: 'nearest' });
  }

  /* ---------- SignalR ---------- */
  if (!badge && !page) return; // neither sidebar badge nor conversation page: nothing to do
  if (badge) fetchCount();
  if (!window.signalR) return;

  var connection = new signalR.HubConnectionBuilder()
    .withUrl('/hubs/notifications', { withCredentials: true, transport: signalR.HttpTransportType.WebSockets })
    .withAutomaticReconnect([0, 2000, 10000, 30000])
    .configureLogging(signalR.LogLevel.Warning)
    .build();

  connection.on('internalMessage', function (p) {
    if (!p) return;
    if (pageConversationId && p.conversationId === pageConversationId) {
      if (String(p.senderId) !== String(myId) && !document.querySelector('[data-team-msg="' + p.messageId + '"]')) {
        appendLive(p);
        // The recipient is looking at the conversation: clear the unread state now.
        postRead(pageConversationId);
      }
      fetchCount();
      return;
    }
    fetchCount();
    if (toasts && String(p.senderId) !== String(myId) && window.DeChimexToast) {
      var body = p.body && p.body.length > 140 ? p.body.slice(0, 140) + '…' : (p.body || '');
      window.DeChimexToast.show('Message from ' + (p.senderName || 'a colleague'), body,
        { href: base + '/' + p.conversationId, text: 'Open' });
    }
  });

  connection.onreconnected(function () { fetchCount(); });

  connection.start().then(function () { fetchCount(); }).catch(function () {
    // Anonymous/transport failure: badge simply stays as server-rendered.
  });
})();
