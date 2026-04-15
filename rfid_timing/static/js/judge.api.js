(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function request(url, method, body) {
    return page.state.http.requestData(url, method, body);
  }

  function buildProtocolQuery(target) {
    if (!target) return '';
    if (Array.isArray(target.category_ids) && target.category_ids.length > 0) {
      return '?category_ids=' + target.category_ids.join(',');
    }
    if (target.category_id) {
      return '?category_id=' + target.category_id;
    }
    return '';
  }

  page.api = {
    request: request,
    getCategories: function () {
      return request('/api/categories', 'GET');
    },
    getRaceState: function (categoryId) {
      return request('/api/state' + (categoryId ? '?category_id=' + categoryId : ''), 'GET');
    },
    getRiders: function () {
      return request('/api/riders', 'GET');
    },
    getStartProtocol: function (target) {
      if (typeof target !== 'object' || target === null) {
        target = { category_id: target };
      }
      return request('/api/judge/start-protocol' + buildProtocolQuery(target), 'GET');
    },
    saveStartProtocol: function (payload, intervalSec, riderIds) {
      if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
        payload = {
          category_id: parseInt(payload, 10),
          interval_sec: intervalSec,
          rider_ids: riderIds,
        };
      }
      return request('/api/judge/start-protocol', 'POST', payload);
    },
    autoFillStartProtocol: function (payload, intervalSec) {
      if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
        payload = {
          category_id: parseInt(payload, 10),
          interval_sec: intervalSec,
        };
      }
      return request('/api/judge/start-protocol/auto-fill', 'POST', payload);
    },
    clearStartProtocol: function (target) {
      if (typeof target !== 'object' || target === null) {
        target = { category_id: target };
      }
      return request('/api/judge/start-protocol' + buildProtocolQuery(target), 'DELETE');
    },
    getStartProtocolStatus: function (target) {
      if (typeof target !== 'object' || target === null) {
        target = { category_id: target };
      }
      return request('/api/judge/start-protocol/status' + buildProtocolQuery(target), 'GET');
    },
    launchStartProtocol: function (payload) {
      return request('/api/judge/start-protocol/launch', 'POST', payload);
    },
    startProtocolRider: function (payload) {
      return request('/api/judge/start-protocol/start-rider', 'POST', payload);
    },
    stopStartProtocol: function (payload) {
      if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
        payload = { category_id: parseInt(payload, 10) };
      }
      return request('/api/judge/start-protocol/stop', 'POST', payload);
    },
    individualStart: function (riderId) {
      return request('/api/judge/individual-start', 'POST', { rider_id: riderId });
    },
    massStart: function (payload) {
      if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
        return request('/api/judge/mass-start', 'POST', payload);
      }
      return request('/api/judge/mass-start', 'POST', { category_id: parseInt(payload, 10) });
    },
    finishRace: function (categoryId) {
      return request('/api/judge/finish-race', 'POST', { category_id: parseInt(categoryId, 10) });
    },
    resetCategory: function (categoryId) {
      return request('/api/judge/reset-category', 'POST', {
        category_id: parseInt(categoryId, 10),
      });
    },
    newRace: function () {
      return request('/api/settings/reset-race', 'POST');
    },
    getRiderStatus: function (riderId) {
      return request('/api/judge/rider-status/' + riderId, 'GET');
    },
    getRiderLaps: function (riderId) {
      return request('/api/judge/rider-laps/' + riderId, 'GET');
    },
    updateLap: function (lapId, lapTimeMs) {
      return request('/api/judge/lap/' + lapId, 'PUT', { lap_time_ms: lapTimeMs });
    },
    deleteLap: function (lapId) {
      return request('/api/judge/lap/' + lapId, 'DELETE');
    },
    addManualLap: function (riderId) {
      return request('/api/judge/manual-lap', 'POST', { rider_id: riderId });
    },
    editFinishTime: function (riderId, finishTimeMs) {
      return request('/api/judge/edit-finish-time', 'POST', {
        rider_id: riderId,
        finish_time_ms: finishTimeMs,
      });
    },
    unfinishRider: function (riderId) {
      return request('/api/judge/unfinish-rider', 'POST', { rider_id: riderId });
    },
    dnf: function (riderId, reasonCode) {
      return request('/api/judge/dnf', 'POST', { rider_id: riderId, reason_code: reasonCode });
    },
    dsq: function (riderId, reason) {
      return request('/api/judge/dsq', 'POST', { rider_id: riderId, reason: reason });
    },
    timePenalty: function (riderId, seconds, reason) {
      return request('/api/judge/time-penalty', 'POST', {
        rider_id: riderId,
        seconds: seconds,
        reason: reason,
      });
    },
    extraLap: function (riderId, laps, reason) {
      return request('/api/judge/extra-lap', 'POST', {
        rider_id: riderId,
        laps: laps,
        reason: reason,
      });
    },
    warning: function (riderId, reason) {
      return request('/api/judge/warning', 'POST', { rider_id: riderId, reason: reason });
    },
    getLog: function () {
      return request('/api/judge/log', 'GET');
    },
    deletePenalty: function (penaltyId) {
      return request('/api/judge/penalty/' + penaltyId, 'DELETE');
    },
    getNotes: function () {
      return request('/api/judge/notes', 'GET');
    },
    addNote: function (text, riderId) {
      return request('/api/judge/notes', 'POST', { text: text, rider_id: riderId || null });
    },
    deleteNote: function (noteId) {
      return request('/api/judge/notes/' + noteId, 'DELETE');
    },
  };
})();
