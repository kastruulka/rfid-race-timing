(function () {
  async function request(url, options, parseAs) {
    const opts = Object.assign({ credentials: 'same-origin' }, options || {});
    const response = await fetch(url, opts);
    let data;

    try {
      if (parseAs === 'text') {
        data = await response.text();
      } else if (parseAs === 'blob') {
        data = await response.blob();
      } else {
        data = await response.json();
      }
    } catch {
      data = parseAs === 'text' ? '' : null;
    }

    return {
      ok: response.ok,
      status: response.status,
      data: data,
      unauthorized: response.status === 401,
    };
  }

  window.httpClient = {
    fetchJson: function (url, options) {
      return request(url, options, 'json');
    },
    fetchText: function (url, options) {
      return request(url, options, 'text');
    },
    fetchBlob: function (url, options) {
      return request(url, options, 'blob');
    },
  };
})();
