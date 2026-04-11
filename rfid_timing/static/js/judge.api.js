(function () {
  const page = window.JudgePage || (window.JudgePage = {});

  function request(url, method, body) {
    return page.state.http.requestData(url, method, body);
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
    getStartProtocol: function (categoryId) {
      return request('/api/judge/start-protocol?category_id=' + categoryId, 'GET');
    },
    saveStartProtocol: function (categoryId, intervalSec, riderIds) {
      return request('/api/judge/start-protocol', 'POST', {
        category_id: parseInt(categoryId, 10),
        interval_sec: intervalSec,
        rider_ids: riderIds,
      });
    },
    autoFillStartProtocol: function (categoryId, intervalSec) {
      return request('/api/judge/start-protocol/auto-fill', 'POST', {
        category_id: parseInt(categoryId, 10),
        interval_sec: intervalSec,
      });
    },
    clearStartProtocol: function (categoryId) {
      return request('/api/judge/start-protocol?category_id=' + categoryId, 'DELETE');
    },
    getStartProtocolStatus: function (categoryId) {
      return request('/api/judge/start-protocol/status?category_id=' + categoryId, 'GET');
    },
    launchStartProtocol: function (payload) {
      return request('/api/judge/start-protocol/launch', 'POST', payload);
    },
    stopStartProtocol: function (categoryId) {
      return request('/api/judge/start-protocol/stop', 'POST', {
        category_id: parseInt(categoryId, 10),
      });
    },
    individualStart: function (riderId) {
      return request('/api/judge/individual-start', 'POST', { rider_id: riderId });
    },
    massStart: function (categoryId) {
      return request('/api/judge/mass-start', 'POST', { category_id: parseInt(categoryId, 10) });
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
